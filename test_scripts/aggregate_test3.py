"""
Aggregate however many test-3 seeds exist into Table 3.

Works at any n. Run it after three seeds, again after five, without editing
anything -- it discovers whatever `test3_seed*_results.json` files are present,
reports the correct critical value for that n, and says plainly whether the
sample is large enough to support the claim being made.

WHY IT REPORTS THE CRITICAL VALUE SO LOUDLY
-------------------------------------------
The analysis is a one-sample t-test of the seed accuracies against the GCB+DFG
checkpoint, and at small n the critical value dominates everything:

    n=3  df=2  t_crit 4.303      n=5  df=4  t_crit 2.776

At n=3 the test fails if the true sd exceeds ~0.18pp, which is under one standard
error above the observed estimate. At n=5 the line moves to ~0.36pp. The number
of seeds is not a detail here; it is most of the analysis.

PRE-REGISTRATION (PAPER.md 3.3a, fixed 2026-09-06 before any warmup run existed)
    target n = 5. Seeds 42, 123, 2025 first; 7 and 2718 if GPU time permits,
    *regardless of what the first three show*. Reporting at whatever n is
    reached, with the critical value for that n stated.
Adding seeds because the first three came out unfavourably would be optional
stopping and would invalidate the p-value. The target was fixed in advance so
that it cannot.

USAGE
    python test_scripts/aggregate_test3.py
    python test_scripts/aggregate_test3.py --results-dir results/test3

OUTPUT  results/test3_multiseed_summary.txt
"""

import argparse
import array
import ast
import glob
import json
import math
import os
import struct
from itertools import combinations

TARGET_N = 5
DFG_ACC = 87.8593        # GCB+DFG, filtered 18,541 (PAPER.md Table 1)
TABLE1_TEXT = 88.2692    # GCB text-only checkpoint, same partition

# two-sided 0.05 critical values, df 1..20
T_CRIT = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
          8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
          14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
          20: 2.086}


def betacf(a, b, x, itmax=200, eps=3e-12):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-30:
            d = 1e-30
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < 1e-30:
            d = 1e-30
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * betacf(b, a, 1.0 - x) / b


def t_sf_two_sided(t, df):
    """P(|T| > |t|) for Student's t. No scipy in this environment."""
    return betai(0.5 * df, 0.5, df / (df + t * t))


def chi2_sf_1df(x):
    return math.erfc(math.sqrt(x / 2.0))


def load_npy(path):
    try:
        import numpy as np
        a = np.load(path)
        return a.reshape(-1).tolist(), a.shape
    except ImportError:
        pass
    with open(path, 'rb') as f:
        if f.read(6) != b'\x93NUMPY':
            raise ValueError(f'{path}: not a .npy')
        major, _ = f.read(2)
        hlen = struct.unpack('<H' if major == 1 else '<I',
                             f.read(2 if major == 1 else 4))[0]
        hdr = ast.literal_eval(f.read(hlen).decode('latin1').strip())
        raw = f.read()
    code = {'<f8': 'd', '<f4': 'f', '<i8': 'q', '<i4': 'i'}[hdr['descr']]
    buf = array.array(code)
    buf.frombytes(raw)
    return list(buf), hdr['shape']


def mcnemar(pred_a, pred_b, labels):
    b = sum(1 for x, z, t in zip(pred_a, pred_b, labels) if x == t and z != t)
    c = sum(1 for x, z, t in zip(pred_a, pred_b, labels) if x != t and z == t)
    n = b + c
    stat = (abs(b - c) - 1) ** 2 / n if n else 0.0
    return b, c, n, stat, chi2_sf_1df(stat)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results-dir', default='results/test3')
    ap.add_argument('--predictions', default='results/predictions')
    ap.add_argument('--out', default='results/test3_multiseed_summary.txt')
    a = ap.parse_args()

    runs = {}
    for path in sorted(glob.glob(os.path.join(a.results_dir, 'test3_seed*_results.json'))):
        with open(path) as f:
            d = json.load(f)
        if not d.get('config', {}).get('cold_start'):
            print(f'  SKIP {path}: not a cold-start run')
            continue
        runs[d['seed']] = d
    if not runs:
        raise SystemExit(
            f'No test-3 results in {a.results_dir}. Expected '
            f'test3_seed<N>_results.json from test_scripts/test_3_multiseed/.')

    n = len(runs)
    accs = [runs[s]['accuracy'] * 100 for s in sorted(runs)]
    mean = sum(accs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in accs) / (n - 1)) if n > 1 else float('nan')

    out = []
    w = out.append
    w('Test 3 -- Multi-Seed Robustness')
    w('=' * 78)
    w(f'Seeds found : {n}  ({", ".join(str(s) for s in sorted(runs))})')
    w(f'Target      : {TARGET_N}  (pre-registered 2026-09-06, PAPER.md 3.3a)')
    if n < TARGET_N:
        w(f'              *** {TARGET_N - n} short. Numbers below are valid but '
          f'under-powered; see the headroom line. ***')
    w('')

    warm = [s for s in sorted(runs)
            if 'warmup' not in json.dumps(runs[s]['config']).lower()]
    w(f'{"seed":>6} {"accuracy":>10} {"ROC-AUC":>9} {"F1":>7} {"FN":>7} {"FP":>7} {"epochs":>7}  stop')
    for s in sorted(runs):
        r = runs[s]
        w(f'{s:>6} {r["accuracy"]*100:9.4f}% {r["roc_auc"]:9.4f} {r["f1"]:7.4f} '
          f'{r["false_negatives"]:7,d} {r["false_positives"]:7,d} {r["epochs_run"]:7d}  {r["stop_reason"]}')
    w('')
    w(f'mean {mean:.4f}%   sample sd {sd:.4f}pp   range {max(accs)-min(accs):.4f}pp')
    if n > 1:
        w(f'sd is itself uncertain: +/-{sd/math.sqrt(2*(n-1)):.4f}pp '
          f'({100/math.sqrt(2*(n-1)):.0f}% relative) at n={n}')
    w('')

    # ── the actual test ──────────────────────────────────────────────────────
    df = n - 1
    tcrit = T_CRIT.get(df)
    diff = mean - DFG_ACC
    if n > 1 and sd > 0:
        t = diff / (sd / math.sqrt(n))
        p = t_sf_two_sided(t, df)
        smax = diff * math.sqrt(n) / tcrit if tcrit else float('nan')
        w(f'One-sample t-test: mean(text seeds) vs GCB+DFG checkpoint ({DFG_ACC:.4f}%)')
        w('-' * 78)
        w(f'  effect      {diff:+.4f}pp')
        w(f'  t({df})       {t:.3f}     critical {tcrit:.3f}     p = {p:.4f}')
        w(f'  verdict     {"SIGNIFICANT at 0.05" if p < 0.05 else "not significant at 0.05"}')
        w(f'  headroom    the test fails if the true sd exceeds {smax:.4f}pp; '
          f'observed {sd:.4f}pp ({smax/sd:.2f}x)')
        if n < TARGET_N and smax / sd < 2.0:
            w(f'  *** that margin is thin. At n={TARGET_N} it would be '
              f'{diff*math.sqrt(TARGET_N)/T_CRIT[TARGET_N-1]/sd:.2f}x. ***')
        w('')

    # ── per-sample churn: how much does the seed alone move predictions? ─────
    lab_path = os.path.join(a.predictions, 'test_labels.npy')
    if os.path.exists(lab_path):
        labels = [int(v) for v in load_npy(lab_path)[0]]
        preds = {}
        for s in sorted(runs):
            pp = os.path.join(a.results_dir, f'test3_seed{s}_probs.npy')
            if not os.path.exists(pp):
                continue
            flat, shape = load_npy(pp)
            probs = flat[1::2] if len(shape) == 2 and shape[1] == 2 else flat
            if len(probs) != len(labels):
                w(f'  WARNING: seed {s} probs are {len(probs):,}, labels {len(labels):,} -- skipped')
                continue
            preds[s] = [1 if p > 0.5 else 0 for p in probs]

        if len(preds) > 1:
            w('Per-sample: how much does the SEED alone move classifications?')
            w('-' * 78)
            w(f'{"pair":>18} {"differ":>9} {"%":>7} {"|b-c|":>7} {"p":>8}')
            for s1, s2 in combinations(sorted(preds), 2):
                dis = sum(1 for x, z in zip(preds[s1], preds[s2]) if x != z)
                b, c, tot, stat, p = mcnemar(preds[s1], preds[s2], labels)
                w(f'{f"{s1} vs {s2}":>18} {dis:9,d} {100*dis/len(labels):6.2f}% '
                  f'{abs(b-c):7d} {p:8.3f}')
            unstable = sum(1 for i in range(len(labels))
                           if len({preds[s][i] for s in preds}) > 1)
            w('')
            w(f'  all {len(preds)} seeds agree on {len(labels)-unstable:,} samples '
              f'({100*(len(labels)-unstable)/len(labels):.2f}%)')
            w(f'  at least one dissents on {unstable:,} ({100*unstable/len(labels):.2f}%)')
            w('')
            w('  For scale, test-8 reports GCB text vs GCB+DFG at 1,298 samples')
            w('  classified differently (7.00%), |b-c| = 76, p = 0.037. If the seed')
            w('  pairs above are the same magnitude, the architecture is not moving')
            w('  more predictions than a reseed does -- only moving them more')
            w('  consistently in one direction, which is what McNemar tests.')
            w('')

            dfg_path = os.path.join(a.predictions, 'test_probs_graphcodebert_dfg.npy')
            if os.path.exists(dfg_path):
                flat, shape = load_npy(dfg_path)
                dprobs = flat[1::2] if len(shape) == 2 and shape[1] == 2 else flat
                dfg = [1 if p > 0.5 else 0 for p in dprobs]
                w('Each seed against the SAME GCB+DFG checkpoint')
                w('-' * 78)
                w(f'{"seed":>6} {"accuracy":>10} {"delta":>10} {"|b-c|":>7} {"p":>8}  significant?')
                for s in sorted(preds):
                    acc = 100 * sum(1 for x, t in zip(preds[s], labels) if x == t) / len(labels)
                    b, c, tot, stat, p = mcnemar(preds[s], dfg, labels)
                    w(f'{s:>6} {acc:9.4f}% {acc-DFG_ACC:+9.3f}pp {abs(b-c):7d} {p:8.3f}  '
                      f'{"YES" if p < 0.05 else "no"}')
                w(f'{"Tbl 1":>6} {TABLE1_TEXT:9.4f}% {TABLE1_TEXT-DFG_ACC:+9.3f}pp '
                  f'{76:7d} {0.037:8.3f}  YES')
                w('')
                w('  CHECK THE WARMUP FIELD before reading this table. Comparing a')
                w('  non-warmup text model against the warmup DFG checkpoint handicaps')
                w('  the text arm by ~0.26pp -- the same order as the effect under test.')
                w('  See results/superseded/test3_nowarmup/README.md.')
                w('')

    w('Provenance: test_scripts/aggregate_test3.py over '
      f'{a.results_dir} ({n} seed{"s" if n != 1 else ""})')

    text = '\n'.join(out)
    print(text)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print(f'\nSaved -> {a.out}')


if __name__ == '__main__':
    main()
