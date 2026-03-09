import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import os

os.makedirs('results', exist_ok=True)

# ------------------------------------------------------------------
# 1. Replot Test 5: Per-Source
# ------------------------------------------------------------------
sources = ['Devign', 'Draper', 'LVDAndro', 'Juliet']
accs = [0.664274, 0.895670, 0.990083, 1.000000]
aucs = [0.7417, 0.9541, 0.9988, 1.0000]
f1s  = [0.6643, 0.8957, 0.9901, 1.0000]

x = np.arange(len(sources))
width = 0.25
colors = ['#4C72B0', '#55A868', '#C44E52']

fig, ax = plt.subplots(figsize=(10, 5))
b1 = ax.bar(x - width, accs, width, label='Accuracy', color=colors[0])
b2 = ax.bar(x,         aucs, width, label='ROC-AUC',  color=colors[1])
b3 = ax.bar(x + width, f1s,  width, label='F1 (macro)',color=colors[2])

for bar in [b1, b2, b3]:
    for rect in bar:
        h = rect.get_height()
        ax.annotate(f'{h:.3f}',
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords='offset points',
                    ha='center', va='bottom', fontsize=8)

ax.set_xticks(x)
ax.set_xticklabels(['Devign\n(C/C++ QEMU/FFmpeg)', 'Draper\n(C/C++ NVD/SARD)', 'LVDAndro\n(Android Java/C)', 'Juliet\n(Synthetic C/C++)'], fontsize=10)
ax.set_ylim(0.50, 1.05) # Adjusted scale so Devign (0.66) is totally visible but differences are still clear
ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
ax.set_title('Per-Source Accuracy Breakdown (GraphCodeBERT + DFG)', fontsize=13, fontweight='bold')
ax.legend(loc='lower right')
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('results/test5_per_source_bar.png', dpi=150, bbox_inches='tight')
plt.close()

# ------------------------------------------------------------------
# 2. Replot Test 6: Baseline Comparison
# ------------------------------------------------------------------
models = ['LR + TF-IDF', 'MLP + TF-IDF', 'GraphCodeBERT + DFG']
accs_6 = [0.842719, 0.855321, 0.918200]
aucs_6 = [0.9275, 0.9398, 0.9798]
f1s_6  = [0.8405, 0.8554, 0.9182]

x_6 = np.arange(len(models))

fig2, ax2 = plt.subplots(figsize=(8, 5))
b1_6 = ax2.bar(x_6 - width, accs_6, width, label='Accuracy', color=colors[0])
b2_6 = ax2.bar(x_6,         aucs_6, width, label='ROC-AUC',  color=colors[1])
b3_6 = ax2.bar(x_6 + width, f1s_6,  width, label='F1 (macro)',color=colors[2])

for bar in [b1_6, b2_6, b3_6]:
    for rect in bar:
        h = rect.get_height()
        ax2.annotate(f'{h:.3f}',
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords='offset points',
                    ha='center', va='bottom', fontsize=9)

ax2.set_xticks(x_6)
ax2.set_xticklabels(models, fontsize=11)
ax2.set_ylim(0.70, 1.02) # Adjusted scale to strongly magnify differences among 0.84-0.97
ax2.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
ax2.set_title('Baseline Model Comparison (Lower Bound Test)', fontsize=13, fontweight='bold')
ax2.legend(loc='lower right')
ax2.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('results/test6_baseline_bar.png', dpi=150, bbox_inches='tight')
plt.close()

print("Recreated both bar charts with magnified and corrected scaling.")
