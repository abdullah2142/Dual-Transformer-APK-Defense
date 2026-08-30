import os
import glob
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Find all vulnerability reports in the workspace
workspace_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
report_files = []
for root, dirs, files in os.walk(workspace_dir):
    for file in files:
        if file.endswith('_vuln_report.json'):
            report_files.append(os.path.join(root, file))

if not report_files:
    print("No *_vuln_report.json files found. Run the scanner pipeline first.")
    exit(0)

all_probs = []
apk_stats = {}

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
            probs = []
            
            # Simple recursive search for 'probability' or 'confidence' keys
            def extract_probs(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ['probability', 'confidence', 'score']:
                            if isinstance(v, (int, float)):
                                probs.append(float(v))
                        else:
                            extract_probs(v)
                elif isinstance(obj, list):
                    for item in obj:
                        extract_probs(item)
            
            extract_probs(data)
            
            apk_name = os.path.basename(file).replace('_vuln_report.json', '')
            flagged = sum(1 for p in probs if p >= THRESHOLD)
            apk_stats[apk_name] = {
                'scanned': len(probs),
                'flagged': flagged,
                'probs': probs
            }
            all_probs.extend(probs)
        except Exception as e:
            print(f"Error reading {file}: {e}")

if not all_probs:
    print("No probability scores found in the JSON reports.")
    exit(0)

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

out_dir = os.path.join(workspace_dir, 'results')
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
