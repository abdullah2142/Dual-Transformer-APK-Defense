!pip install statsmodels pandas numpy -q

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

results = []
results.append(run_mcnemar(preds_gcb_dfg, preds_gcb_text, labels, 'GraphCodeBERT+DFG', 'GraphCodeBERT Text'))
results.append(run_mcnemar(preds_codebert_dfg, preds_codebert_text, labels, 'CodeBERT+DFG', 'CodeBERT Text'))
results.append(run_mcnemar(preds_unix_dfg, preds_unix_text, labels, 'UniXcoder+DFG', 'UniXcoder Text'))
results.append(run_mcnemar(preds_gcb_dfg, preds_codebert_dfg, labels, 'GraphCodeBERT+DFG', 'CodeBERT+DFG'))
results.append(run_mcnemar(preds_gcb_dfg, preds_unix_dfg, labels, 'GraphCodeBERT+DFG', 'UniXcoder+DFG'))

df = pd.DataFrame(results)
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
