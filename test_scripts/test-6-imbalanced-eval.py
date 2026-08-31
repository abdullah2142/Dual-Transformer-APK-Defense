!pip install torch transformers tree_sitter==0.21.3 scikit-learn matplotlib -q

import os, json, random, math, hashlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from torch.utils.data import DataLoader, Dataset
from transformers import RobertaConfig, RobertaModel, AutoTokenizer
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, average_precision_score,
    confusion_matrix, classification_report
)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from tqdm import tqdm
from collections import defaultdict

print('Imports OK')
print(f'CUDA: {torch.cuda.is_available()}')

# ─── CONFIGURATION ────────────────────────────────────────────
class Args:
    train_file       = '/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl'
    # UniXcoder text-only -- the configuration scanner-pipeline.ipynb runs.
    #
    # test-6, the scanner and test-9 form ONE story: the operating point, the
    # sweep that justifies it, and the behaviour on real APKs. They must agree
    # on the model, or the threshold is calibrated on one and deployed on
    # another. The rest of the study (tests 2, 3, 4, 7) need not match -- they
    # answer corpus questions, not deployment ones.
    #
    # NOT a claim that UniXcoder is best: Table 1's top three sit inside the
    # +-0.10% seed-noise floor and PAPER.md 3.1 identifies no best model. The
    # pipeline is the contribution and is agnostic to the classifier.
    unixcoder_text_weights = '' # leave BLANK - resolver finds saved_models_unixcoder/best_model_text_only.bin
    model_name_or_path     = 'microsoft/unixcoder-base'

    # 384: unixcoder-text-only.ipynb trains at 384. It was 512 while this
    # evaluated GraphCodeBERT text-only, which trains at 512. Always match the
    # checkpoint -- see PAPER.md 4.3 finding 4.
    code_length      = 384
    data_flow_length = 128
    eval_batch_size  = 32
    seed             = 42
    
    test_ratio       = 0.10
    val_ratio        = 0.08
    
    target_malicious_ratio = 0.10   # 10% malicious, 90% safe
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
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

args.unixcoder_text_weights = resolve('UniXcoder text-only', 'saved_models_unixcoder/best_model_text_only.bin', override=args.unixcoder_text_weights or None)

# 0.45, matching what scanner-pipeline.ipynb actually deploys.
#
# NOT the F1 optimum. The 2026-08-30 sweep puts that at 0.90 (F1=0.7347), and
# we deliberately do not use it: F1 weights precision and recall equally, but a
# false negative ships a vulnerability while a false positive costs an analyst
# a few minutes. At 0.90 the scanner would miss 22% of vulnerabilities
# (recall 77.66%, FN 233) to halve its alert volume. At 0.45 recall is 88.21%
# at 10.32% FPR. See PAPER.md 6.7.
#
# WARNING: every figure in the paragraph above -- the 0.90 peak, 88.21% recall,
# 10.32% FPR -- came from the GraphCodeBERT text-only sweep. They will differ
# for UniXcoder. Re-read them off THIS run's sweep before quoting PAPER.md 6.7,
# and re-check that 0.45 is still the operating point you want.
OPT_THRESHOLD = 0.45

def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if args.n_gpu > 0: torch.cuda.manual_seed_all(s)
set_seed(args.seed)

print(f'Device: {args.device}')
print(f'Threshold: {OPT_THRESHOLD}')
print(f'Target ratio: {args.target_malicious_ratio*100:.0f}% malicious')

# ─── MODEL DEFINITIONS ───────────────────────
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

class TextModel(nn.Module):
    def __init__(self, encoder, config):
        super().__init__()
        self.encoder = encoder
        self.config = config
        self.dropout = nn.Dropout(config.hidden_dropout_prob)
        self.classifier = nn.Linear(config.hidden_size, 2)

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)[0]
        logits = self.classifier(self.dropout(outputs[:, 0, :]))
        prob = F.softmax(logits, dim=-1)

        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(logits, labels)
            return loss, prob
        return prob

# ─── DATASET CLASSES ─────────────────────────
class TextDataset(Dataset):
    def __init__(self, tokenizer, args, file_path, indices=None):
        self.args = args
        self.tokenizer = tokenizer
        self.total_len = args.code_length + args.data_flow_length
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        self.lines = [all_lines[i] for i in indices] if indices is not None else all_lines
            
    def __len__(self): return len(self.lines)

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
    def __init__(self, tokenizer, args, file_path, indices=None):
        self.tokenizer = tokenizer
        self.args = args
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        self.lines = [all_lines[i] for i in indices] if indices is not None else all_lines

    def __len__(self): return len(self.lines)

    def __getitem__(self, idx):
        entry = json.loads(self.lines[idx])
        code = entry.get('code', '')
        label = int(entry.get('label', 0)) if entry.get('label') is not None else 0

        tok = self.tokenizer(
            code, 
            max_length=self.args.code_length,
            truncation=True,
            padding='max_length'
        )
        return {
            'input_ids': torch.tensor(tok['input_ids'], dtype=torch.long),
            'attention_mask': torch.tensor(tok['attention_mask'], dtype=torch.long),
            'label': torch.tensor(label, dtype=torch.long)
        }

# ─── SPLIT (matches training) + DUPLICATE FILTER ──────────────────────────────
# See REMEDIATION_PLAN.md §5.1.
#
# CRITICAL: this file previously recovered the source from the filename prefix
# and grouped by it before splitting. The training notebooks did NOT (their
# infer_source finds no source key in this corpus, so every entry resolved to
# "unknown" and the split became a single random shuffle). That mismatch put
# 89.9% of this script's "test" set inside the training data.

def infer_source(entry):
    """Verbatim from the training notebooks. Do NOT add a filename fallback."""
    for key in ("source", "dataset", "origin", "project"):
        val = entry.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return "unknown"

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
            report_sources.append(str(e.get('filename', '')).split('_')[0] or 'unknown')
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
_train_idx, _val_idx, test_indices, report_sources = get_split_indices(
    args.train_file, test_ratio=args.test_ratio, val_ratio=args.val_ratio, seed=args.seed)
print(f"Clean test samples: {len(test_indices):,}")

# ─── LOAD MODEL ───────────────────────────────────────────────
# Single model: UniXcoder text-only -- the configuration the scanner runs
# (PAPER.md 5.5), which is what a DEPLOYMENT table must describe.
#
# Previously this evaluated GraphCodeBERT+DFG plus a 50/50
# probability-average "ensemble" with CodeBERT. Both were dropped:
#   * GCB+DFG (88.5600%) is the weaker variant of the middle backbone, so
#     characterising deployment with it contradicts the paper's own finding
#     that DFG does not help. PAPER_TODO.md:86 already flagged this.
#   * The ensemble was never defined in any document, and after the CodeBERT
#     retrain its partner scores 88.5427% - statistically indistinguishable
#     from GCB+DFG, so it averaged two equivalent non-best models.
if not args.unixcoder_text_weights or not os.path.exists(args.unixcoder_text_weights):
    print("Please set args.unixcoder_text_weights")
    model_a = None
else:
    print('Loading UniXcoder (text-only)...')
    cfg_a = RobertaConfig.from_pretrained(args.model_name_or_path)
    cfg_a.num_labels = 2
    tok_a = AutoTokenizer.from_pretrained(args.model_name_or_path, use_fast=True)
    enc_a = RobertaModel.from_pretrained(args.model_name_or_path, config=cfg_a)
    model_a = TextModel(enc_a, cfg_a).to(args.device)
    model_a.load_state_dict(torch.load(args.unixcoder_text_weights, map_location=args.device))
    model_a.eval()
    print('  ✓ Model loaded')

# ─── BUILD TEST SET ───────────────────────────────────────────
if model_a:
    print('Building test dataset...')
    test_ds_a = SimpleCodeDataset(tok_a, args, args.train_file, indices=test_indices)

# ─── RUN INFERENCE ON BALANCED SET ────────────────────────────
@torch.no_grad()
def get_probs_a(model, dataset):
    loader = DataLoader(dataset, batch_size=args.eval_batch_size, shuffle=False, num_workers=2)
    all_p, all_l = [], []
    for batch in tqdm(loader, desc='Inference'):
        inp = {k: batch[k].to(args.device) for k in ('input_ids','attention_mask')}
        pr  = model(**inp)[:, 1].cpu().numpy()
        all_p.extend(pr); all_l.extend(batch['label'].numpy())
    return np.array(all_p), np.array(all_l)

if model_a:
    probs_a, labels_bal = get_probs_a(model_a, test_ds_a)
    print('Inference complete')
    print(f'Test set  -> {len(labels_bal):,} samples, {labels_bal.mean():.4f} malicious ratio')
else:
    print("Skipping inference (no model loaded)")

# ─── CREATE IMBALANCED TEST SET ───────────────────────────────────────────────
if model_a:
    rng = np.random.default_rng(args.seed)

    safe_idx = np.where(labels_bal == 0)[0]
    mal_idx  = np.where(labels_bal == 1)[0]

    # Keep all malicious (or enough safe to hit 90% safe)
    # The paper mentions "keeping all malicious samples and randomly downsampling safe samples". 
    # But wait, there's usually around 50/50. If we keep all malicious, we'd need 9x safe, 
    # which is more than we have! So we keep all SAFE and downsample MALICIOUS. 
    # Let's check original script logic:
    n_safe       = len(safe_idx)
    n_mal_target = int(n_safe * args.target_malicious_ratio / (1 - args.target_malicious_ratio))
    n_mal_target = min(n_mal_target, len(mal_idx))
    mal_sample   = rng.choice(mal_idx, size=n_mal_target, replace=False)
    imb_idx      = np.concatenate([safe_idx, mal_sample])

    probs_a_imb  = probs_a[imb_idx]
    labels_imb   = labels_bal[imb_idx]

    print(f'\nImbalanced set -> {len(labels_imb):,} samples')
    print(f'  Malicious: {labels_imb.sum():,}  ({labels_imb.mean()*100:.1f}%)')
    print(f'  Safe:      {(labels_imb==0).sum():,}  ({(1-labels_imb.mean())*100:.1f}%)')

# ─── EVALUATION HELPER ────────────────────────────────────────
def evaluate(probs, labels, name, threshold=OPT_THRESHOLD):
    preds = (probs >= threshold).astype(int)
    acc   = accuracy_score(labels, preds)
    prec  = precision_score(labels, preds, zero_division=0)
    rec   = recall_score(labels, preds, zero_division=0)
    f1    = f1_score(labels, preds, zero_division=0)
    auc   = roc_auc_score(labels, probs)
    pr_a  = average_precision_score(labels, probs)
    cm    = confusion_matrix(labels, preds)
    fn    = cm[1, 0] if cm.shape == (2,2) else 0
    fp    = cm[0, 1] if cm.shape == (2,2) else 0
    fpr   = fp / max((cm[0,0]+cm[0,1]), 1)
    print(f'\n=== {name} (threshold={threshold}) ===')
    print(f'  Accuracy  : {acc:.4%}')
    print(f'  Precision : {prec:.4f}  (of predicted malicious, how many actually are)')
    print(f'  Recall    : {rec:.4f}  (of actual malicious, how many we caught)')
    print(f'  F1        : {f1:.4f}')
    print(f'  ROC-AUC   : {auc:.4f}')
    print(f'  PR-AUC    : {pr_a:.4f}')
    print(f'  FN        : {fn:,}  (missed malware)')
    print(f'  FP        : {fp:,}  (false alarms)')
    print(f'  FPR       : {fpr:.4f}  (false alarm rate on safe apps)')
    return dict(name=name, acc=acc, prec=prec, rec=rec, f1=f1,
                auc=auc, pr_auc=pr_a, fn=fn, fp=fp, fpr=fpr)

# ─── EVALUATE: BALANCED (original 50/50) ──────────────────────
if model_a:
    print('\n--- BALANCED (50/50) EVALUATION ---')
    res_bal_a = evaluate(probs_a, labels_bal, 'UniXcoder text-only [balanced 50/50]')

# ─── EVALUATE: IMBALANCED (90/10) ─────────────────────────────
if model_a:
    print('\n--- IMBALANCED (90% safe / 10% malicious) EVALUATION ---')
    res_imb_a = evaluate(probs_a_imb, labels_imb, 'UniXcoder text-only [imbalanced 90/10]')

# ─── THRESHOLD SENSITIVITY ON IMBALANCED SET ──────────────────
if model_a:
    print('\nThreshold sensitivity (UniXcoder text-only, imbalanced 90/10 set):')
    print(f'{"Threshold":>10} {"Precision":>10} {"Recall":>8} {"F1":>8} {"FPR":>8} {"FN":>6}')
    print('-'*55)
    # Swept 0.30-0.65 until 2026-08-30. Over that range F1 rose monotonically and
    # was still climbing at the last point, so the maximum lay outside the sweep
    # and the claim "F1 is maximised at 0.60" was unsupported by its own table.
    # Range extended to 0.95 so the optimum is actually contained.
    sweep_results = []
    sweep_rows = []
    for th in [round(0.30 + 0.05 * i, 2) for i in range(14)]:      # 0.30 .. 0.95
        p = (probs_a_imb >= th).astype(int)
        prec = precision_score(labels_imb, p, zero_division=0)
        rec  = recall_score(labels_imb,    p, zero_division=0)
        f1   = f1_score(labels_imb,        p, zero_division=0)
        cm   = confusion_matrix(labels_imb, p)
        fn   = cm[1,0] if cm.shape==(2,2) else 0
        fp   = cm[0,1] if cm.shape==(2,2) else 0
        fpr  = fp / max(cm[0,0]+cm[0,1], 1)
        line = f'{th:>10.2f} {prec:>10.4f} {rec:>8.4f} {f1:>8.4f} {fpr:>8.4f} {fn:>6,}'
        print(line)
        sweep_results.append(line)
        sweep_rows.append(dict(th=th, prec=prec, rec=rec, f1=f1, fpr=fpr, fn=int(fn)))

    # State the optimum rather than leaving it to be eyeballed.
    best = max(sweep_rows, key=lambda r: r['f1'])
    edge = best['th'] in (sweep_rows[0]['th'], sweep_rows[-1]['th'])
    print(f"\n  F1-optimal threshold: {best['th']:.2f}  "
          f"(F1={best['f1']:.4f}, recall={best['rec']:.4f}, FPR={best['fpr']:.4f}, FN={best['fn']:,})")
    if edge:
        print('  *** WARNING: the optimum sits at the EDGE of the swept range, so the true')
        print('      maximum may lie outside it. Widen the sweep before quoting this value.')
    else:
        print('  The optimum is interior to the swept range, so this is a real maximum.')
    print(f"  Deployed scanner threshold is 0.45 -> F1="
          f"{[r for r in sweep_rows if r['th']==0.45][0]['f1']:.4f}; "
          f"0.60 -> {[r for r in sweep_rows if r['th']==0.60][0]['f1']:.4f}")

# ─── SAVE PROBABILITIES ───────────────────────────────────────
# test-6 used to discard these, which is why every question about the decision
# threshold cost a full GPU re-run. With them saved, any future sweep is a CPU
# script over a small file -- same reasoning as results/predictions/ for test-8.
if model_a:
    np.save('/kaggle/working/test6_probs_balanced.npy', probs_a)
    np.save('/kaggle/working/test6_labels_balanced.npy', labels_bal)
    np.save('/kaggle/working/test6_probs_imbalanced.npy', probs_a_imb)
    np.save('/kaggle/working/test6_labels_imbalanced.npy', labels_imb)
    print('\nSaved probabilities -> /kaggle/working/test6_{probs,labels}_{balanced,imbalanced}.npy')

# ─── COMPARISON BAR CHART ─────────────────────────────────────
if model_a:
    conditions = ['Balanced\n(50/50)', 'Imbalanced\n(90/10 real-world)']
    prec_vals = [res_bal_a['prec'], res_imb_a['prec']]
    rec_vals  = [res_bal_a['rec'],  res_imb_a['rec']]
    f1_vals   = [res_bal_a['f1'],   res_imb_a['f1']]
    xlabels   = ['UniXcoder\nBalanced', 'UniXcoder\nImbalanced']

    x = np.arange(len(xlabels))
    w = 0.26
    fig, ax = plt.subplots(figsize=(11, 6))
    b1 = ax.bar(x - w,   prec_vals, w, label='Precision', color='#4C72B0', alpha=0.88)
    b2 = ax.bar(x,       rec_vals,  w, label='Recall',    color='#55A868', alpha=0.88)
    b3 = ax.bar(x + w,   f1_vals,   w, label='F1',        color='#DD8452', alpha=0.88)

    for bars in [b1, b2, b3]:
        for bar in bars:
            ax.annotate(f'{bar.get_height():.3f}',
                        xy=(bar.get_x()+bar.get_width()/2, bar.get_height()),
                        xytext=(0,4), textcoords='offset points',
                        ha='center', va='bottom', fontsize=9)
    ax.set_ylim(0.0, 1.12)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels, fontsize=10)
    ax.set_ylabel('Score', fontsize=13)
    ax.set_title(f'Precision / Recall / F1: Balanced vs Imbalanced (threshold={OPT_THRESHOLD})', fontsize=13)
    ax.legend(fontsize=11)
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    
    os.makedirs('/kaggle/working', exist_ok=True)
    out_img = '/kaggle/working/test7_precision_recall_bar.png'
    fig.savefig(out_img, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'Saved -> {out_img}')

# ─── SAVE TEXT RESULTS ────────────────────────────────────────
if model_a:
    out_txt = '/kaggle/working/test7_imbalanced_results.txt'
    with open(out_txt, 'w') as fh:
        fh.write('Test 7: Imbalanced Class Evaluation\n')
        fh.write('='*60 + '\n')
        fh.write('Model    : UniXcoder text-only (the configuration the scanner runs, PAPER.md 5.5)\n')
        fh.write(f'Test set : {len(test_indices):,} samples (duplicate-filtered)\n')
        fh.write(f'Threshold used: {OPT_THRESHOLD}\n')
        fh.write(f'Imbalanced ratio: 90% safe / 10% malicious\n\n')
        for res in [res_bal_a, res_imb_a]:
            fh.write(f"\n{res['name']}\n")
            for k in ['acc','prec','rec','f1','auc','pr_auc','fn','fp','fpr']:
                if isinstance(res[k], float):
                    fh.write(f'  {k:<8}: {res[k]:.4f}\n')
                else:
                    fh.write(f'  {k:<8}: {res[k]:,}\n')
        
        fh.write(f'\n\nF1-optimal threshold: {best["th"]:.2f}  (F1={best["f1"]:.4f}, '
                 f'recall={best["rec"]:.4f}, FPR={best["fpr"]:.4f}, FN={best["fn"]:,})\n')
        if edge:
            fh.write('WARNING: optimum at the edge of the swept range -- widen before quoting.\n')
        fh.write('\n\nThreshold Sensitivity Sweep (UniXcoder text-only, imbalanced 90/10):\n')
        fh.write(f'{"Threshold":>10} {"Precision":>10} {"Recall":>8} {"F1":>8} {"FPR":>8} {"FN":>6}\n')
        fh.write('-'*55 + '\n')
        for line in sweep_results:
            fh.write(line + '\n')
    print(f'Saved -> {out_txt}')
