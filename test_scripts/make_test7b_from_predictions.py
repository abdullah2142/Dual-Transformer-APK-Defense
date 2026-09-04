"""
Test 7b without a GPU: qualitative false-negative analysis of the DEPLOYED
SCANNER MODEL (UniXcoder text-only), derived from probabilities already on disk.

WHY THIS IS VALID -- AND HOW IT IS PROVEN
-----------------------------------------
test-2 ran all six models over the duplicate-filtered test partition and saved
per-sample probabilities to results/predictions/. Those arrays are ordered by
SequentialSampler over the same sorted `test_indices` every script builds, so
array position i corresponds to corpus index test_indices[i].

Re-running UniXcoder text-only on that partition would recompute numbers that
already exist. Instead this script derives them -- and refuses to run unless it
can first reproduce a known answer:

    GUARD: rebuild GraphCodeBERT+DFG's false-negative set from its saved
    probabilities and require an EXACT set match against the 1,054 corpus
    indices that test-7 recorded from an actual GPU run.

If the guard passes, the alignment assumption is not an assumption. If it fails,
the script aborts rather than emit numbers built on a broken mapping.

test_scripts/test-7b-qualitative-scanner-model.py is the GPU-side equivalent and
stays in the repo as the reproducible path. It should produce identical output.

THRESHOLD
    0.45 is primary -- the deployed scanner value (PAPER.md 6.7).
    0.50 (argmax) is reported alongside so counts compare directly with Part 7.

USAGE
    python test_scripts/make_test7b_from_predictions.py

OUTPUTS
    results/test7b_qualitative_scanner_results.txt   top 20 with full code
    results/test7b_false_negatives.json              every FN + flags + overlap
"""

import argparse
import array
import ast
import json
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from split_and_filter import get_split_indices

DATA = 'dataset/dataset_graphcodebert.jsonl'
PRED = 'results/predictions'
LOG_CALL = re.compile(r'\bLog\.[vdiwe]\s*\(')


def load_npy(path):
    """Minimal .npy reader. numpy is not installed everywhere this repo runs;
    make_baseline_chart.py has the same no-dependency posture."""
    try:
        import numpy as np
        a = np.load(path)
        return a.reshape(-1).tolist(), a.shape
    except ImportError:
        pass
    with open(path, 'rb') as f:
        if f.read(6) != b'\x93NUMPY':
            raise ValueError(f'{path}: not a .npy file')
        major, _ = f.read(2)
        hlen = struct.unpack('<H' if major == 1 else '<I',
                             f.read(2 if major == 1 else 4))[0]
        header = ast.literal_eval(f.read(hlen).decode('latin1').strip())
        raw = f.read()
    typecode = {'<f8': 'd', '<f4': 'f', '<i8': 'q', '<i4': 'i'}.get(header['descr'])
    if typecode is None:
        raise ValueError(f'{path}: unsupported dtype {header["descr"]}')
    buf = array.array(typecode)
    buf.frombytes(raw)
    return list(buf), header['shape']


def p_vulnerable(path):
    """Column 1 of an (N, 2) softmax output, or a flat (N,) array as-is."""
    flat, shape = load_npy(path)
    if len(shape) == 2 and shape[1] == 2:
        return flat[1::2]
    return flat


def brace_balanced(code):
    depth = 0
    for ch in code:
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def false_negative_positions(probs, labels, threshold):
    """argmax semantics at 0.50: predicted safe when p_vuln <= 0.50."""
    if threshold == 0.50:
        return [i for i, (p, y) in enumerate(zip(probs, labels)) if y == 1 and p <= 0.50]
    return [i for i, (p, y) in enumerate(zip(probs, labels)) if y == 1 and p < threshold]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=DATA)
    ap.add_argument('--threshold', type=float, default=0.45)
    ap.add_argument('--out-txt', default='results/test7b_qualitative_scanner_results.txt')
    ap.add_argument('--out-json', default='results/test7b_false_negatives.json')
    a = ap.parse_args()

    _, _, test_idx, _ = get_split_indices(a.data)
    assert len(test_idx) == 18541, f'expected 18,541 filtered test rows, got {len(test_idx):,}'
    assert test_idx == sorted(test_idx), 'test_indices must be sorted for positional alignment'

    labels = [int(v) for v in load_npy(os.path.join(PRED, 'test_labels.npy'))[0]]
    assert len(labels) == len(test_idx), 'label array does not match the partition'

    # ── GUARD ────────────────────────────────────────────────────────────────
    # Reproduce a GPU-measured answer before trusting the mapping for anything.
    gcb = p_vulnerable(os.path.join(PRED, 'test_probs_graphcodebert_dfg.npy'))
    derived = {test_idx[i] for i in false_negative_positions(gcb, labels, 0.50)}
    with open('results/test7_false_negatives.json', encoding='utf-8') as f:
        d = json.load(f)
    recs = d if isinstance(d, list) else d.get('false_negatives')
    recorded = {r['index'] for r in recs}
    if derived != recorded:
        sys.exit(
            f'GUARD FAILED: GCB+DFG false negatives rebuilt from saved probabilities '
            f'({len(derived):,}) do not match test-7\'s GPU run ({len(recorded):,}); '
            f'{len(derived ^ recorded):,} differ. The probability arrays are not aligned '
            f'to the partition -- refusing to derive test-7b from them.')
    print(f'GUARD PASSED: rebuilt GCB+DFG FN set matches test-7 exactly '
          f'({len(derived):,} corpus indices, set-identical).')

    # ── the deployed scanner model ───────────────────────────────────────────
    uni = p_vulnerable(os.path.join(PRED, 'test_probs_unixcoder_text.npy'))
    n = len(uni)

    def acc(t):
        return sum(1 for p, y in zip(uni, labels)
                   if (p >= t) == (y == 1)) / n

    acc45, acc50 = acc(0.45), acc(0.50)
    pos45 = false_negative_positions(uni, labels, 0.45)
    pos50 = false_negative_positions(uni, labels, 0.50)
    print(f'\nUniXcoder text-only (the deployed scanner model)')
    print(f'  @0.45  acc={acc45*100:.4f}%  FN={len(pos45):,}')
    print(f'  @0.50  acc={acc50*100:.4f}%  FN={len(pos50):,}   '
          f'<- test-2 records 88.3447% / FN 1,217')

    wanted = {test_idx[i] for i in pos45}
    corpus = {}
    with open(a.data, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            if i in wanted:
                e = json.loads(line)
                corpus[i] = (e.get('code') or '', str(e.get('filename') or 'Unknown'))

    fns = []
    for i in pos45:
        ci = test_idx[i]
        code, fname = corpus[ci]
        fns.append({
            'index': ci,
            'subset_index': i,
            'confidence_safe': 1.0 - uni[i],
            'prob_vulnerable': uni[i],
            'also_fn_at_0.50': uni[i] <= 0.50,
            'brace_balanced': brace_balanced(code),
            'has_log_call': bool(LOG_CALL.search(code)),
            'code': code,
            'project': fname,
            'source': fname.split('_')[0] or 'unknown',
        })
    fns.sort(key=lambda r: r['confidence_safe'], reverse=True)
    by_source = Counter(r['source'] for r in fns)

    # ── cross-model overlap: does the text-only arm fail where the DFG arm does?
    overlap = wanted & recorded
    jaccard = len(overlap) / len(wanted | recorded)
    print(f'\nCross-model FN overlap (UniXcoder text-only @0.45 vs GCB+DFG @argmax):')
    print(f'  shared {len(overlap):,} | UniXcoder-only {len(wanted-recorded):,} | '
          f'GCB+DFG-only {len(recorded-wanted):,} | Jaccard {jaccard:.3f}')

    malformed = sum(1 for r in fns if not r['brace_balanced'])
    logs = sum(1 for r in fns if r['has_log_call'])

    out = []
    w = out.append
    w('Test 7b: Qualitative Analysis - Top False Negatives (DEPLOYED SCANNER MODEL)')
    w('=' * 78)
    w('Model         : UniXcoder text-only  (the model scanner-pipeline.ipynb ships)')
    w('Backbone      : microsoft/unixcoder-base')
    w('code_length   : 384   (truncation=True, no sliding window -- PAPER.md 6.8)')
    w(f'Threshold     : {a.threshold}  (deployed scanner value, PAPER.md 6.7)')
    w(f'Test set      : {len(test_idx):,} samples, duplicate-filtered (PAPER.md 5.3)')
    w('Derived from  : results/predictions/test_probs_unixcoder_text.npy (test-2, 2026-08-20)')
    w('Guard         : GCB+DFG FN set rebuilt from the same arrays reproduces test-7\'s')
    w('                1,054 corpus indices exactly, so the positional mapping is verified.')
    w('')
    w(f'Accuracy @0.45: {acc45*100:.4f}%     false negatives: {len(pos45):,}')
    w(f'Accuracy @0.50: {acc50*100:.4f}%     false negatives: {len(pos50):,}')
    w('  test-2 independently records this model at 88.3447% / FN 1,217 by argmax.')
    w('')
    w(f'False negatives by source (@{a.threshold}):')
    for s, c in by_source.most_common():
        w(f'  {s:<12} {c:>6,}')
    w('')
    w(f'Of {len(fns):,} false negatives: {malformed:,} are not brace-balanced '
      f'({100*malformed/max(1,len(fns)):.1f}%), {logs:,} contain a Log.x() call '
      f'({100*logs/max(1,len(fns)):.1f}%)')
    w('')
    w('Cross-model comparison with test-7 (GraphCodeBERT+DFG, argmax):')
    w(f'  shared false negatives : {len(overlap):,}')
    w(f'  UniXcoder text-only only: {len(wanted-recorded):,}')
    w(f'  GraphCodeBERT+DFG only : {len(recorded-wanted):,}')
    w(f'  Jaccard                : {jaccard:.3f}')
    w('')
    w('')
    w('Top 20 most confident false negatives')
    w('=' * 78)
    w(f'{"#":>3} {"corpus_idx":>11} {"source":<10} {"conf_safe":>10} {"form":>11} {"log":>4}  filename')
    w('-' * 78)
    for i, r in enumerate(fns[:20]):
        w(f'{i+1:>3} {r["index"]:>11} {r["source"]:<10} '
          f'{r["confidence_safe"]*100:>9.2f}% '
          f'{"malformed" if not r["brace_balanced"] else "well-formed":>11} '
          f'{"yes" if r["has_log_call"] else "no":>4}  {r["project"]}')
    w('')
    w('')
    w('Full code of the top 20 (for hand-classification, PAPER.md Part 7)')
    for i, r in enumerate(fns[:20]):
        w('')
        w('=' * 78)
        w(f'[FN #{i+1}] corpus_idx={r["index"]} source={r["source"]} '
          f'confidence_safe={r["confidence_safe"]*100:.2f}% '
          f'{"MALFORMED" if not r["brace_balanced"] else "well-formed"}'
          f'{" HAS-LOG" if r["has_log_call"] else ""}')
        w(f'filename: {r["project"]}')
        w('-' * 78)
        w(r['code'])
    w('')
    w('')
    w('Provenance: test_scripts/make_test7b_from_predictions.py')

    os.makedirs(os.path.dirname(a.out_txt) or '.', exist_ok=True)
    with open(a.out_txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print(f'\nSaved -> {a.out_txt}')

    with open(a.out_json, 'w', encoding='utf-8') as f:
        json.dump({
            'model': 'unixcoder_text_only',
            'role': 'deployed scanner model (scanner-pipeline.ipynb)',
            'backbone': 'microsoft/unixcoder-base',
            'code_length': 384,
            'threshold': a.threshold,
            'derived_from': 'results/predictions/test_probs_unixcoder_text.npy',
            'guard': 'GCB+DFG FN set rebuilt from saved probs == test-7 GPU run (exact)',
            'test_set_size': len(test_idx),
            'duplicate_filtered': True,
            'accuracy_at_0.45': acc45,
            'accuracy_at_0.50': acc50,
            'total_false_negatives_at_0.45': len(pos45),
            'total_false_negatives_at_0.50': len(pos50),
            'by_source': dict(by_source),
            'overlap_with_gcb_dfg': {
                'shared': len(overlap),
                'unixcoder_text_only': len(wanted - recorded),
                'gcb_dfg_only': len(recorded - wanted),
                'jaccard': jaccard,
            },
            'false_negatives': [{k: v for k, v in r.items() if k != 'code'} for r in fns],
        }, f, indent=2)
    print(f'Saved -> {a.out_json}')


if __name__ == '__main__':
    main()
