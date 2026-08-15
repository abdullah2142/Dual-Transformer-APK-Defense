!pip install torch transformers tree_sitter==0.21.3 scikit-learn matplotlib statsmodels pandas -q

# =============================================================================
#  TEST 2 + TEST 8  (combined, run top to bottom in one Kaggle notebook)
# =============================================================================
#  Test 2 scores all six checkpoints, writes six test_probs_*.npy plus
#  test_labels.npy into /kaggle/working, and emits the ROC/PR figure and
#  test2_auc_results.txt.
#
#  Test 8 then reads those .npy straight out of /kaggle/working -- its
#  SEARCH_ROOTS covers it -- and runs McNemar's test. It is CPU-only and takes
#  seconds, so running it inside the GPU session costs essentially nothing and
#  saves shuttling the .npy between notebooks.
#
#  INPUTS   the dataset JSONL, plus the six training runs attached via
#           "+ Add Input -> Notebooks". Checkpoints resolve themselves and
#           print the path they found -- check those lines before trusting any
#           number.
#
#  SANITY   after Test 2, CodeBERT should read about 88.4%, NOT 93.4%.
#           93.4% means the OLD leaked checkpoints are attached.
#           Test 2 must also print "-> 18,541 clean test entries".
#
#  test-8's `results` was renamed to `mcnemar_results` here; test-2 uses
#  `results` for its own per-model dict.
# =============================================================================

import os, json, random, math, hashlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from torch.utils.data import DataLoader, Dataset, Subset
from transformers import RobertaConfig, RobertaModel, AutoTokenizer
from sklearn.metrics import (
    roc_curve, auc,
    precision_recall_curve, average_precision_score,
    accuracy_score, classification_report
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
    train_file = "/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl"
    
    # Models with DFG
    gcb_dfg_weights       = "" # TODO: /kaggle/input/<your-dataset>/saved_models/best_model.bin
    codebert_dfg_weights  = "" # TODO: /kaggle/input/<your-dataset>/saved_models_codebert_dfg/best_model.bin   (NEW - from retrain)
    unixcoder_dfg_weights = "" # TODO: /kaggle/input/<your-dataset>/saved_models_unixcoder_dfg/model_unixcoder_dfg_best.bin
    
    # Text-only Models
    gcb_text_weights       = "" # TODO: /kaggle/input/<your-dataset>/saved_models/best_model_text_only.bin
    codebert_text_weights  = "" # TODO: /kaggle/input/<your-dataset>/saved_models_codebert_text/best_model.bin  (NEW - from retrain)
    unixcoder_text_weights = "" # TODO: /kaggle/input/<your-dataset>/saved_models_unixcoder/best_model_text_only.bin

    code_length       = 384
    data_flow_length  = 128
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

args.gcb_dfg_weights = resolve('GCB + DFG', 'saved_models/best_model.bin', override=args.gcb_dfg_weights or None)
args.gcb_text_weights = resolve('GCB text-only', 'saved_models/best_model_text_only.bin', override=args.gcb_text_weights or None)
args.codebert_dfg_weights = resolve('CodeBERT + DFG', 'saved_models_codebert_dfg/best_model.bin', override=args.codebert_dfg_weights or None)
args.codebert_text_weights = resolve('CodeBERT text', 'saved_models_codebert_text/best_model.bin', override=args.codebert_text_weights or None)
args.unixcoder_dfg_weights = resolve('UniXcoder + DFG', 'saved_models_unixcoder_dfg/model_unixcoder_dfg_best.bin', override=args.unixcoder_dfg_weights or None)
args.unixcoder_text_weights = resolve('UniXcoder text', 'saved_models_unixcoder/best_model_text_only.bin', override=args.unixcoder_text_weights or None)

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if args.n_gpu > 0:
        torch.cuda.manual_seed_all(seed)

set_seed(args.seed)
print(f"Device: {args.device}")

# ─── MODEL CLASSES ────────────────────────────────────────────────────────────
class DFGModel(nn.Module):   
    def __init__(self, encoder, config):
        super(DFGModel, self).__init__()
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
        )
        sequence_output = encoder_outputs[0]
        logits = self.classifier(self.dropout(sequence_output[:, 0, :]))
        prob = F.softmax(logits, dim=-1)

        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(logits, labels)
            return loss, prob
        return prob

class TextModel(nn.Module):
    def __init__(self, encoder, config):
        super(TextModel, self).__init__()
        self.encoder = encoder
        self.config = config
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, 2)

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits = self.classifier(self.dropout(sequence_output[:, 0, :]))
        prob = F.softmax(logits, dim=-1)

        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(logits, labels)
            return loss, prob
        return prob

# ─── DATASET CLASSES ──────────────────────────────────────────────────────────
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

class SimpleCodeDataset(Dataset):
    def __init__(self, tokenizer, args, file_path):
        self.tokenizer = tokenizer
        self.args = args
        with open(file_path, 'r', encoding='utf-8') as f:
            self.lines = f.readlines()

    def __len__(self): return len(self.lines)

    def __getitem__(self, idx):
        entry = json.loads(self.lines[idx])
        code = entry.get('code', '')
        label = int(entry.get('label', 0)) if entry.get('label') is not None else 0
        tok = self.tokenizer(
            code, max_length=self.args.code_length,
            truncation=True, padding='max_length'
        )
        return {
            'input_ids': torch.tensor(tok['input_ids'], dtype=torch.long),
            'attention_mask': torch.tensor(tok['attention_mask'], dtype=torch.long),
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

def get_split_indices(filepath, test_ratio=0.10, val_ratio=0.08, seed=42):
    """Returns (train, val, test, code_hashes). Reproduces the training
    partition exactly (163,967/15,997/19,996). The duplicate filter is applied
    separately, AFTER the split guard — see below."""
    srcs, hashes = [], []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            e = json.loads(line)
            srcs.append(infer_source(e))
            hashes.append(hashlib.md5(str(e.get('code', '')).encode('utf-8', 'ignore')).hexdigest())
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

    return sorted(train_indices), sorted(val_indices), sorted(test_indices), hashes

print("Building split (matches training partition)...")
train_indices, val_indices, test_indices, code_hashes = get_split_indices(args.train_file)
print(f"Split: train={len(train_indices):,} val={len(val_indices):,} "
      f"test={len(test_indices):,}")

# ─── SPLIT GUARD ──────────────────────────────────────────────────────────────
# Asserts that the partition rebuilt here is byte-for-byte the one the training
# notebooks used. This is the check that would have caught the original CodeBERT
# bug (see SPLIT_MISMATCH.md), so it is fail-closed: a missing file is an error,
# not a silent skip.
#
# The training notebooks write test_indices.npy into their own output dirs
# ('saved_models_codebert_text/', 'saved_models_codebert_dfg/'), which you then
# upload as a Kaggle dataset. Rather than hardcode one upload path, search for
# the file so it is found wherever it was attached.
import glob as _glob

_guard_candidates = sorted(set(
    _glob.glob('/kaggle/input/**/test_indices.npy', recursive=True) +
    _glob.glob('/kaggle/working/**/test_indices.npy', recursive=True) +
    _glob.glob('/kaggle/input/**/split_indices.json', recursive=True)
))

assert _guard_candidates, (
    "Split guard file missing. Upload the training run's output (which contains "
    "test_indices.npy, e.g. saved_models_codebert_text/test_indices.npy) as a "
    "Kaggle dataset and attach it to this notebook. Searched /kaggle/input and "
    "/kaggle/working recursively."
)

for _gp in _guard_candidates:
    if _gp.endswith('.npy'):
        _saved = np.load(_gp)
    else:
        with open(_gp, 'r') as _f:
            _saved = np.array(json.load(_f).get('test_indices', []))
    assert np.array_equal(test_indices, _saved), (
        f"Split mismatch against {_gp}: the evaluation partition differs from "
        f"the training partition. Do NOT proceed - this is the exact bug the "
        f"guard exists to catch."
    )
    print(f"Split guard passed: {_gp} ({len(_saved):,} indices)")

# ─── DUPLICATE FILTER ─────────────────────────────────────────────────────────
# Applied AFTER the split guard on purpose: the guard compares against the
# indices the training notebooks saved, which are the full unfiltered 19,996.
# Filtering first would make the guard fail spuriously.
#
# Drops test entries whose `code` is byte-identical to a train/val entry, so the
# models are measured only on code they never saw. Training data is unchanged.
# See REMEDIATION_PLAN.md 5.1.
_seen = {code_hashes[i] for i in train_indices}
_seen.update(code_hashes[i] for i in val_indices)
_before = len(test_indices)
test_indices = [i for i in test_indices if code_hashes[i] not in _seen]
_dropped = _before - len(test_indices)
print(f"Duplicate filter: dropped {_dropped:,} ({_dropped/_before:.2%}) test entries "
      f"byte-identical to a train/val sample -> {len(test_indices):,} clean")

# ─── EVALUATION FUNCTION ──────────────────────────────────────────────────────
def evaluate(model, dataset, args, is_dfg=True):
    dataloader = DataLoader(dataset, batch_size=args.eval_batch_size, num_workers=4, pin_memory=True)
    model.eval()
    all_probs = []
    all_labels = []

    for batch in tqdm(dataloader, desc="Evaluating"):
        input_ids = batch['input_ids'].to(args.device)
        labels = batch['label'].to(args.device)
        
        with torch.no_grad():
            if is_dfg:
                p_ids = batch['p_ids'].to(args.device)
                attn_mask = batch['attn_mask'].to(args.device)
                prob = model(input_ids=input_ids, p_ids=p_ids, attn_mask=attn_mask)
            else:
                attention_mask = batch['attention_mask'].to(args.device)
                prob = model(input_ids=input_ids, attention_mask=attention_mask)
                
        all_probs.append(prob.cpu().numpy())
        all_labels.append(labels.cpu().numpy())

    all_probs = np.concatenate(all_probs, axis=0)
    all_labels = np.concatenate(all_labels, axis=0)
    
    preds = np.argmax(all_probs, axis=1)
    acc = accuracy_score(all_labels, preds)
    
    fpr, tpr, _ = roc_curve(all_labels, all_probs[:, 1])
    roc_auc = auc(fpr, tpr)
    
    precision, recall, _ = precision_recall_curve(all_labels, all_probs[:, 1])
    pr_auc = auc(recall, precision)

    return fpr, tpr, roc_auc, recall, precision, pr_auc, acc, all_probs, all_labels

# ─── MODEL FACTORY & EXECUTION ────────────────────────────────────────────────
def load_and_evaluate(name, model_type, model_path, base_model_name, is_dfg):
    print(f"\n{'='*50}\nEvaluating {name}\n{'='*50}")
    if not model_path or not os.path.exists(model_path):
        print(f"Skipping {name} (path not found or empty: {model_path})")
        return None
        
    tokenizer = AutoTokenizer.from_pretrained(base_model_name, use_fast=True)
    config = RobertaConfig.from_pretrained(base_model_name)
    config.num_labels = 2
    encoder = RobertaModel.from_pretrained(base_model_name, config=config)
    
    if is_dfg:
        model = DFGModel(encoder, config)
        dataset = TextDataset(tokenizer, args, args.train_file)
    else:
        model = TextModel(encoder, config)
        dataset = SimpleCodeDataset(tokenizer, args, args.train_file)
        
    test_dataset = Subset(dataset, test_indices)
    
    model.load_state_dict(torch.load(model_path, map_location=args.device))
    model.to(args.device)
    
    metrics = evaluate(model, test_dataset, args, is_dfg=is_dfg)
    print(f"{name} - Acc: {metrics[6]:.4f}, ROC-AUC: {metrics[2]:.4f}, PR-AUC: {metrics[5]:.4f}")
    
    safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").lower()
    np.save(f'/kaggle/working/test_probs_{safe_name}.npy', metrics[7])
    if not os.path.exists('/kaggle/working/test_labels.npy'):
        np.save('/kaggle/working/test_labels.npy', metrics[8])
    
    # Cleanup to save RAM
    del model, encoder, dataset, test_dataset
    torch.cuda.empty_cache()
    
    return metrics

models_to_run = [
    ("GraphCodeBERT (DFG)", "microsoft/graphcodebert-base", args.gcb_dfg_weights, True),
    ("GraphCodeBERT (Text)", "microsoft/graphcodebert-base", args.gcb_text_weights, False),
    ("CodeBERT (DFG)", "microsoft/codebert-base", args.codebert_dfg_weights, True),
    ("CodeBERT (Text)", "microsoft/codebert-base", args.codebert_text_weights, False),
    ("UniXcoder (DFG)", "microsoft/unixcoder-base", args.unixcoder_dfg_weights, True),
    ("UniXcoder (Text)", "microsoft/unixcoder-base", args.unixcoder_text_weights, False),
]

results = {}
for name, base_name, path, is_dfg in models_to_run:
    metrics = load_and_evaluate(name, "roberta", path, base_name, is_dfg)
    if metrics:
        results[name] = metrics

# ─── PLOT ROC AND PR CURVES ───────────────────────────────────────────────────
if not results:
    print("No results to plot. Please configure the model weights paths.")
else:
    colors = {
        "GraphCodeBERT (DFG)": "blue",
        "GraphCodeBERT (Text)": "cornflowerblue",
        "CodeBERT (DFG)": "green",
        "CodeBERT (Text)": "limegreen",
        "UniXcoder (DFG)": "red",
        "UniXcoder (Text)": "salmon",
    }
    
    linestyles = {
        "GraphCodeBERT (DFG)": "-",
        "GraphCodeBERT (Text)": "--",
        "CodeBERT (DFG)": "-",
        "CodeBERT (Text)": "--",
        "UniXcoder (DFG)": "-",
        "UniXcoder (Text)": "--",
    }

    plt.figure(figsize=(16, 7))

    # ROC Curve
    plt.subplot(1, 2, 1)
    for name, metrics in results.items():
        fpr, tpr, roc_auc, *_ = metrics   # evaluate() returns 9; absorb the rest
        plt.plot(fpr, tpr, color=colors[name], linestyle=linestyles[name],
                 lw=2, label=f'{name} (AUC = {roc_auc:.4f})')

    plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle=':')
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('False Positive Rate', fontsize=12)
    plt.ylabel('True Positive Rate', fontsize=12)
    plt.title('Receiver Operating Characteristic (ROC)', fontsize=14)
    plt.legend(loc="lower right", fontsize=10)
    plt.grid(alpha=0.3)

    # PR Curve
    plt.subplot(1, 2, 2)
    for name, metrics in results.items():
        _, _, _, recall, precision, pr_auc, *_ = metrics   # evaluate() returns 9
        plt.plot(recall, precision, color=colors[name], linestyle=linestyles[name],
                 lw=2, label=f'{name} (AUC = {pr_auc:.4f})')

    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel('Recall', fontsize=12)
    plt.ylabel('Precision', fontsize=12)
    plt.title('Precision-Recall Curve', fontsize=14)
    plt.legend(loc="lower left", fontsize=10)
    plt.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig('/kaggle/working/test2_roc_pr_curves.png', dpi=300)
    print("Saved plots to /kaggle/working/test2_roc_pr_curves.png")

    # ─── RESULTS FILE ─────────────────────────────────────────────────────────
    # This file is the ONLY consistent source for Table 1: every model here is
    # scored on the same duplicate-filtered test set. Do NOT mix these figures
    # with the per-model numbers each training notebook prints - those are on the
    # unfiltered 19,996 and the arithmetic (acc = 1 - (FN+FP)/N) will not
    # reconcile. FN/FP are emitted here for exactly that reason.
    with open('/kaggle/working/test2_auc_results.txt', 'w') as f:
        f.write("=== Test 2: ROC-AUC and PR-AUC Results ===\n")
        f.write(f"Test set: {len(test_indices):,} samples "
                f"(duplicate-filtered; see REMEDIATION_PLAN.md 5.1)\n")
        f.write("Threshold: argmax (0.5)\n\n")

        # Machine-readable line kept first for downstream parsers (test-5 reads
        # 'Acc=' / 'ROC-AUC=' / 'PR-AUC=' from these lines).
        for name, metrics in results.items():
            f.write(f"{name}: Acc={metrics[6]:.4f}, ROC-AUC={metrics[2]:.4f}, "
                    f"PR-AUC={metrics[5]:.4f}\n")

        f.write("\n\n=== Table 1 (paper-ready) ===\n")
        f.write(f'{"Model":<24}{"Accuracy":>11}{"ROC-AUC":>10}{"PR-AUC":>9}'
                f'{"FN":>8}{"FP":>8}{"N":>9}\n')
        f.write('-' * 79 + '\n')
        for name, metrics in results.items():
            probs, labels_arr = metrics[7], metrics[8]
            preds = np.argmax(probs, axis=1)
            fn = int(np.sum((labels_arr == 1) & (preds == 0)))
            fp = int(np.sum((labels_arr == 0) & (preds == 1)))
            n  = int(len(labels_arr))
            f.write(f'{name:<24}{metrics[6]*100:>10.4f}%{metrics[2]:>10.4f}'
                    f'{metrics[5]:>9.4f}{fn:>8,}{fp:>8,}{n:>9,}\n')
            # cross-check: accuracy must equal 1 - (FN+FP)/N
            assert abs((1.0 - (fn + fp) / n) - metrics[6]) < 1e-9, \
                f"{name}: FN/FP do not reconcile with accuracy"
    print("Saved metrics to /kaggle/working/test2_auc_results.txt")

# =============================================================================
#  TEST 8 -- McNemar's test on the .npy Test 2 just wrote
# =============================================================================

import os
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import mcnemar

SEARCH_ROOTS = [Path('/kaggle/working'), Path('/kaggle/input')]

def find_candidates(names):
    hits = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for name in names:
            direct = root / name
            if direct.exists():
                hits.append(direct)
            hits.extend(root.rglob(name))
    unique = []
    seen = set()
    for path in hits:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique

def load_first(label, names):
    matches = find_candidates(names)
    if not matches:
        raise FileNotFoundError(f'Missing {label}. Looked for: {names}')
    path = matches[0]
    arr = np.load(path)
    print(f'{label:<24} -> {path}')
    print(f'  shape={arr.shape} dtype={arr.dtype}')
    return arr, path

probs_gcb_dfg, _ = load_first('GCB + DFG', ['test_probs_graphcodebert_dfg.npy'])
probs_gcb_text, _ = load_first('GCB Text', ['test_probs_graphcodebert_text.npy'])
probs_codebert_dfg, _ = load_first('CodeBERT + DFG', ['test_probs_codebert_dfg.npy'])
probs_codebert_text, _ = load_first('CodeBERT Text', ['test_probs_codebert_text.npy'])
probs_unix_dfg, _ = load_first('UniXcoder + DFG', ['test_probs_unixcoder_dfg.npy'])
probs_unix_text, _ = load_first('UniXcoder Text', ['test_probs_unixcoder_text.npy'])
labels, _ = load_first('Shared labels', ['test_labels.npy'])

assert len(labels) == len(probs_gcb_dfg) == len(probs_gcb_text) == len(probs_codebert_dfg) == len(probs_codebert_text) == len(probs_unix_dfg) == len(probs_unix_text)
print(f'\nLoaded {len(labels):,} shared test samples.')

def to_preds(probs, threshold=0.5):
    return (probs[:, 1] >= threshold).astype(int)

preds_gcb_dfg = to_preds(probs_gcb_dfg)
preds_gcb_text = to_preds(probs_gcb_text)
preds_codebert_dfg = to_preds(probs_codebert_dfg)
preds_codebert_text = to_preds(probs_codebert_text)
preds_unix_dfg = to_preds(probs_unix_dfg)
preds_unix_text = to_preds(probs_unix_text)

def run_mcnemar(preds_a, preds_b, labels, name_a, name_b):
    correct_a = (preds_a == labels)
    correct_b = (preds_b == labels)
    b = int(np.sum(correct_a & ~correct_b))
    c = int(np.sum(~correct_a & correct_b))
    result = mcnemar([[0, b], [c, 0]], exact=False, correction=True)
    acc_a = np.mean(preds_a == labels)
    acc_b = np.mean(preds_b == labels)
    sig_msg = 'NOT significant (p>0.05)' if result.pvalue > 0.05 else 'SIGNIFICANT (p<=0.05)'
    print(f'\n{name_a} vs {name_b}')
    print(f'  Acc A: {acc_a:.4%}   Acc B: {acc_b:.4%}   Delta: {acc_a - acc_b:+.4%}')
    print(f'  b (A correct, B wrong): {b}')
    print(f'  c (A wrong, B correct): {c}')
    print(f'  McNemar statistic: {result.statistic:.4f}')
    print(f'  p-value: {result.pvalue:.4f}  {sig_msg}')
    return {
        'comparison': f'{name_a} vs {name_b}',
        'acc_a': acc_a,
        'acc_b': acc_b,
        'delta': acc_a - acc_b,
        'b': b,
        'c': c,
        'statistic': float(result.statistic),
        'pvalue': float(result.pvalue),
        'significant': bool(result.pvalue <= 0.05),
    }

mcnemar_results = []
mcnemar_results.append(run_mcnemar(preds_gcb_dfg, preds_gcb_text, labels, 'GraphCodeBERT+DFG', 'GraphCodeBERT Text'))
mcnemar_results.append(run_mcnemar(preds_codebert_dfg, preds_codebert_text, labels, 'CodeBERT+DFG', 'CodeBERT Text'))
mcnemar_results.append(run_mcnemar(preds_unix_dfg, preds_unix_text, labels, 'UniXcoder+DFG', 'UniXcoder Text'))
mcnemar_results.append(run_mcnemar(preds_gcb_dfg, preds_codebert_dfg, labels, 'GraphCodeBERT+DFG', 'CodeBERT+DFG'))
mcnemar_results.append(run_mcnemar(preds_gcb_dfg, preds_unix_dfg, labels, 'GraphCodeBERT+DFG', 'UniXcoder+DFG'))

df = pd.DataFrame(mcnemar_results)
print('\n' + '=' * 70)
print('SIGNIFICANCE TESTING SUMMARY')
print('=' * 70)
print(df[['comparison', 'delta', 'pvalue', 'significant']].to_string(index=False))

out_path = '/kaggle/working/test8_significance_results.txt'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write('Statistical Significance Testing - McNemar\'s Test\n')
    f.write('=' * 60 + '\n')
    f.write(df.to_string(index=False))
    f.write('\n\nInterpretation:\n')
    f.write('p > 0.05 = differences are NOT statistically significant\n')
    f.write('p <= 0.05 = differences ARE statistically significant\n')
    sig_rows = df[df['significant']]
    if len(sig_rows) == 0:
        f.write('\nNo significant pairwise differences were detected at alpha = 0.05.\n')
    else:
        f.write('\nSignificant comparisons (must be reported explicitly):\n')
        for _, row in sig_rows.iterrows():
            f.write(f"  - {row['comparison']} (p={row['pvalue']:.4f}, delta={row['delta']:+.4%})\n")
print(f'\nSaved -> {out_path}')
