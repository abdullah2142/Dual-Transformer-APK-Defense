!pip install torch transformers tree_sitter==0.21.3 scikit-learn matplotlib -q

import os, json, random, math, hashlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from torch.utils.data import DataLoader, Dataset, Subset
from transformers import RobertaConfig, RobertaModel, AutoTokenizer
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from tqdm import tqdm
from collections import defaultdict, Counter

print("Imports OK")
print(f"CUDA: {torch.cuda.is_available()}")

# ─── CONFIGURATION ────────────────────────────────────────────────────────────
class Args:
    train_file = "/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl"
    # GraphCodeBERT text-only: top of Table 1 and the model the scanner deploys.
    # Table 4 is a capability claim, so it should rest on the best model rather
    # than on GCB+DFG, which the paper's own null-DFG finding calls the weaker
    # variant. See PAPER.md 5.6.
    gcb_text_weights = ""   # leave BLANK - resolver finds saved_models/best_model_text_only.bin

    model_name_or_path = "microsoft/graphcodebert-base"
    tokenizer_name     = "microsoft/graphcodebert-base"

    # 512, NOT 384: graphcodebert-train-text-only.ipynb trains at code_length 512
    # while every other text-only run uses 384. Scoring it at 384 would measure
    # the model at a length it never saw. See PAPER.md 4.3 finding 4.
    code_length       = 512
    data_flow_length  = 128   # unused by the text-only path; kept for TextDataset
    eval_batch_size   = 32
    seed              = 42

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_gpu  = torch.cuda.device_count()

args = Args()

# ─── CHECKPOINT RESOLVER ──────────────────────────────────────────────────────
# Canonical copy: test_scripts/resolve_checkpoints.py
#
# Finds each checkpoint under /kaggle/input and PRINTS the path it resolved, so
# model provenance lands in the run log automatically. Every `weights` field
# used to be a blank "# TODO", which is what let the CodeBERT split mismatch
# hide for two months (PAPER.md 10.4).
#
# Matches on '<dir>/<file>', never filename alone: THREE checkpoints are called
# best_model.bin (GCB+DFG, CodeBERT text, CodeBERT+DFG). Path components must
# match exactly, so 'saved_models/x' does not match 'saved_models_unixcoder/x'.
# Zero matches is an error; two or more is also an error -- it never guesses.
# Setting the Args field by hand overrides the search.
import glob as _g

def resolve(label, suffix, override=None, roots=('/kaggle/input', '/kaggle/working')):
    if override:
        if not os.path.exists(override):
            raise FileNotFoundError(f'{label}: path does not exist: {override}')
        print(f'  {label:24s} -> {override}  (explicit)')
        return override
    hits = sorted({p for r in roots if os.path.isdir(r)
                   for p in _g.glob(os.path.join(r, '**', suffix), recursive=True)})
    if len(hits) > 1:
        raise RuntimeError(f'{label}: {len(hits)} files match "{suffix}" -- refusing to guess.\n  '
                           + '\n  '.join(hits) + '\nAttach one training run per model.')
    if not hits:
        raise FileNotFoundError(
            f'{label}: nothing matching "{suffix}" under {list(roots)}. On Kaggle use '
            f'"+ Add Input -> Notebooks" and attach the training run that produced it. '
            f"Debug with: import glob; print(glob.glob('/kaggle/input/**/*.bin', recursive=True))")
    mb = os.path.getsize(hits[0]) / 1e6
    print(f'  {label:24s} -> {hits[0]}  ({mb:.0f} MB)')
    if mb < 100:
        print(f'  {"":24s}    WARNING: {mb:.0f} MB is small for a checkpoint (expect ~499 MB).')
    return hits[0]

print('Resolving checkpoints:')

args.gcb_text_weights = resolve('GCB text-only', 'saved_models/best_model_text_only.bin', override=args.gcb_text_weights or None)

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if args.n_gpu > 0:
        torch.cuda.manual_seed_all(seed)

set_seed(args.seed)

SOURCES = {
    'Devign'   : 'Devign (C/C++ — QEMU/FFmpeg)',
    'Draper'   : 'Draper (C/C++ — NVD/SARD)',
    'LVDAndro' : 'LVDAndro (Android Java/C)',
    'Juliet'   : 'Juliet Test Suite (Synthetic C/C++)',
}

print(f"Device : {args.device}")
print(f"Sources: {list(SOURCES.keys())}")

# ─── MODEL ────────────────────────────────────────────────────────────────────
class DFGModel(nn.Module):
    def __init__(self, encoder, config):
        super().__init__()
        self.encoder = encoder
        self.config = config
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, 2)

    def forward(self, input_ids=None, p_ids=None, attn_mask=None, labels=None):
        extended_attention_mask = (1.0 - attn_mask) * -10000.0
        extended_attention_mask = extended_attention_mask.unsqueeze(1)
        embedding_output = self.encoder.embeddings(input_ids=input_ids, position_ids=p_ids)
        encoder_outputs = self.encoder.encoder(
            embedding_output,
            attention_mask=extended_attention_mask,
            head_mask=[None] * self.config.num_hidden_layers
        )[0]
        logits = self.classifier(self.dropout(encoder_outputs[:, 0, :]))
        prob = F.softmax(logits, dim=-1)

        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(logits, labels)
            return loss, prob
        return prob

# ─── DATASET ──────────────────────────────────────────────────────────────────
class TextDataset(Dataset):
    def __init__(self, tokenizer, args, file_path, indices=None):
        self.args = args
        self.tokenizer = tokenizer
        self.total_len = args.code_length + args.data_flow_length
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        self.lines = [all_lines[i] for i in indices] if indices is not None else all_lines
            
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

# ─── SPLIT (matches training) + DUPLICATE FILTER ──────────────────────────────
# See REMEDIATION_PLAN.md §5.1.
#
# CRITICAL: the split must NOT be grouped by source. The training notebooks'
# infer_source finds no source key in this corpus (keys are only code/dfg/
# label/filename), so every entry resolved to "unknown" and the split became a
# single random shuffle. The previous version of this file recovered the source
# from the filename prefix and grouped by it, producing a DIFFERENT partition in
# which 89.9% of the "test" set was training data.
#
# Source is recovered AFTER the split, for table rows only.

def infer_source(entry):
    """Verbatim from the training notebooks. Do NOT add a filename fallback."""
    for key in ("source", "dataset", "origin", "project"):
        val = entry.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return "unknown"

def source_for_reporting(filename):
    """Recovers the true source from the filename prefix. REPORTING ONLY."""
    prefix = str(filename).split('_')[0]
    for known in SOURCES.keys():
        if known.lower() in prefix.lower():
            return known
    return prefix or "unknown"

def allocate_counts(total_needed, groups, fraction):
    raw = {g: len(v) * fraction for g, v in groups.items()}
    base = {g: int(math.floor(v)) for g, v in raw.items()}
    remainder = total_needed - sum(base.values())
    order = sorted(groups.keys(), key=lambda g: (raw[g] - base[g], len(groups[g])), reverse=True)
    for g in order[:remainder]:
        base[g] += 1
    return base

def get_split_indices(filepath, test_ratio=0.10, val_ratio=0.08, seed=42,
                      drop_duplicate_test=True):
    """Returns (train, val, test, report_sources). Reproduces the training
    partition exactly (163,967/15,997/19,996), then drops test entries that are
    byte-identical to a train/val entry."""
    srcs, hashes, report_sources = [], [], []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            e = json.loads(line)
            srcs.append(infer_source(e))
            hashes.append(hashlib.md5(str(e.get('code', '')).encode('utf-8', 'ignore')).hexdigest())
            report_sources.append(source_for_reporting(e.get('filename', '')))
            del e
    total = len(srcs)

    rng = random.Random(seed)
    source_to_indices = defaultdict(list)
    for idx, s in enumerate(srcs):
        source_to_indices[s].append(idx)
    for indices in source_to_indices.values():
        rng.shuffle(indices)

    target_test = int(round(total * test_ratio))
    target_val = int(round(total * val_ratio))

    test_alloc = allocate_counts(target_test, source_to_indices, test_ratio)
    trainval_groups, test_indices = {}, []
    for source, indices in source_to_indices.items():
        take = min(test_alloc[source], len(indices))
        test_indices.extend(indices[:take])
        trainval_groups[source] = indices[take:]

    val_alloc = allocate_counts(target_val, trainval_groups, val_ratio / (1.0 - test_ratio))
    val_indices, train_indices = [], []
    for source, indices in trainval_groups.items():
        take = min(val_alloc[source], len(indices))
        val_indices.extend(indices[:take])
        train_indices.extend(indices[take:])

    train_indices, val_indices = sorted(train_indices), sorted(val_indices)
    test_indices = sorted(test_indices)
    assert len(test_indices) == target_test
    assert set(train_indices).isdisjoint(test_indices)
    assert set(val_indices).isdisjoint(test_indices)
    print(f"Split: train={len(train_indices):,} val={len(val_indices):,} "
          f"test={len(test_indices):,}")

    if drop_duplicate_test:
        seen = {hashes[i] for i in train_indices}
        seen.update(hashes[i] for i in val_indices)
        before = len(test_indices)
        test_indices = [i for i in test_indices if hashes[i] not in seen]
        dropped = before - len(test_indices)
        print(f"Duplicate filter: dropped {dropped:,} ({dropped/before:.2%}) test "
              f"entries byte-identical to a train/val sample -> "
              f"{len(test_indices):,} clean")

    return train_indices, val_indices, test_indices, report_sources

print("Building split (matches training partition) ...")
_train_idx, _val_idx, test_indices, report_sources = get_split_indices(args.train_file)

# Group the CLEAN test indices by source, for the per-source table only.
test_indices_by_source = defaultdict(list)
for i in test_indices:
    test_indices_by_source[report_sources[i]].append(i)

total_test = sum(len(idxs) for idxs in test_indices_by_source.values())
print(f"Total clean test set size: {total_test:,}")
print("Test-set sample counts per source (after duplicate filter):")
for src in SOURCES:
    print(f"  {src:12s}: {len(test_indices_by_source.get(src, [])):,}")

# ─── TEXT-ONLY MODEL AND DATASET ────────────────────────────────────────────
class TextModel(nn.Module):
    """Text-only classifier. Mirrors the TextModel in test-6-imbalanced-eval.py."""
    def __init__(self, encoder, config):
        super(TextModel, self).__init__()
        self.encoder = encoder
        self.config = config
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, 2)

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        logits = self.classifier(self.dropout(outputs[0][:, 0, :]))
        prob = F.softmax(logits, dim=-1)
        if labels is not None:
            return CrossEntropyLoss()(logits, labels), prob
        return prob


class SimpleCodeDataset(Dataset):
    """Text-only dataset. Mirrors SimpleCodeDataset in test-6-imbalanced-eval.py.
    Emits input_ids/attention_mask only -- no DFG tensors."""
    def __init__(self, tokenizer, args, file_path, indices=None):
        self.tokenizer, self.args = tokenizer, args
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        self.lines = [lines[i] for i in indices] if indices is not None else lines

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, idx):
        entry = json.loads(self.lines[idx])
        tok = self.tokenizer(entry.get('code', ''), max_length=self.args.code_length,
                             truncation=True, padding='max_length')
        return {
            'input_ids': torch.tensor(tok['input_ids'], dtype=torch.long),
            'attention_mask': torch.tensor(tok['attention_mask'], dtype=torch.long),
            'label': torch.tensor(int(entry.get('label', 0) or 0), dtype=torch.long),
        }


# ─── EVALUATION FUNCTION ──────────────────────────────────────────────────────
@torch.no_grad()
def evaluate_subset(model, tokenizer, indices, args, label=''):
    ds = SimpleCodeDataset(tokenizer, args, args.train_file, indices=indices)
    loader = DataLoader(ds, batch_size=args.eval_batch_size, shuffle=False, num_workers=2)

    all_preds, all_labels, all_probs = [], [], []

    model.eval()
    for batch in tqdm(loader, desc=f'Eval ({label})', leave=False):
        inp = {
            'input_ids':      batch['input_ids'].to(args.device),
            'attention_mask': batch['attention_mask'].to(args.device),
        }
        labels = batch['label'].to(args.device)
        
        prob = model(**inp)
        probs = prob[:, 1].cpu().numpy()
        preds = torch.argmax(prob, dim=-1).cpu().numpy()
        
        all_preds.extend(preds)
        all_labels.extend(labels.cpu().numpy())
        all_probs.extend(probs)
    
    model.train()

    acc = accuracy_score(all_labels, all_preds)
    prec, rec, f1, _ = precision_recall_fscore_support(
        all_labels, all_preds, average='macro', zero_division=0)
    try:
        auc = roc_auc_score(all_labels, all_probs)
    except Exception:
        auc = float('nan')

    fn = sum(1 for p, l in zip(all_preds, all_labels) if l == 1 and p == 0)
    return acc, prec, rec, f1, auc, fn, len(indices)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if not args.gcb_text_weights or not os.path.exists(args.gcb_text_weights):
    print(f"Please configure args.gcb_text_weights. Given: {args.gcb_text_weights}")
    results = {}
else:
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer_name, use_fast=True)
    config = RobertaConfig.from_pretrained(args.model_name_or_path)
    config.num_labels = 2
    encoder = RobertaModel.from_pretrained(args.model_name_or_path, config=config)
    
    model = TextModel(encoder, config)
    print(f"Loading weights from {args.gcb_text_weights}")
    model.load_state_dict(torch.load(args.gcb_text_weights, map_location=args.device))
    model.to(args.device)
    
    print("\nRunning per-source evaluation on test set...\n")
    results = {}
    
    for prefix, label in SOURCES.items():
        src_indices = test_indices_by_source.get(prefix, [])
        if not src_indices:
            print(f"  ⚠ No test samples found for source: {prefix}")
            continue
            
        torch.cuda.empty_cache()
        import gc; gc.collect()
        
        print(f"  Evaluating {prefix} ({len(src_indices):,} samples)...")
        acc, prec, rec, f1, auc, fn, n = evaluate_subset(model, tokenizer, src_indices, args, prefix)
        results[prefix] = dict(label=label, acc=acc, prec=prec, rec=rec, f1=f1, auc=auc, fn=fn, n=n)
        print(f"    Acc={acc:.4%}  ROC-AUC={auc:.4f}  F1={f1:.4f}  FN={fn}")
        
    print("\nAll sources done!")

# ─── OUTPUT ───────────────────────────────────────────────────────────────────
if results:
    line = '=' * 72
    report = []
    report.append(line)
    report.append('PER-SOURCE ACCURACY BREAKDOWN (paper-ready table)')
    report.append(line)
    report.append(f'{"Source":<22} {"N":>7}  {"Accuracy":>10}  {"ROC-AUC":>10}  {"F1":>8}  {"FN":>6}')
    report.append('-' * 72)
    
    for prefix, R in results.items():
        report.append(f'{prefix:<22} {R["n"]:>7,}  {R["acc"]:>10.4%}  {R["auc"]:>10.4f}  {R["f1"]:>8.4f}  {R["fn"]:>6}')
        
    report.append(line)
    
    all_accs = [R['acc'] for R in results.values()]
    all_aucs = [R['auc'] for R in results.values()]
    all_f1s  = [R['f1']  for R in results.values()]
    report.append(f'Macro mean across sources: Acc={np.mean(all_accs):.4%}  AUC={np.nanmean(all_aucs):.4f}  F1={np.mean(all_f1s):.4f}')
    
    report_str = "\n".join(report)
    print(report_str)
    
    os.makedirs('/kaggle/working', exist_ok=True)
    with open('/kaggle/working/test5_per_source_results.txt', 'w') as f:
        f.write(report_str)
    print("Saved metrics to /kaggle/working/test5_per_source_results.txt")
    
    # ─── PLOT ─────────────────────────────────────────────────────────────────
    sources  = list(results.keys())
    accs     = [results[s]['acc']  for s in sources]
    aucs     = [results[s]['auc']  for s in sources]
    f1s      = [results[s]['f1']   for s in sources]

    x     = range(len(sources))
    width = 0.25
    colors = ['#4C72B0', '#55A868', '#C44E52']

    fig, ax = plt.subplots(figsize=(10, 5))
    b1 = ax.bar([i - width for i in x], accs, width, label='Accuracy',  color=colors[0])
    b2 = ax.bar([i         for i in x], aucs, width, label='ROC-AUC',   color=colors[1])
    b3 = ax.bar([i + width for i in x], f1s,  width, label='F1 (macro)',color=colors[2])

    for bar in [b1, b2, b3]:
        for rect in bar:
            h = rect.get_height()
            ax.annotate(f'{h:.3f}',
                        xy=(rect.get_x() + rect.get_width() / 2, h),
                        xytext=(0, 3),  
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9)

    ax.set_ylabel('Score')
    # This script loads saved_models/best_model_text_only.bin (see args.gcb_text_weights),
    # so the title must say text-only. It read "GraphCodeBERT + DFG" until 2026-09-02,
    # which made results/test5_per_source_bar.png contradict PAPER.md 3.5.
    ax.set_title('Test Set Performance by Source (GraphCodeBERT text-only)')
    ax.set_xticks(x)
    ax.set_xticklabels([results[s]['label'] for s in sources], rotation=15, ha='right')
    ax.set_ylim(0, 1.15)
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig('/kaggle/working/test5_per_source_bar.png', dpi=300)
    print("Bar chart saved → /kaggle/working/test5_per_source_bar.png")
