"""
Standalone chart builder: per-source accuracy / ROC-AUC / F1.

WHY THIS EXISTS
---------------
Same reasoning as make_baseline_chart.py. Re-running test-4 to redraw its bar
chart would reload a 499 MB checkpoint and score 18,541 samples on a GPU to
reproduce four numbers that are already written down and deterministic. This
reads the results file instead and draws the figure in a second, on CPU.

It also fixes a real defect. The chart test-4 emitted was titled
"GraphCodeBERT + DFG" while the script loads
`saved_models/best_model_text_only.bin` -- so the committed
results/test5_per_source_bar.png contradicted PAPER.md 3.5, which reports
Table 4 as text-only. The title below is derived from the model label passed
in, not hardcoded, so the two cannot drift apart again.

USAGE
    python test_scripts/make_per_source_chart.py
    python test_scripts/make_per_source_chart.py --out results/foo.svg

INPUT   results/test5_per_source_results.txt   (from test-4)
"""

import argparse
import os
import pathlib
import re
import sys

SRC_DEFAULT = 'results/test5_per_source_results.txt'
OUT_DEFAULT = 'results/test5_per_source_bar.svg'
MODEL_DEFAULT = 'GraphCodeBERT text-only'

# Long-form labels, so the figure states which corpus each bar is without
# forcing the reader back to the table.
DESCRIPTIONS = {
    'LVDAndro': 'LVDAndro\n(decompiled Android)',
    'Draper':   'Draper\n(C/C++ NVD/SARD)',
    'Juliet':   'Juliet\n(synthetic CWE)',
    'Devign':   'Devign\n(C/C++ QEMU/FFmpeg)',
}


def parse(path):
    """test-4's fixed-width block: 'Devign  2,388  64.7404%  0.7189  0.6463  482'."""
    rows = []
    line_re = re.compile(
        r'^\s*(\w+)\s+([\d,]+)\s+([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s+([\d,]+)\s*$')
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            m = line_re.match(line)
            if not m:
                continue
            name, n, acc, auc, f1, fn = m.groups()
            acc = float(acc) / 100.0
            if acc == 0.0:
                print(f'  skipping {name}: 0.0000% is a placeholder, not a measurement')
                continue
            rows.append({
                'source': name,
                'n': int(n.replace(',', '')),
                'acc': acc,
                'auc': float(auc),
                'f1': float(f1),
                'fn': int(fn.replace(',', '')),
            })
    return rows


def write_svg(rows, model, path):
    """Grouped bar chart in raw SVG. No dependencies, and vector beats 150 dpi."""
    W, H = 1000, 560
    ML, MR, MT, MB = 66, 24, 80, 148
    PW, PH = W - ML - MR, H - MT - MB
    gw = PW / len(rows)
    bw = gw * 0.23
    y = lambda v: MT + PH - v * PH

    esc = lambda s: str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}"'
         f' height="{H}" font-family="DejaVu Sans, Arial, sans-serif">',
         f'<rect width="{W}" height="{H}" fill="white"/>']

    total = sum(r['n'] for r in rows)
    o.append(f'<text x="{W/2}" y="24" text-anchor="middle" font-size="15" font-weight="600">'
             f'Test Set Performance by Source ({esc(model)})</text>')
    o.append(f'<text x="{W/2}" y="43" text-anchor="middle" font-size="11.5" fill="#555">'
             f'{total:,} duplicate-filtered test samples</text>')

    for gv in [i / 10 for i in range(0, 11, 2)]:
        yy = y(gv)
        o.append(f'<line x1="{ML}" y1="{yy:.1f}" x2="{ML+PW}" y2="{yy:.1f}" stroke="#ccc"/>')
        o.append(f'<text x="{ML-9}" y="{yy+4:.1f}" text-anchor="end" font-size="11" '
                 f'fill="#444">{gv:.1f}</text>')
    o.append(f'<line x1="{ML}" y1="{MT+PH}" x2="{ML+PW}" y2="{MT+PH}" stroke="#333" stroke-width="1.2"/>')
    o.append(f'<text x="16" y="{MT+PH/2}" text-anchor="middle" font-size="12" '
             f'transform="rotate(-90 16 {MT+PH/2})">Score</text>')

    series = (('acc', '#4C72B0'), ('auc', '#55A868'), ('f1', '#C44E52'))
    for i, r in enumerate(rows):
        cx = ML + gw * (i + 0.5)
        for k, (key, col) in enumerate(series):
            val = r[key]
            bx, by = cx + (k - 1) * (bw + 3) - bw / 2, y(val)
            o.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" '
                     f'height="{MT+PH-by:.1f}" fill="{col}" opacity="0.9"/>')
            o.append(f'<text x="{bx+bw/2:.1f}" y="{by-5:.1f}" text-anchor="middle" '
                     f'font-size="9.5" fill="#222">{val:.3f}</text>')
        label = DESCRIPTIONS.get(r['source'], r['source'])
        for j, part in enumerate(label.split('\n')):
            o.append(f'<text x="{cx:.1f}" y="{MT+PH+19+j*13:.1f}" text-anchor="middle" '
                     f'font-size="10.5" fill="#222">{esc(part)}</text>')
        o.append(f'<text x="{cx:.1f}" y="{MT+PH+19+2*13:.1f}" text-anchor="middle" '
                 f'font-size="10" fill="#666">N = {r["n"]:,} · {r["fn"]} FN</text>')

    # Horizontal legend on the header strip. A boxed legend inside the plot
    # collides with the LVDAndro group, which is near 1.0 on all three series.
    entries = (('Accuracy', '#4C72B0'), ('ROC-AUC', '#55A868'), ('F1 (macro)', '#C44E52'))
    widths = [len(lab) * 6.2 + 32 for lab, _ in entries]
    lx, ly = (W - sum(widths)) / 2, MT - 26
    for (lab, col), wd in zip(entries, widths):
        o.append(f'<rect x="{lx:.1f}" y="{ly}" width="12" height="12" fill="{col}" opacity="0.9"/>')
        o.append(f'<text x="{lx+17:.1f}" y="{ly+10.5}" font-size="11.5" fill="#222">{lab}</text>')
        lx += wd

    o.append('</svg>')
    pathlib.Path(path).write_text('\n'.join(o), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=SRC_DEFAULT)
    ap.add_argument('--out', default=OUT_DEFAULT)
    ap.add_argument('--model', default=MODEL_DEFAULT,
                    help='model label for the title; must match what test-4 loaded')
    a = ap.parse_args()

    print(f'Reading {a.source}')
    rows = parse(a.source)
    if not rows:
        sys.exit(f'No usable rows in {a.source}. Run test-4 first.')

    # Report in the order the paper's table uses, not the file's order.
    order = ['LVDAndro', 'Draper', 'Juliet', 'Devign']
    rows.sort(key=lambda r: order.index(r['source']) if r['source'] in order else 99)

    for r in rows:
        print(f'  {r["source"]:10s} N={r["n"]:6,d}  acc={r["acc"]:.4f}  '
              f'auc={r["auc"]:.4f}  f1={r["f1"]:.4f}  FN={r["fn"]}')

    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    write_svg(rows, a.model, a.out)
    print(f'\nSaved -> {a.out}')


if __name__ == '__main__':
    main()
