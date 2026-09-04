!pip install torch transformers scikit-learn -q

# ==============================================================================
# Test 7b: Qualitative false-negative analysis using THE DEPLOYED SCANNER MODEL
# ==============================================================================
#
# WHY THIS EXISTS
# ---------------
# test-7-qualitative-analysis.py profiles GraphCodeBERT + DFG. That is the right
# model for explaining why DFG does not help (PAPER.md Part 7), but it is NOT
# the model the scanner ships. Per D6/§5.6 the scanner runs UniXcoder text-only,
# so Section 8's failure patterns currently describe a model we do not deploy.
# This script closes that gap: same partition, same output format, same
# hand-classification workflow -- different model.
#
# EXACTLY MATCHES THE SCANNER (test_scripts/scanner-pipeline.ipynb):
#   backbone      microsoft/unixcoder-base
#   architecture  SimpleModel: encoder -> CLS -> dropout -> Linear(hidden, 2)
#   checkpoint    saved_models_unixcoder/best_model_text_only.bin
#   code_length   384, truncation=True, padding='max_length'
#   threshold     0.45
#   text-only     no DFG tensor is built or passed
#
# DELIBERATE DIFFERENCE FROM THE SCANNER
# --------------------------------------
# The scanner wraps raw decompiled APK methods in `public class DummyClass {...}`
# because methods extracted from an APK have no enclosing class. Corpus records
# already carry that wrapper where the builder added it, so this script feeds
# entry['code'] through unchanged -- same as test-2/4/6/7. Re-wrapping here would
# double-wrap and make the numbers incomparable with every other test.
#
# THRESHOLD
# ---------
# test-7 defines a false negative by argmax, i.e. p_vuln < 0.50. The scanner
# deploys at 0.45. Both are reported: 0.45 is primary (it is what the deployed
# system does), 0.50 is printed alongside so the count is directly comparable
# with Part 7's 1,054. A lower threshold flags more as vulnerable, so the 0.45
# FN set is a subset of the 0.50 one.
#
# ON KAGGLE
#   + Add Input -> Notebooks -> attach `unixcoder-text-only` (the training run)
#   + Add Input -> Datasets  -> attach the dfgdataset2 corpus
#
# OUTPUTS (to /kaggle/working)
#   test7b_qualitative_scanner_results.txt   full code of the top 20, for hand-classification
#   test7b_false_negatives.json              every FN with corpus index + flags
#   test7b_probs_unixcoder_text.npy          probabilities, aligned to the filtered test set
# ==============================================================================

import os
import re
import json
import math
import random
import hashlib
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, SequentialSampler, Dataset
from transformers import AutoTokenizer, RobertaConfig, RobertaModel
from tqdm.auto import tqdm
from collections import defaultdict, Counter

print("Imports complete.")


class Args:
    train_file = '/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl'
    unixcoder_text_weights = ''      # blank => resolver finds it; see below
    backbone = "microsoft/unixcoder-base"
    code_length = 384                # matches the scanner AND unixcoder-text-only.ipynb
    threshold = 0.45                 # matches the deployed scanner
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_batch_size = 32
    seed = 42
    test_ratio = 0.10
    val_ratio = 0.08                 # so the duplicate filter can exclude val too


args = Args()

# ─── CHECKPOINT RESOLVER ──────────────────────────────────────────────────────
# Canonical copy: test_scripts/resolve_checkpoints.py
# Matches on '<dir>/<file>', never filename alone -- three checkpoints in this
# project are called best_model.bin. Zero matches is an error; two or more is
# also an error. It never guesses. Setting the Args field by hand overrides it.
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
            f'"+ Add Input -> Notebooks" and attach unixcoder-text-only. '
            f"Debug with: import glob; print(glob.glob('/kaggle/input/**/*.bin', recursive=True))")
    mb = os.path.getsize(hits[0]) / 1e6
    print(f'  {label:24s} -> {hits[0]}  ({mb:.0f} MB)')
    if mb < 100:
        print(f'  {"":24s}    WARNING: {mb:.0f} MB is small for a checkpoint (expect ~499 MB).')
    return hits[0]


print('Resolving checkpoints:')
args.unixcoder_text_weights = resolve(
    'UniXcoder text', 'saved_models_unixcoder/best_model_text_only.bin',
    override=args.unixcoder_text_weights or None)


def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if torch.cuda.device_count() > 0:
        torch.cuda.manual_seed_all(s)


set_seed(args.seed)

# ─── SPLIT (matches training) + DUPLICATE FILTER ──────────────────────────────
# Verbatim from test_scripts/split_and_filter.py. infer_source deliberately has
# NO filename fallback: the training notebooks had none, so every entry resolves
# to "unknown" and the split is a single shuffle. Adding a fallback here would
# re-create the 89.9% leak that PAPER.md §10.4 documents.


def infer_source(entry):
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

    train_indices, val_indices = sorted(train_indices), sorted(val_indices)
    test_indices = sorted(test_indices)
    assert len(test_indices) == target_test
    assert set(train_indices).isdisjoint(test_indices)
    assert set(val_indices).isdisjoint(test_indices)
    print(f"Split: train={len(train_indices):,} val={len(val_indices):,} test={len(test_indices):,}")

    if drop_duplicate_test:
        seen = {hashes[i] for i in train_indices}
        seen.update(hashes[i] for i in val_indices)
        before = len(test_indices)
        test_indices = [i for i in test_indices if hashes[i] not in seen]
        dropped = before - len(test_indices)
        print(f"Duplicate filter: dropped {dropped:,} ({dropped/before:.2%}) test entries "
              f"byte-identical to a train/val sample -> {len(test_indices):,} clean")

    return train_indices, val_indices, test_indices


print("Building split (matches training partition) ...")
_train_idx, _val_idx, test_indices = get_split_indices(
    args.train_file, test_ratio=args.test_ratio, val_ratio=args.val_ratio, seed=args.seed)

# Fail closed: every other script on this partition reports 18,541.
assert len(test_indices) == 18541, (
    f"Expected 18,541 filtered test samples, got {len(test_indices):,}. "
    f"The partition does not match test-2/4/6/7 -- do not compare these results.")
print(f"Clean test samples: {len(test_indices):,}  (matches test-2/4/6/7)")


# ─── MODEL: verbatim from scanner-pipeline.ipynb ──────────────────────────────
class SimpleModel(nn.Module):
    def __init__(self, encoder, config):
        super(SimpleModel, self).__init__()
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
            loss_fct = nn.CrossEntropyLoss()
            return loss_fct(logits, labels), prob
        return prob


# ─── DATASET: text-only, no DFG tensor built at all ───────────────────────────
class SimpleCodeDataset(Dataset):
    def __init__(self, tokenizer, args, file_path, indices):
        self.args = args
        self.tokenizer = tokenizer
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        self.lines = [all_lines[i] for i in indices]
        self.original_indices = list(indices)

    def __len__(self):
        return len(self.lines)

    def __getitem__(self, item):
        entry = json.loads(self.lines[item])
        code = entry.get('code', '')
        label = int(entry.get('label', 0)) if entry.get('label') is not None else 0
        enc = self.tokenizer(
            code,
            max_length=self.args.code_length,
            truncation=True,
            padding='max_length',
            return_tensors='pt',
        )
        return {
            'input_ids': enc['input_ids'].squeeze(0),
            'attention_mask': enc['attention_mask'].squeeze(0),
            'label': torch.tensor(label, dtype=torch.long),
            'index': item,
        }


print(f"Loading tokenizer + dataset ({args.backbone}) ...")
tokenizer = AutoTokenizer.from_pretrained(args.backbone, use_fast=True)
test_ds = SimpleCodeDataset(tokenizer, args, args.train_file, test_indices)
print(f"Test samples isolated: {len(test_ds):,}")

print("Loading UniXcoder (text-only) -- the deployed scanner model ...")
config = RobertaConfig.from_pretrained(args.backbone)
config.num_labels = 2
encoder = RobertaModel.from_pretrained(args.backbone, config=config)
model = SimpleModel(encoder, config)
model.load_state_dict(torch.load(args.unixcoder_text_weights, map_location=args.device))
model.to(args.device)
model.eval()
print("  Model loaded successfully.")

loader = DataLoader(test_ds, sampler=SequentialSampler(test_ds),
                    batch_size=args.eval_batch_size, num_workers=2)

all_probs, all_labels, all_idx = [], [], []
print("Running inference ...")
with torch.no_grad():
    for batch in tqdm(loader, desc="Evaluating"):
        probs = model(
            input_ids=batch['input_ids'].to(args.device),
            attention_mask=batch['attention_mask'].to(args.device),
        )
        all_probs.extend(probs[:, 1].cpu().numpy())
        all_labels.extend(batch['label'].numpy())
        all_idx.extend(batch['index'].numpy())

all_probs = np.asarray(all_probs, dtype=np.float64)
all_labels = np.asarray(all_labels, dtype=np.int64)

# ─── ACCURACY AT BOTH THRESHOLDS ──────────────────────────────────────────────
# At 0.50 the rule is argmax semantics -- argmax([p0, p1]) picks class 1 only
# when p1 > p0, i.e. p1 > 0.50 -- so predicted-safe is `p <= 0.50`. Kept
# consistent between the accuracy and false-negative counts here; test-2 records
# no sample sitting exactly at 0.50, but the two must not disagree by
# construction.
pred_045 = (all_probs >= 0.45).astype(int)
pred_050 = (all_probs > 0.50).astype(int)
acc_045 = float((pred_045 == all_labels).mean())
acc_050 = float((pred_050 == all_labels).mean())
n_fn_045 = int(((all_labels == 1) & (all_probs < 0.45)).sum())
n_fn_050 = int(((all_labels == 1) & (all_probs <= 0.50)).sum())
print(f"\nAccuracy @0.45 : {acc_045*100:.4f}%   false negatives: {n_fn_045:,}")
print(f"Accuracy @0.50 : {acc_050*100:.4f}%   false negatives: {n_fn_050:,}")

# ─── PRE-REGISTERED EXPECTATION ───────────────────────────────────────────────
# These four numbers were derived before this run, from the probabilities test-2
# saved on 2026-08-20 (results/predictions/test_probs_unixcoder_text.npy) via
# test_scripts/make_test7b_from_predictions.py. This run recomputes them from the
# checkpoint. If they disagree, something loaded wrong -- do not use the output.
EXPECTED = {'acc_045': 88.3717, 'fn_045': 1154, 'acc_050': 88.3447, 'fn_050': 1217}
got = {'acc_045': round(acc_045*100, 4), 'fn_045': n_fn_045,
       'acc_050': round(acc_050*100, 4), 'fn_050': n_fn_050}
print("\nCross-check against the pre-registered values:")
ok = True
for k, want in EXPECTED.items():
    have = got[k]
    hit = abs(have - want) < (0.01 if 'acc' in k else 1)
    ok &= hit
    print(f"  {k:9s} expected {want:>10}   got {have:>10}   {'OK' if hit else 'MISMATCH'}")
if not ok:
    raise SystemExit(
        "\nMISMATCH: this run disagrees with the values derived from test-2's saved "
        "probabilities. Most likely the resolver picked a different checkpoint, or the "
        "partition differs. Check the resolved path printed above before using anything.")
print("  -> all four match; the checkpoint and partition are confirmed.")


# ─── COLLECT FALSE NEGATIVES AT THE DEPLOYED THRESHOLD ────────────────────────
LOG_CALL = re.compile(r'\bLog\.[vdiwe]\s*\(')


def brace_balanced(code):
    """Weak necessary condition for parseability. PAPER.md §3.5b / §7.4 show 88.7%
    of GCB+DFG's LVDAndro false negatives fail it, so flagging it here saves
    re-deriving the P1 classification by hand."""
    depth = 0
    for ch in code:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


false_negatives = []
for pos, (prob, label, raw_idx) in enumerate(zip(all_probs, all_labels, all_idx)):
    if label == 1 and prob < args.threshold:
        raw = json.loads(test_ds.lines[int(raw_idx)])
        code = raw.get('code', '') or ''
        fname = str(raw.get('filename', '') or 'Unknown')
        false_negatives.append({
            'index': int(test_ds.original_indices[int(raw_idx)]),
            'subset_index': int(raw_idx),
            'confidence_safe': float(1.0 - prob),
            'prob_vulnerable': float(prob),
            'also_fn_at_0.50': bool(prob < 0.50),
            'brace_balanced': brace_balanced(code),
            'has_log_call': bool(LOG_CALL.search(code)),
            'code': code,
            'project': fname,
            'source': fname.split('_')[0] or 'unknown',
        })

false_negatives.sort(key=lambda x: x['confidence_safe'], reverse=True)
src_counts = Counter(fn['source'] for fn in false_negatives)
print(f"\nTotal false negatives @{args.threshold}: {len(false_negatives):,}")

print("\n" + "=" * 62)
print("Top 20 most confident false negatives")
print("=" * 62 + "\n")
for i, fn in enumerate(false_negatives[:20]):
    print(f"[FN #{i+1}] corpus_idx={fn['index']} source={fn['source']} "
          f"conf_safe={fn['confidence_safe']*100:.2f}%  "
          f"{'MALFORMED' if not fn['brace_balanced'] else 'well-formed'}"
          f"{'  HAS-LOG' if fn['has_log_call'] else ''}")
    print(f"from '{fn['project']}'")
    print("-" * 40)
    lines = fn['code'].split('\n')
    print('\n'.join(lines[:35]))
    if len(lines) > 35:
        print(f"... [truncated {len(lines)-35} more lines]")
    print("=" * 60 + "\n")


# ─── PERSIST ──────────────────────────────────────────────────────────────────
out_txt = '/kaggle/working/test7b_qualitative_scanner_results.txt'
with open(out_txt, 'w', encoding='utf-8') as fh:
    fh.write('Test 7b: Qualitative Analysis - Top False Negatives (DEPLOYED SCANNER MODEL)\n')
    fh.write('=' * 78 + '\n')
    fh.write('Model         : UniXcoder text-only  (the model scanner-pipeline.ipynb ships)\n')
    fh.write(f'Backbone      : {args.backbone}\n')
    fh.write(f'Checkpoint    : {args.unixcoder_text_weights}\n')
    fh.write(f'code_length   : {args.code_length}   (truncation=True, no sliding window -- PAPER.md 6.8)\n')
    fh.write(f'Threshold     : {args.threshold}  (deployed scanner value)\n')
    fh.write(f'Test set      : {len(test_indices):,} samples, duplicate-filtered (PAPER.md 5.3)\n')
    fh.write('\n')
    fh.write(f'Accuracy @0.45: {acc_045*100:.4f}%     false negatives: {n_fn_045:,}\n')
    fh.write(f'Accuracy @0.50: {acc_050*100:.4f}%     false negatives: {n_fn_050:,}\n')
    fh.write('  test-2 reports this model at 88.3447% / FN 1,217 by argmax; the @0.50\n')
    fh.write('  row is the cross-check. A mismatch means the wrong checkpoint loaded.\n')
    fh.write('\nFalse negatives by source (@%.2f):\n' % args.threshold)
    for s, c in src_counts.most_common():
        fh.write(f'  {s:<12} {c:>6,}\n')

    mal = sum(1 for fn in false_negatives if not fn['brace_balanced'])
    logs = sum(1 for fn in false_negatives if fn['has_log_call'])
    fh.write(f'\nOf {len(false_negatives):,} false negatives: {mal:,} malformed '
             f'({100*mal/max(1,len(false_negatives)):.1f}%), '
             f'{logs:,} contain a Log.x() call ({100*logs/max(1,len(false_negatives)):.1f}%)\n')

    fh.write('\n\nTop 20 most confident false negatives\n')
    fh.write('=' * 78 + '\n')
    fh.write(f'{"#":>3} {"corpus_idx":>11} {"source":<10} {"conf_safe":>10} {"form":>11} {"log":>4}  filename\n')
    fh.write('-' * 78 + '\n')
    for i, fn in enumerate(false_negatives[:20]):
        fh.write(f'{i+1:>3} {fn["index"]:>11} {fn["source"]:<10} '
                 f'{fn["confidence_safe"]*100:>9.2f}% '
                 f'{"malformed" if not fn["brace_balanced"] else "well-formed":>11} '
                 f'{"yes" if fn["has_log_call"] else "no":>4}  {fn["project"]}\n')

    fh.write('\n\nFull code of the top 20 (for hand-classification, PAPER.md Part 7)\n')
    for i, fn in enumerate(false_negatives[:20]):
        fh.write('\n' + '=' * 78 + '\n')
        fh.write(f'[FN #{i+1}] corpus_idx={fn["index"]} source={fn["source"]} '
                 f'confidence_safe={fn["confidence_safe"]*100:.2f}% '
                 f'{"MALFORMED" if not fn["brace_balanced"] else "well-formed"}'
                 f'{" HAS-LOG" if fn["has_log_call"] else ""}\n')
        fh.write(f'filename: {fn["project"]}\n')
        fh.write('-' * 78 + '\n')
        fh.write(fn['code'] + '\n')

    fh.write('\n\nProvenance: test_scripts/test-7b-qualitative-scanner-model.py\n')
print(f'\nSaved -> {out_txt}')

out_json = '/kaggle/working/test7b_false_negatives.json'
with open(out_json, 'w', encoding='utf-8') as fh:
    json.dump({
        'model': 'unixcoder_text_only',
        'role': 'deployed scanner model (scanner-pipeline.ipynb)',
        'backbone': args.backbone,
        'checkpoint': args.unixcoder_text_weights,
        'code_length': args.code_length,
        'threshold': args.threshold,
        'test_set_size': len(test_indices),
        'duplicate_filtered': True,
        'accuracy_at_0.45': acc_045,
        'accuracy_at_0.50': acc_050,
        'total_false_negatives_at_0.45': n_fn_045,
        'total_false_negatives_at_0.50': n_fn_050,
        'by_source': dict(src_counts),
        'false_negatives': [{k: v for k, v in fn.items() if k != 'code'}
                            for fn in false_negatives],
    }, fh, indent=2)
print(f'Saved -> {out_json}')

np.save('/kaggle/working/test7b_probs_unixcoder_text.npy', all_probs)
print('Saved -> /kaggle/working/test7b_probs_unixcoder_text.npy')
print('\nDone. Download all three files into results/.')
