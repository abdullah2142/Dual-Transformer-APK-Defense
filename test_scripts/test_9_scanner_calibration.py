import os
import glob
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Find all vulnerability reports.
#
# __file__ is undefined when this is pasted into a notebook cell, which is how
# it is actually run on Kaggle -- it raised NameError before reading anything.
# Search the standard roots instead, matching how test-8 and the checkpoint
# resolver locate their inputs.
if '__file__' in globals():
    SEARCH_ROOTS = [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
else:
    SEARCH_ROOTS = [r for r in ('/kaggle/input', '/kaggle/working', os.getcwd())
                    if os.path.isdir(r)]

print(f"Searching for *_vuln_report.json under: {SEARCH_ROOTS}")
report_files = []
_seen = set()
for _root_dir in SEARCH_ROOTS:
    for root, dirs, files in os.walk(_root_dir):
        for file in files:
            if file.endswith('_vuln_report.json'):
                _p = os.path.realpath(os.path.join(root, file))
                if _p not in _seen:          # roots can overlap
                    _seen.add(_p)
                    report_files.append(_p)
print(f"Found {len(report_files)} report(s)")
for _f in sorted(report_files):
    print(f"  {_f}")

if not report_files:
    print("No *_vuln_report.json files found. Run the scanner pipeline first.")
    exit(0)

all_probs = []
apk_stats = {}
_failures = []

# 0.45, matching the deployed scanner and test-6. Was 0.60, which meant every
# reported flag rate described an operating point the scanner does not use.
THRESHOLD = 0.45

for file in report_files:
    with open(file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # Find probability field in the report (depends on scanner output format)
            # Assuming format: [{'function': '...', 'probability': 0.12}, ...]
            # or a top-level dict containing a list of findings.
            # Read the field the scanner actually writes.
            #
            # This used to be a recursive hunt for keys named 'probability',
            # 'confidence' or 'score'. scanner-pipeline.ipynb writes NONE of
            # those -- it emits a flat list under 'all_probabilities', plus
            # 'prob' inside each vulnerable_functions entry. So the search
            # matched nothing and the script exited with "No probability scores
            # found", silently, on every report. The .ipynb version had it
            # right; this .py was a bad port of it.
            #
            # Fail closed: a report without the key is an error, not an empty
            # contribution that quietly shrinks the corpus.
            if 'all_probabilities' not in data:
                raise KeyError(
                    f"{os.path.basename(file)} has no 'all_probabilities' key. "
                    f"Keys present: {sorted(data)}. Expected the output of "
                    f"scanner-pipeline.ipynb.")
            probs = [float(x) for x in data['all_probabilities']]

            # A report with zero functions is legitimate -- istark.vpn.starkreloaded
            # decompiles to a single source file with no extractable methods.
            declared = data.get('total_functions_scanned')
            if declared is not None and declared != len(probs):
                raise ValueError(
                    f"{os.path.basename(file)}: total_functions_scanned="
                    f"{declared} but all_probabilities has {len(probs)} entries.")
            
            apk_name = os.path.basename(file).replace('_vuln_report.json', '')
            flagged = sum(1 for p in probs if p >= THRESHOLD)
            apk_stats[apk_name] = {
                'scanned': len(probs),
                'flagged': flagged,
                'probs': probs
            }
            all_probs.extend(probs)
        except Exception as e:
            # Record and continue so every bad report is reported in one pass,
            # then fail below. Printing and carrying on would let the
            # calibration silently describe fewer APKs than were scanned --
            # which is what the all_probabilities guard above exists to stop.
            print(f"  ERROR reading {os.path.basename(file)}: {e}")
            _failures.append((os.path.basename(file), str(e)))

if _failures:
    raise RuntimeError(
        f"{len(_failures)} of {len(report_files)} reports could not be read; refusing to "
        f"produce a calibration over a partial corpus:\n  "
        + "\n  ".join(f"{n}: {m}" for n, m in _failures))

if not all_probs:
    raise RuntimeError(
        "No probability scores found. Every report parsed but none carried a populated "
        "'all_probabilities' list -- check the scanner actually ran inference.")

print(f"\nParsed {len(report_files)} reports, {len(all_probs):,} function probabilities total")

# --- 1. Text Report Generation ---
all_probs = np.array(all_probs)
total_funcs = len(all_probs)
mean_prob = np.mean(all_probs)
median_prob = np.median(all_probs)
std_prob = np.std(all_probs)

safe_pct = np.mean(all_probs < 0.10) * 100
uncertain_pct = np.mean((all_probs >= 0.10) & (all_probs < 0.60)) * 100
flagged_pct = np.mean(all_probs >= 0.60) * 100
highly_conf_pct = np.mean(all_probs > 0.90) * 100

report = "Test 9: Confidence Calibration - Real World Scanner\n"
report += "=" * 50 + "\n\n"
report += f"Total functions analysed: {total_funcs:,}\n"
report += f"Decision threshold: {THRESHOLD}\n\n"

report += "Distribution:\n"
report += f"  Mean: {mean_prob:.4f}\n"
report += f"  Median: {median_prob:.4f}\n"
report += f"  Std: {std_prob:.4f}\n"
report += f"  Confidently safe (prob < 0.10): {safe_pct:.1f}%\n"
report += f"  Uncertain (0.10 to {THRESHOLD}): {uncertain_pct:.1f}%\n"
report += f"  Flagged (prob >= {THRESHOLD}): {flagged_pct:.1f}%\n"
report += f"  Highly confident vuln (> 0.90): {highly_conf_pct:.1f}%\n\n"

report += "Per-APK breakdown:\n"
for apk, stats in sorted(apk_stats.items()):
    rate = (stats['flagged'] / stats['scanned']) * 100 if stats['scanned'] > 0 else 0.0
    report += f"  {apk}: {stats['scanned']} scanned, {stats['flagged']} flagged ({rate:.1f}%)\n"

report += "\nInterpretation:\n"
if median_prob < 0.1:
    report += "  Distribution is strongly concentrated near 0.0 with a small high-confidence tail.\n"
else:
    report += "  Distribution indicates potential over-flagging or uniform uncertainty.\n"

print(report)

# workspace_dir no longer exists -- see the search-root block above. On Kaggle
# write to /kaggle/working so the files land in the notebook output; as a script,
# write to <repo>/results.
if '__file__' in globals():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
elif os.path.isdir('/kaggle/working'):
    out_dir = '/kaggle/working'
else:
    out_dir = os.path.join(os.getcwd(), 'results')
print(f"Writing outputs to {out_dir}")
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, 'test9_scanner_calibration.txt'), 'w', encoding='utf-8') as f:
    f.write(report)

# --- 2. Graphical Generation ---
# Combined Histogram
plt.figure(figsize=(10, 6))
plt.hist(all_probs, bins=50, color='skyblue', edgecolor='black', alpha=0.7)
plt.axvline(THRESHOLD, color='red', linestyle='dashed', linewidth=2, label=f'Threshold ({THRESHOLD})')
plt.title('Global Probability Distribution (Scanner Findings)')
plt.xlabel('Vulnerability Probability')
plt.ylabel('Function Count (Log Scale)')
plt.yscale('log')
plt.legend()
plt.tight_layout()
plt.savefig(os.path.join(out_dir, 'test9_confidence_histogram.png'), dpi=300)
plt.close()

# Per-APK Histogram Grid (max 16 to fit)
num_apks = min(len(apk_stats), 16)
if num_apks > 0:
    cols = min(4, num_apks)
    rows = (num_apks + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 4, rows * 3))
    if num_apks == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for idx, (apk, stats) in enumerate(list(apk_stats.items())[:num_apks]):
        ax = axes[idx]
        if stats['scanned'] > 0:
            ax.hist(stats['probs'], bins=20, color='coral', edgecolor='black', alpha=0.7)
        ax.set_title(apk[:20] + '..', fontsize=10)
        ax.set_yscale('log')
        ax.axvline(THRESHOLD, color='red', linestyle='dashed', linewidth=1)
        ax.set_xticks([0.0, 0.5, 1.0])

    for i in range(num_apks, len(axes)):
        fig.delaxes(axes[i])

    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, 'test9_per_apk_histogram.png'), dpi=300)
    plt.close()

print(f"\nSaved calibration outputs to {out_dir}")
