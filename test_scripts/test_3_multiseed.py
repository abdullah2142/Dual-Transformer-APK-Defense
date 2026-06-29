!pip install torch transformers tree_sitter==0.21.3 scikit-learn matplotlib -q

import os, json, random, copy, math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from torch.utils.data import DataLoader, Dataset, Subset
from torch.optim import AdamW
from torch.cuda.amp import autocast, GradScaler
from transformers import (
    get_linear_schedule_with_warmup,
    RobertaConfig, RobertaModel,
    AutoTokenizer)

from sklearn.metrics import (
    accuracy_score, f1_score,
    roc_auc_score, average_precision_score,
    classification_report
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tqdm import tqdm
from collections import defaultdict

print("Imports OK")
print(f"CUDA: {torch.cuda.is_available()}")

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
class Args:
    train_file         = "/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl"
    pretrained_encoder = ""   # TODO: /kaggle/input/.../model.bin (GraphCodeBERT+DFG)

    model_name_or_path = "microsoft/graphcodebert-base"
    tokenizer_name     = "microsoft/graphcodebert-base"

    code_length        = 384
    data_flow_length   = 128
    train_batch_size   = 16
    eval_batch_size    = 32
    learning_rate      = 2e-5
    max_grad_norm      = 1.0
    num_train_epochs   = 5         # epochs per seed
    patience           = 2         # early stopping patience
    
    # ── KEY: list of seeds to run ──
    seeds              = [42, 123, 2025]

    # FREEZE_ENCODER = True  → only train classifier head (fast, ~10 min/seed)
    # FREEZE_ENCODER = False → full fine-tune (slow, ~6h/seed)
    freeze_encoder     = False

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_gpu  = torch.cuda.device_count()

args = Args()

print(f"Device  : {args.device}")
print(f"Seeds   : {args.seeds}")
print(f"Frozen  : {args.freeze_encoder}")

# ─── MODEL ────────────────────────────────────────────────────────────────────
class DFGModel(nn.Module):
    def __init__(self, encoder, config, seed):
        super().__init__()
        self.encoder    = encoder
        self.config     = config
        self.dropout    = nn.Dropout(config.hidden_dropout_prob)

        # Initialise the head with a fixed seed so only the seed arg matters
        torch.manual_seed(seed)
        self.classifier = nn.Linear(config.hidden_size, 2)

    def forward(self, input_ids=None, p_ids=None, attn_mask=None, labels=None):
        ext = (1.0 - attn_mask) * -10000.0
        ext = ext.unsqueeze(1)
        emb = self.encoder.embeddings(input_ids=input_ids, position_ids=p_ids)
        out = self.encoder.encoder(
            emb, attention_mask=ext,
            head_mask=[None] * self.config.num_hidden_layers
        )[0]
        logits = self.classifier(self.dropout(out[:, 0, :]))
        prob   = F.softmax(logits, dim=-1)
        if labels is not None:
            return CrossEntropyLoss()(logits, labels), prob
        return prob

# ─── DATASET ──────────────────────────────────────────────────────────────────
class TextDataset(Dataset):
    def __init__(self, tokenizer, args, file_path):
        self.args = args
        self.tokenizer = tokenizer
        self.total_len = args.code_length + args.data_flow_length
        with open(file_path, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()
            
    def __len__(self):
        return len(self.lines)

    def _get_char_index(self, code_lines, coord):
        row, col = coord
        char_idx = 0
        for i in range(min(row, len(code_lines))):
            char_idx += len(code_lines[i]) 
        return char_idx + col

    def __getitem__(self, item):
        entry = json.loads(self.lines[item])
        code = entry.get('code', '')
        dfg = entry.get('dfg', [])[:self.args.data_flow_length]
        label = int(entry.get('label', 0)) if entry.get('label') is not None else 0

        tokens_obj = self.tokenizer(
            code, 
            max_length=self.args.code_length, 
            truncation=True, 
            padding='max_length',
            return_offsets_mapping=True
        )
        input_ids = tokens_obj['input_ids']
        offsets = tokens_obj['offset_mapping']
        code_lines = code.splitlines(keepends=True)

        dfg_ids = [self.tokenizer.unk_token_id] * len(dfg)
        pos_to_node_idx = {}
        node_to_token_map = {}

        for node_idx, item_node in enumerate(dfg):
            start_pos, end_pos = item_node[1][0], item_node[1][1]
            pos_key = (start_pos[0], start_pos[1], end_pos[0], end_pos[1])
            pos_to_node_idx[pos_key] = node_idx
            
            char_start = self._get_char_index(code_lines, start_pos)
            char_end = self._get_char_index(code_lines, end_pos)
            
            aligned_tokens = []
            for t_idx, (t_start, t_end) in enumerate(offsets):
                if t_start == t_end: continue
                if (t_start >= char_start and t_end <= char_end) or (char_start >= t_start and char_end <= t_end):
                    aligned_tokens.append(t_idx)
            node_to_token_map[node_idx] = aligned_tokens

        attn_mask = np.zeros((self.total_len, self.total_len), dtype=bool)
        c_len = self.args.code_length
        attn_mask[:c_len, :c_len] = True
        
        for node_idx, item_node in enumerate(dfg):
            abs_node_idx = c_len + node_idx
            for t_idx in node_to_token_map.get(node_idx, []):
                attn_mask[abs_node_idx, t_idx] = True
                attn_mask[t_idx, abs_node_idx] = True
            
            for p_pos in item_node[4]:
                p_key = (p_pos[0][0], p_pos[0][1], p_pos[1][0], p_pos[1][1])
                if p_key in pos_to_node_idx:
                    abs_parent_idx = c_len + pos_to_node_idx[p_key]
                    attn_mask[abs_node_idx, abs_parent_idx] = True
                    attn_mask[abs_parent_idx, abs_node_idx] = True
            attn_mask[abs_node_idx, abs_node_idx] = True

        full_input_ids = input_ids + dfg_ids
        p_ids = [i + 2 for i in range(c_len)] + [0] * len(dfg_ids)
        padding_len = self.total_len - len(full_input_ids)
        
        if padding_len > 0:
            full_input_ids += [self.tokenizer.pad_token_id] * padding_len
            p_ids += [1] * padding_len
        
        return {
            'input_ids': torch.tensor(full_input_ids, dtype=torch.long),
            'p_ids': torch.tensor(p_ids, dtype=torch.long),
            'attn_mask': torch.tensor(attn_mask, dtype=torch.float),
            'label': torch.tensor(label, dtype=torch.long)
        }

# ─── STRATIFIED SPLIT ─────────────────────────────────────────────────────────
def infer_source(entry):
    for key in ("source", "dataset", "origin", "project"):
        value = entry.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return "unknown"

def allocate_counts(total_needed, groups, fraction):
    raw = {g: len(v) * fraction for g, v in groups.items()}
    base = {g: int(math.floor(v)) for g, v in raw.items()}
    remainder = total_needed - sum(base.values())
    order = sorted(groups.keys(), key=lambda g: (raw[g] - base[g], len(groups[g])), reverse=True)
    for g in order[:remainder]:
        base[g] += 1
    return base

def get_stratified_indices(filepath, test_ratio=0.10, val_ratio=0.08, seed=42):
    with open(filepath, 'r', encoding='utf-8') as f:
        entries = [json.loads(line) for line in f]
    
    rng = random.Random(seed) # Fixed seed for splitting
    source_to_indices = defaultdict(list)
    for idx, entry in enumerate(entries):
        source_to_indices[infer_source(entry)].append(idx)

    for indices in source_to_indices.values():
        rng.shuffle(indices)

    total = len(entries)
    target_test = int(round(total * test_ratio))
    target_val = int(round(total * val_ratio))
    target_train = total - target_test - target_val

    test_alloc = allocate_counts(target_test, source_to_indices, test_ratio)
    trainval_groups = {}
    test_indices = []
    for source, indices in source_to_indices.items():
        take = min(test_alloc[source], len(indices))
        test_indices.extend(indices[:take])
        trainval_groups[source] = indices[take:]

    adjusted_val_ratio = val_ratio / (1.0 - test_ratio)
    val_alloc = allocate_counts(target_val, trainval_groups, adjusted_val_ratio)

    val_indices, train_indices = [], []
    for source, indices in trainval_groups.items():
        take = min(val_alloc[source], len(indices))
        val_indices.extend(indices[:take])
        train_indices.extend(indices[take:])

    return sorted(train_indices), sorted(val_indices), sorted(test_indices)

print("Calculating stratified split (82/8/10) with fixed seed=42...")
train_indices, val_indices, test_indices = get_stratified_indices(args.train_file)
print(f"Train: {len(train_indices)}, Val: {len(val_indices)}, Test: {len(test_indices)}")

# ─── EVALUATION FUNCTION ──────────────────────────────────────────────────────
@torch.no_grad()
def evaluate(model, dataset, desc="Eval"):
    loader = DataLoader(dataset, batch_size=args.eval_batch_size, num_workers=2, pin_memory=True)
    model.eval()
    preds, labels, probs_list = [], [], []
    for batch in loader:
        inp = {
            'input_ids': batch['input_ids'].to(args.device),
            'p_ids':     batch['p_ids'].to(args.device),
            'attn_mask': batch['attn_mask'].to(args.device)
        }
        prob = model(**inp)
        probs_list.extend(prob[:, 1].cpu().numpy())
        preds.extend(torch.argmax(prob, dim=-1).cpu().numpy())
        labels.extend(batch['label'].numpy())
    model.train()
    
    acc = accuracy_score(labels, preds)
    roc = roc_auc_score(labels, probs_list)
    return acc, roc, preds, np.array(probs_list), np.array(labels)

# ─── TRAINING LOOP ───────────────────────────────────────────────────────────
def train_one_seed(model, train_ds, val_ds, seed):
    loader = DataLoader(
        train_ds, batch_size=args.train_batch_size,
        shuffle=True, num_workers=2, pin_memory=True
    )

    params = model.classifier.parameters() if args.freeze_encoder else model.parameters()
    optimizer = AdamW(params, lr=args.learning_rate, eps=1e-8)
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=0,
        num_training_steps=len(loader) * args.num_train_epochs
    )
    scaler = GradScaler()

    best_val_acc = -1.0
    patience_counter = 0
    best_model_state = None

    for epoch in range(args.num_train_epochs):
        model.train()
        tr_loss = 0.0
        for batch in tqdm(loader, desc=f"  [seed {seed}] Epoch {epoch}"):
            inp = {
                'input_ids': batch['input_ids'].to(args.device),
                'p_ids':     batch['p_ids'].to(args.device),
                'attn_mask': batch['attn_mask'].to(args.device),
                'labels':    batch['label'].to(args.device)
            }
            optimizer.zero_grad()
            with autocast():
                loss, _ = model(**inp)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            tr_loss += loss.item()

        avg_loss = tr_loss / len(loader)
        
        # Validation
        val_acc, val_roc, _, _, _ = evaluate(model, val_ds, desc="Validation")
        print(f"  Epoch {epoch} | Loss: {avg_loss:.4f} | Val Acc: {val_acc:.4%} | Val ROC: {val_roc:.4f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
            best_model_state = copy.deepcopy(model.state_dict())
            print(f"  * New best validation accuracy!")
        else:
            patience_counter += 1
            print(f"  * No improvement. Patience {patience_counter}/{args.patience}")
            if patience_counter >= args.patience:
                print("  * Early stopping triggered.")
                break

    # Load best state
    if best_model_state is not None:
        model.load_state_dict(best_model_state)
    return model

# ─── MAIN: MULTI-SEED LOOP ────────────────────────────────────────────────────
if not args.pretrained_encoder or not os.path.exists(args.pretrained_encoder):
    print(f"Please specify a valid pretrained_encoder path. Given: {args.pretrained_encoder}")
else:
    print("Loading shared components...")
    config    = RobertaConfig.from_pretrained(args.model_name_or_path)
    config.num_labels = 2
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name, use_fast=True)
    print("  ✓ Config & tokenizer ready")

    print("Loading dataset...")
    full_ds = TextDataset(tokenizer, args, args.train_file)
    train_ds = Subset(full_ds, train_indices)
    val_ds = Subset(full_ds, val_indices)
    test_ds = Subset(full_ds, test_indices)

    # Load the pre-trained encoder weights ONCE
    print("\nLoading pre-trained encoder...")
    encoder_base = RobertaModel.from_pretrained(args.model_name_or_path, config=config)
    pretrained   = torch.load(args.pretrained_encoder, map_location='cpu')
    
    # Extract only encoder weights (strip classifier keys if any)
    encoder_state = {k.replace('encoder.', ''): v
                     for k, v in pretrained.items() if k.startswith('encoder.') or not k.startswith('classifier.')}
    encoder_base.load_state_dict(encoder_state, strict=False)
    print("  ✓ Encoder weights loaded")

    seed_results = []

    for seed in args.seeds:
        print(f"\n{'─'*55}")
        print(f"SEED {seed}")
        print(f"{'─'*55}")

        # Fix all RNG sources for this seed
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if args.n_gpu > 0:
            torch.cuda.manual_seed_all(seed)

        # Deep-copy encoder so each seed starts from identical pretrained weights
        enc   = copy.deepcopy(encoder_base)
        model = DFGModel(enc, config, seed).to(args.device)

        if args.freeze_encoder:
            for param in model.encoder.parameters():
                param.requires_grad = False
            trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
            print(f"  Encoder frozen. Trainable params: {trainable:,}")

        model = train_one_seed(model, train_ds, val_ds, seed)

        # Evaluate once on the held-out test set
        test_acc, _, test_preds, test_probs, test_labels = evaluate(model, test_ds, desc="Final Test")

        roc_auc = roc_auc_score(test_labels, test_probs)
        pr_auc  = average_precision_score(test_labels, test_probs)
        f1_mac  = f1_score(test_labels, test_preds, average='macro')
        f1_mal  = f1_score(test_labels, test_preds, pos_label=1)

        seed_results.append({
            'seed':    seed,
            'acc':     test_acc,
            'roc_auc': roc_auc,
            'pr_auc':  pr_auc,
            'f1_mac':  f1_mac,
            'f1_mal':  f1_mal
        })

        print(f"\n  Seed {seed} → Acc={test_acc:.4%}  ROC={roc_auc:.4f}  PR={pr_auc:.4f}  F1={f1_mac:.4f}\n")

    print("All seeds done!")

# ─── AGGREGATE & SAVE RESULTS ─────────────────────────────────────────────────
if 'seed_results' in locals() and seed_results:
    accs = [r['acc'] for r in seed_results]
    rocs = [r['roc_auc'] for r in seed_results]
    prs  = [r['pr_auc'] for r in seed_results]
    f1s  = [r['f1_mac'] for r in seed_results]

    m_acc, s_acc = np.mean(accs), np.std(accs)
    m_roc, s_roc = np.mean(rocs), np.std(rocs)
    m_pr,  s_pr  = np.mean(prs),  np.std(prs)
    m_f1,  s_f1  = np.mean(f1s),  np.std(f1s)

    report = (
        f"=== Test 4: Multi-Seed Robustness ({len(args.seeds)} seeds) ===\n"
        f"Accuracy  : {m_acc:.2%} ± {s_acc:.2%}\n"
        f"ROC-AUC   : {m_roc:.4f} ± {s_roc:.4f}\n"
        f"PR-AUC    : {m_pr:.4f} ± {s_pr:.4f}\n"
        f"F1 (macro): {m_f1:.4f} ± {s_f1:.4f}\n"
        "\nPer-seed details:\n"
    )
    for r in seed_results:
        report += f"Seed {r['seed']:>4}: Acc={r['acc']:.4%} ROC={r['roc_auc']:.4f} PR={r['pr_auc']:.4f}\n"

    print(report)

    os.makedirs('/kaggle/working', exist_ok=True)
    with open('/kaggle/working/test4_multiseed_results.txt', 'w') as f:
        f.write(report)
    print("Saved summary to /kaggle/working/test4_multiseed_results.txt")
