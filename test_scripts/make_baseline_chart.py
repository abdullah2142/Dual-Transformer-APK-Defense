"""
Standalone chart builder: TF-IDF baselines vs the six transformers.

WHY THIS EXISTS
---------------
Re-running test-5 to redraw its chart would refit a TF-IDF vectoriser over
163,967 documents, a saga LogisticRegression at max_iter=1000, and a 30-iteration
MLP -- 30-60 minutes of CPU to reproduce numbers that are deterministic under
seed 42 and already recorded. This reads the two results files instead and draws
the same figure in seconds.

Use it whenever test-2 is re-run and the comparison needs refreshing. It does not
recompute anything; if a number is wrong here, it is wrong in the source file.

USAGE
    python test_scripts/make_baseline_chart.py
    python test_scripts/make_baseline_chart.py --out /kaggle/working/test6_baseline_bar.png

INPUTS   results/test6_baseline_results.txt   (LR + MLP, from test-5)
         results/test2_auc_results.txt        (six transformers, from test-2)

Both must describe the SAME test partition. The script checks this and refuses
to plot if they disagree -- mixing an 18,541-sample transformer row with a
19,996-sample baseline row is exactly the kind of silent mismatch this project
has spent its whole history unpicking.
"""

import argparse
import os
import re
import sys

BASE_DEFAULT = 'results/test6_baseline_results.txt'
T2_DEFAULT   = 'results/test2_auc_results.txt'
OUT_DEFAULT  = 'results/test6_baseline_bar.png'


def parse_baselines(path):
    """test-5's block format:  'LR + TF-IDF\n  Accuracy : 83.6794%\n  ROC-AUC : 0.9202'"""
    txt = open(path, encoding='utf-8').read()
    rows, n = [], None
    m = re.search(r'Test set\s*:\s*([\d,]+)\s*samples', txt)
    if m:
        n = int(m.group(1).replace(',', ''))
    for name in ('LR + TF-IDF', 'MLP + TF-IDF'):
        blk = re.search(rf'^{re.escape(name)}\n(.*?)(?=\n\S|\Z)', txt, re.S | re.M)
        if not blk:
            continue
        body = blk.group(1)
        acc = re.search(r'Accuracy\s*:\s*([\d.]+)%', body)
        auc = re.search(r'ROC-AUC\s*:\s*([\d.]+)', body)
        if not (acc and auc):
            continue
        a = float(acc.group(1)) / 100.0
        if a == 0.0:
            print(f'  skipping {name}: 0.0000% is a placeholder, not a measurement')
            continue
        rows.append((name, a, float(auc.group(1))))
    return rows, n


def parse_transformers(path):
    """test-2's machine-readable line: 'CodeBERT (Text): Acc=0.8768, ROC-AUC=0.9571, ...'"""
    if not os.path.exists(path):
        return [], None
    txt = open(path, encoding='utf-8').read()
    n = None
    m = re.search(r'Test set:\s*([\d,]+)\s*samples', txt)
    if m:
        n = int(m.group(1).replace(',', ''))
    rows = []
    for line in txt.splitlines():
        m = re.match(r'\s*(.+?):\s*Acc=([\d.]+),\s*ROC-AUC=([\d.]+)', line)
        if m:
            a = float(m.group(2))
            if a == 0.0:
                print(f'  skipping {m.group(1)}: 0.0000 is a placeholder')
                continue
            rows.append((m.group(1).strip(), a, float(m.group(3))))
    return rows, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baselines', default=BASE_DEFAULT)
    ap.add_argument('--test2', default=T2_DEFAULT)
    ap.add_argument('--out', default=OUT_DEFAULT)
    a = ap.parse_args()

    print(f'Reading baselines   : {a.baselines}')
    base, n_base = parse_baselines(a.baselines)
    print(f'Reading transformers: {a.test2}')
    trans, n_trans = parse_transformers(a.test2)

    if not base:
        sys.exit('No usable baseline rows. Run test-5 first.')
    if not trans:
        sys.exit(f'No usable transformer rows in {a.test2}. Run test-2 first, then '
                 f'copy its test2_auc_results.txt into results/.')

    # A test-2 file with no "Test set:" header predates the duplicate filter, so
    # it is by definition from before the remediation. Refuse it: the committed
    # example carries CodeBERT at 0.9312/0.9340, the leaked Partition-B numbers.
    if n_trans is None:
        sys.exit(f'REFUSING TO PLOT: {a.test2} has no "Test set: N samples" header, '
                 f'so it predates the duplicate filter and is stale. Replace it with '
                 f'the output of the current test-2.')

    # both files must describe the same partition
    if n_base and n_trans and n_base != n_trans:
        sys.exit(f'REFUSING TO PLOT: baselines are on {n_base:,} samples but '
                 f'transformers are on {n_trans:,}. These are different test sets and '
                 f'must not share an axis. Re-run whichever is stale.')
    n = n_trans or n_base

    rows = base + trans
    print(f'\n{len(rows)} models on {n:,} samples' if n else f'\n{len(rows)} models')
    for nm, acc, auc in rows:
        print(f'  {nm:24s} acc={acc:.4f}  roc={auc:.4f}')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [r[0].replace(' (', '\n(').replace(' + ', '+\n') for r in rows]
    x = np.arange(len(rows))
    w = 0.35
    fig, ax = plt.subplots(figsize=(14, 6))
    b1 = ax.bar(x - w / 2, [r[1] for r in rows], w, label='Accuracy', color='#4C72B0', alpha=0.88)
    b2 = ax.bar(x + w / 2, [r[2] for r in rows], w, label='ROC-AUC',  color='#55A868', alpha=0.88)

    for bar in list(b1) + list(b2):
        ax.annotate(f'{bar.get_height():.3f}',
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 4), textcoords='offset points',
                    ha='center', va='bottom', fontsize=8)

    ax.set_ylim(0.0, 1.1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9, rotation=15, ha='right')
    ax.set_ylabel('Score', fontsize=12)
    title = 'Accuracy & ROC-AUC: TF-IDF Baselines vs Transformer Models'
    if n:
        title += f'  ({n:,} duplicate-filtered test samples)'
    ax.set_title(title, fontsize=13)
    ax.legend(fontsize=11, loc='lower right')
    ax.yaxis.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    ax.axvspan(-0.5, len(base) - 0.5, alpha=0.07, color='red')
    ax.text((len(base) - 1) / 2, 1.05, 'Baselines', ha='center', fontsize=10, color='#880000',
            transform=ax.get_xaxis_transform())

    plt.tight_layout()
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    fig.savefig(a.out, dpi=150)
    print(f'\nSaved -> {a.out}')


if __name__ == '__main__':
    main()
