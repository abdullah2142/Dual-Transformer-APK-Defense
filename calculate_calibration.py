import os
import json
import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = "results"
OUTPUT_IMG = os.path.join(RESULTS_DIR, "test_c_confidence_histogram.png")

all_probs = []

# Read all JSON files in the results directory
for filename in os.listdir(RESULTS_DIR):
    if filename.endswith(".json"):
        filepath = os.path.join(RESULTS_DIR, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                if "all_probabilities" in data:
                    all_probs.extend(data["all_probabilities"])
        except Exception as e:
            print(f"Error reading {filename}: {e}")

if not all_probs:
    print("No probabilities found in the JSON files.")
    exit(1)

print(f"Successfully loaded {len(all_probs)} function probability scores across all APKs.")

# Plot the histogram
plt.figure(figsize=(10, 6))
counts, bins, patches = plt.hist(all_probs, bins=50, color='skyblue', edgecolor='black', alpha=0.7)

# Highlight the decision boundary
plt.axvline(x=0.45, color='red', linestyle='--', linewidth=2, label='Decision Boundary (0.45)')

plt.title('End-to-End Pipeline Confidence Calibration\n(Distribution of Inference Probabilities)', fontsize=14)
plt.xlabel('Vulnerability Probability Score', fontsize=12)
plt.ylabel('Number of Functions (Log Scale)', fontsize=12)
plt.yscale('log')
plt.legend()
plt.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig(OUTPUT_IMG, dpi=300)
print(f"Confidence calibration histogram saved to: {OUTPUT_IMG}")
