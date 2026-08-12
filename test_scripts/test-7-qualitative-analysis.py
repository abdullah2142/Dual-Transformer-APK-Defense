!pip install torch transformers tree_sitter==0.21.3 scikit-learn matplotlib -q

import os
import torch
import json
import math
import hashlib
import random
import numpy as np
from transformers import AutoTokenizer, RobertaConfig, RobertaModel
from torch.utils.data import DataLoader, SequentialSampler, Dataset
from tqdm.auto import tqdm
import torch.nn as nn
import torch.nn.functional as F
from torch.nn import CrossEntropyLoss
from collections import defaultdict

print("Imports complete.")

class Args:
    train_file = '/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl'
    gcb_dfg_weights = '' # TODO: /kaggle/input/<your-dataset>/saved_models/best_model.bin
    code_length = 384
    data_flow_length = 128
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    eval_batch_size = 32
    seed = 42
    test_ratio = 0.10
    val_ratio = 0.08   # needed so the duplicate filter can exclude val samples too

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

def set_seed(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if torch.cuda.device_count() > 0: torch.cuda.manual_seed_all(s)
set_seed(args.seed)

# ─── SPLIT (matches training) + DUPLICATE FILTER ──────────────────────────────
# See REMEDIATION_PLAN.md §5.1.
#
# CRITICAL: this file previously recovered the source from the filename prefix
# and grouped by it before splitting. The training notebooks did NOT (their
# infer_source finds no source key in this corpus, so every entry resolved to
# "unknown" and the split became a single random shuffle). That mismatch put
# 89.9% of this script's "test" set inside the training data — which means the
# top-20 false negatives behind Section 8's P5a/P5b/P1 patterns were drawn
# largely from samples the model had trained on.
#
# Source is still reported per false negative, via the `filename` field below.

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

# ─── DATASET CLASSES ─────────────────────────
class TextDataset(Dataset):
    def __init__(self, tokenizer, args, file_path, indices=None):
        self.args = args
        self.tokenizer = tokenizer
        self.total_len = args.code_length + args.data_flow_length
        with open(file_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        self.lines = [all_lines[i] for i in indices] if indices is not None else all_lines
        self.original_indices = indices if indices is not None else list(range(len(all_lines)))
            
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
            'label': torch.tensor(label, dtype=torch.long),
            'index': item
        }

print("Loading dataset...")
tokenizer = AutoTokenizer.from_pretrained("microsoft/graphcodebert-base", use_fast=True)
test_ds = TextDataset(tokenizer, args, args.train_file, indices=test_indices)
print(f"Test samples isolated: {len(test_ds)}")

print("Loading GraphCodeBERT model...")
if not args.gcb_dfg_weights or not os.path.exists(args.gcb_dfg_weights):
    print("Please set args.gcb_dfg_weights")
    model = None
else:
    config = RobertaConfig.from_pretrained("microsoft/graphcodebert-base")
    config.num_labels = 2
    encoder = RobertaModel.from_pretrained("microsoft/graphcodebert-base", config=config)
    model = DFGModel(encoder, config)
    model.load_state_dict(torch.load(args.gcb_dfg_weights, map_location=args.device))
    model.to(args.device)
    model.eval()
    print("Model loaded successfully!")

if model:
    eval_sampler = SequentialSampler(test_ds)
    eval_dataloader = DataLoader(test_ds, sampler=eval_sampler, batch_size=args.eval_batch_size, num_workers=2)

    all_preds = []
    all_labels = []
    all_probs = []
    all_indices = []

    print("Running inference on test set...")
    with torch.no_grad():
        for batch in tqdm(eval_dataloader, desc="Evaluating"):
            input_ids = batch['input_ids'].to(args.device)
            p_ids = batch['p_ids'].to(args.device)
            attn_mask = batch['attn_mask'].to(args.device)
            labels = batch['label'].to(args.device)
            indices = batch['index']
            
            probs = model(input_ids=input_ids, p_ids=p_ids, attn_mask=attn_mask)
            preds = torch.argmax(probs, dim=-1)
            
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_probs.extend(probs[:, 1].cpu().numpy())
            all_indices.extend(indices.numpy())

if model:
    false_negatives = []

    for i, (pred, label, prob, raw_idx) in enumerate(zip(all_preds, all_labels, all_probs, all_indices)):
        if label == 1 and pred == 0:
            raw_line = test_ds.lines[raw_idx]
            raw_data = json.loads(raw_line)
            
            # raw_idx is the position WITHIN the test subset. Record the index
            # into the original JSONL as well, so each false negative can be
            # traced back to the corpus and compared across models/runs — the
            # hand-classification in Section 8 depends on stable identifiers.
            # Cast out of numpy scalars: `prob` is float32 and `raw_idx` is
            # int64, neither of which json.dump can serialise.
            corpus_idx = int(test_ds.original_indices[int(raw_idx)])
            false_negatives.append({
                'index': corpus_idx,
                'subset_index': int(raw_idx),
                'confidence_safe': float(1.0 - prob),
                'code': raw_data.get('code', 'N/A'),
                'project': raw_data.get('filename', 'Unknown'),
                'source': str(raw_data.get('filename', '')).split('_')[0] or 'unknown'
            })

    print(f"\nTotal False Negatives Found in Test Set: {len(false_negatives)}")

    false_negatives.sort(key=lambda x: x['confidence_safe'], reverse=True)

    print("\n======================================================")
    print("Analyzing the Top 20 Most Confident False Negatives:")
    print("======================================================\n")

    for i, fn in enumerate(false_negatives[:20]):
        print(f"[False Negative #{i+1}] - corpus_idx={fn['index']} "
              f"source={fn['source']} - Originally from '{fn['project']}'")
        print(f"Model Confidence it was SAFE: {fn['confidence_safe'] * 100:.2f}%")
        print("-" * 40)
        lines = fn['code'].split('\n')
        
        max_lines = 35
        print('\n'.join(lines[:max_lines]))
        if len(lines) > max_lines:
            print(f"... [Truncated {len(lines) - max_lines} more lines]")
        print("=" * 60 + "\n")

    # ─── PERSIST RESULTS ──────────────────────────────────────────────────────
    # Section 8's pattern classification (P5a/P5b/P1/...) is done by hand from
    # these samples, so they must outlive the Kaggle console log. Full code is
    # written for the top 20 (what gets classified); the JSON carries every FN
    # with its corpus index so FN sets can be compared across models and runs.
    from collections import Counter as _Counter
    src_counts = _Counter(fn['source'] for fn in false_negatives)

    out_txt = '/kaggle/working/test7_qualitative_results.txt'
    with open(out_txt, 'w', encoding='utf-8') as fh:
        fh.write('Test 7: Qualitative Analysis - Top False Negatives\n')
        fh.write('=' * 60 + '\n')
        fh.write('Model      : GraphCodeBERT + DFG\n')
        fh.write(f'Test set   : {len(test_indices):,} samples '
                 f'(duplicate-filtered; see REMEDIATION_PLAN.md 5.1)\n')
        fh.write(f'Threshold  : argmax (0.5)\n')
        fh.write(f'Total FNs  : {len(false_negatives):,}\n\n')
        fh.write('False negatives by source:\n')
        for s, c in src_counts.most_common():
            fh.write(f'  {s:<12} {c:>6,}\n')

        fh.write('\n\nTop 20 most confident false negatives\n')
        fh.write('=' * 60 + '\n')
        fh.write(f'{"#":>3} {"corpus_idx":>11} {"source":<10} {"conf_safe":>10}  filename\n')
        fh.write('-' * 60 + '\n')
        for i, fn in enumerate(false_negatives[:20]):
            fh.write(f'{i+1:>3} {fn["index"]:>11} {fn["source"]:<10} '
                     f'{fn["confidence_safe"]*100:>9.2f}%  {fn["project"]}\n')

        fh.write('\n\nFull code of the top 20 (for pattern classification)\n')
        for i, fn in enumerate(false_negatives[:20]):
            fh.write('\n' + '=' * 60 + '\n')
            fh.write(f'[FN #{i+1}] corpus_idx={fn["index"]} source={fn["source"]} '
                     f'confidence_safe={fn["confidence_safe"]*100:.2f}%\n')
            fh.write(f'filename: {fn["project"]}\n')
            fh.write('-' * 60 + '\n')
            fh.write(fn['code'] + '\n')
    print(f'Saved -> {out_txt}')

    # Machine-readable: every FN, code omitted to keep the file small.
    out_json = '/kaggle/working/test7_false_negatives.json'
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump({
            'model': 'graphcodebert_dfg',
            'test_set_size': len(test_indices),
            'duplicate_filtered': True,
            'total_false_negatives': len(false_negatives),
            'by_source': dict(src_counts),
            'false_negatives': [
                {k: v for k, v in fn.items() if k != 'code'}
                for fn in false_negatives
            ],
        }, fh, indent=2)
    print(f'Saved -> {out_json}')
