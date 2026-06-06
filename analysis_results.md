# Retrained Models: Results Comparison & Action Items

## Methodology Changes (Original → Retrained)

| Setting | Original | Retrained |
|---|---|---|
| Epochs | 3 (fixed) | 5 (ceiling) |
| Checkpoint selection | Final epoch (no selection) | Best validation accuracy (early stopping) |
| Validation set | None | 8% stratified split |
| Split | 90/10 train/test | 82/8/10 train/val/test |
| Patience | N/A | 2 epochs |
| Data used for training | 90% of data | 82% of data |

> [!IMPORTANT]
> The retrained models use **validation-based early stopping**, which is a fundamental methodology change from the original "no checkpoint selection" approach. This changes a key design decision documented in [RESEARCH_NOTES.md](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/RESEARCH_NOTES.md#L422-L429) (Decision 3) that was specifically chosen to eliminate differential optimism bias.

---

## Results Comparison (Final Test Set — 19,996 samples)

### Individual Model Results

| Model | Metric | Original | Retrained | Delta | Direction |
|---|---|---|---|---|---|
| **CodeBERT (text)** | Accuracy | 88.4777% | 88.5627% | +0.085% | ↑ |
| | ROC-AUC | 0.9610 | 0.9610 | 0.0000 | = |
| | PR-AUC | 0.9616 | 0.9625 | +0.0009 | ↑ |
| | FN | 1,072 | 1,180 | +108 | ↓ worse |
| | FP | 1,232 | 1,107 | −125 | ↑ better |
| | Best Epoch | 3 (fixed) | 4 (early stop) | — | — |
| **CodeBERT + DFG** | Accuracy | 88.4477% | 88.5427% | +0.095% | ↑ |
| | ROC-AUC | 0.9609 | 0.9604 | −0.0005 | ↓ |
| | PR-AUC | 0.9616 | 0.9622 | +0.0006 | ↑ |
| | FN | 1,089 | 1,248 | +159 | ↓ worse |
| | FP | 1,221 | 1,043 | −178 | ↑ better |
| | Best Epoch | 3 (fixed) | 4 (early stop) | — | — |
| **GraphCodeBERT (text)** | Accuracy | 88.7177%* | 88.9300% | +0.212% | ↑ |
| | ROC-AUC | 0.9612* | 0.9596 | −0.0016 | ↓ |
| | PR-AUC | 0.9618* | 0.9611 | −0.0007 | ↓ |
| | FN | 1,194* | 1,241 | +47 | ↓ worse |
| | FP | 1,062* | 972 | −90 | ↑ better |
| | Best Epoch | 3 (fixed) | 5 (early stop) | — | — |
| **GraphCodeBERT + DFG** | Accuracy | 88.7077% | 88.5600% | −0.148% | ↓ |
| | ROC-AUC | 0.9616 | 0.9585 | −0.0031 | ↓ |
| | PR-AUC | 0.9622 | 0.9597 | −0.0025 | ↓ |
| | FN | 1,184 | 1,196 | +12 | ↓ worse |
| | FP | 1,074 | 1,091 | +17 | ↓ worse |
| | Best Epoch | 3 (fixed) | 5 (early stop) | — | — |
| **UniXcoder (text)** | Accuracy | 89.2829% | 89.0778% | −0.205% | ↓ |
| | ROC-AUC | 0.9652 | 0.9622 | −0.0030 | ↓ |
| | PR-AUC | 0.9657 | 0.9636 | −0.0021 | ↓ |
| | FN | 1,051 | 1,238 | +187 | ↓ worse |
| | FP | 1,092 | 946 | −146 | ↑ better |
| | Best Epoch | 3 (fixed) | 4 (early stop) | — | — |
| **UniXcoder + DFG** | Accuracy | 89.4029% | 88.3727% | −1.030% | ↓↓ |
| | ROC-AUC | 0.9651 | 0.9602 | −0.0049 | ↓ |
| | PR-AUC | 0.9657 | 0.9612 | −0.0045 | ↓ |
| | FN | 1,043 | 1,125 | +82 | ↓ worse |
| | FP | 1,076 | 1,200 | +124 | ↓ worse |
| | Best Epoch | 3 (fixed) | 4 (early stop) | — | — |

_*GraphCodeBERT text-only was the "GCB no-DFG" ablation condition from test-3._

---

### DFG Delta Analysis (New)

| Backbone | Text-only (New) | DFG-aware (New) | Δ Accuracy | Δ FN | vs Original Δ |
|---|---|---|---|---|---|
| CodeBERT | 88.5627% | 88.5427% | **−0.020%** | +68 | Was −0.03% |
| GraphCodeBERT | 88.9300% | 88.5600% | **−0.370%** | −45 | Was −0.01% |
| UniXcoder | 89.0778% | 88.3727% | **−0.705%** | −113 | Was +0.12% |

> [!WARNING]
> The DFG delta story has changed significantly:
> - **GraphCodeBERT**: DFG now *hurts* by 0.37% (was essentially neutral at −0.01%)
> - **UniXcoder**: DFG now *hurts* by 0.71% (was *helping* by +0.12%)
> - **CodeBERT**: Still essentially neutral (−0.02% vs −0.03%)
>
> The null result is now potentially a **negative result** — DFG consistently hurts on decompiled code. This may strengthen the paper's narrative but changes key claims.

---

### Key Observations

1. **Accuracy band shifted**: Models now span 88.37%–89.08% (was 88.45%–89.40%). The band is wider (0.71pp vs 0.95pp), and the top performer changed.
2. **Best model changed**: GraphCodeBERT text-only (88.93%) is now the best, not UniXcoder text-only (was 89.28%).
3. **FN counts universally increased**: Every model now has MORE false negatives (range: +12 to +187). This is because the models are now more conservative (fewer FP) but miss more vulnerabilities.
4. **FP counts mostly decreased**: The models are making fewer false alarms, at the cost of more missed vulnerabilities. This suggests the validation-based checkpoint selection is selecting models that are better calibrated toward the "safe" class.
5. **UniXcoder + DFG degraded most**: Dropped from best performer (89.40%) to worst performer (88.37%), a full 1.03% drop.
6. **ROC-AUC/PR-AUC generally decreased**: Most models show small decreases in AUC metrics.

---

## What Needs To Be Redone

### 🔴 Priority 1 — Must redo (results directly changed)

#### 1. Update all result text files in `results/`
The following files contain hardcoded old numbers that are now wrong:
- [codebert_results.txt](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/results/codebert_results.txt)
- [codebert_dfg_results.txt](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/results/codebert_dfg_results.txt)
- [graphcodebert_results.txt](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/results/graphcodebert_results.txt)
- [unixcoder_results.txt](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/results/unixcoder_results.txt)
- [unixcoder_dfg_results.txt](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/results/unixcoder_dfg_results.txt)

**Action**: Update each file with the new Final Test numbers from the retrained notebooks.

#### 2. Re-run Test 2 — ROC-AUC curves ([test-2-roc-auc.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-2-roc-auc.ipynb))
- Needs new `test_probs.npy` and `test_labels.npy` from all retrained models
- Will regenerate: `test2_auc_results.txt`, `test2_roc_curve.png`, `test2_pr_curve.png`, `test2_confidence_histogram.png`
- The "Best F1 Threshold" value will change

#### 3. Re-run Test 3 — DFG Ablation ([test-3-ablation.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-3-ablation.ipynb))
- The ablation delta has changed dramatically (GCB+DFG vs GCB text: was −0.01%, now −0.37%)
- Will regenerate: `test3_ablation_results.txt`, `test3_ablation_bar.png`
- **This is narratively important** — the null result may now be a clearly negative result

#### 4. Re-run Test 5 — Per-source breakdown ([test-5-per-source.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-5-per-source.ipynb))
- Per-source accuracy (LVDAndro, Draper, Devign, Juliet) will change with new models
- Will regenerate: `test5_per_source_results.txt`, `test5_per_source_bar.png`

#### 5. Re-run Test 6 — MLP/TF-IDF Baseline comparison ([test-6-mlp-baseline.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-6-mlp-baseline.ipynb))
- The transformer rows in the comparison table need new numbers
- May need to re-run baselines too if the data split changed (82/8/10 vs 90/10)
- Will regenerate: `test6_baseline_results.txt`, `test6_baseline_bar.png`

> [!CAUTION]
> The MLP/TF-IDF baselines were trained on the 90/10 split. If you want a fair comparison, baselines must be retrained on the same 82/8/10 split. Otherwise, the baselines saw more training data than the transformers.

#### 6. Re-run Test 7 — Imbalanced evaluation ([test-7-imbalanced-eval.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-7-imbalanced-eval.ipynb))
- Threshold sensitivity will shift with new probability distributions
- The optimal threshold (0.60) may change
- Will regenerate: `test7_imbalanced_results.txt`, `test7_precision_recall_bar.png`
- **Impacts scanner pipeline threshold** if the optimal threshold changes

#### 7. Re-run Test 9 — Statistical significance testing ([test-9-significance-testing.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-9-significance-testing.ipynb))
- McNemar's test results will change because prediction vectors changed
- The GCB+DFG vs UniXcoder+DFG comparison previously showed p=0.0002 (significant) — this may change
- Will regenerate: `test9_significance_results.txt`

---

### 🟡 Priority 2 — Must redo (downstream effects)

#### 8. Re-run Test 4 — Multi-seed stability ([test_4_multiseed.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test_4_multiseed.ipynb))
- The stability estimate (87.53% ± 0.11%) was for the old methodology
- With validation-based early stopping, variance characteristics change
- Will regenerate: `test4_multiseed_results.txt`, `test4_multiseed_errorbar.png`

#### 9. Re-run Test 8 — Qualitative false negative analysis ([test-8-qualitative-analysis.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/test_notebooks/test-8-qualitative-analysis.ipynb))
- The set of false negatives changed (different FN counts, different predictions)
- The "top-20 most confident FNs" will be different samples
- The pattern classification (P1–P7, P5a, P5b) distribution may change
- **This is narratively central** — the FN analysis is Section 8 of the paper

#### 10. Re-run scanner pipeline with new model ([scanner-pipeline-final.ipynb](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/scanner-pipeline-final.ipynb))
- The scanner uses a trained model checkpoint — needs the new one
- If threshold changes (from re-running Test 7), the scanner must use the new threshold
- Will regenerate all APK vulnerability reports

#### 11. Re-run Test C — Confidence calibration ([test_c_calibration_newmodel.txt](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/results/test_c_calibration_newmodel.txt))
- Depends on scanner pipeline output (step 10)
- Distribution stats (89.2% below 0.10, 5.6% above 0.60, etc.) will change
- Will regenerate: `test_c_calibration_newmodel.txt`, histogram PNGs

---

### 🟢 Priority 3 — Must update (documentation)

#### 12. Update [RESEARCH_NOTES.md](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/RESEARCH_NOTES.md)
- **Part 2** — All numbers in the comparison table (lines 44-53), delta analysis (lines 59-65), Test 3-8 summaries
- **Part 4, Decision 3** — The "no validation set" rationale no longer applies; you now HAVE a validation set with early stopping. This entire design decision needs to be rewritten or removed.
- **Part 5** — Draft paper sentences contain hardcoded numbers (e.g., "88.45%–89.40%", "1,184 false negatives", "87.53% ± 0.11%")
- **Part 6** — Quick reference numbers table is entirely stale

#### 13. Update [PAPER_TODO.md](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/PAPER_TODO.md)
- The "All experimental results complete" table (lines 48-62) has old numbers
- Tables 1-7 in "All numbers ready for writing" section (lines 94-146) are stale
- The paper sentence about "no checkpoint selection" (Decision 3) contradicts the new methodology

#### 14. Reconsider paper narrative framing
- The paper originally claimed a **null result** (DFG provides no benefit)
- The retrained results show a **negative result** (DFG consistently hurts: −0.02%, −0.37%, −0.71%)
- The key paper sentence "no consistent benefit" could become "DFG-aware attention consistently **degrades** performance on decompiled code"
- The mechanistic explanation (P5a obfuscation) still holds, and is arguably **stronger** now
- The 1,184 FN count used throughout Section 8 will change

#### 15. Update [LIMITATIONS.md](file:///home/ishu/Codes/Dual-Transformer-APK-Defense/LIMITATIONS.md) if any limitations are tied to specific numbers

---

## Recommended Execution Order

```
1. Download all test_probs.npy / test_labels.npy from Kaggle for all 6 retrained models
2. Update results/*.txt files with new numbers
3. Re-run Test 2 (ROC curves)
4. Re-run Test 3 (Ablation) ← check if null → negative
5. Re-run Test 9 (Significance) ← needs test_probs from step 1
6. Re-run Test 4 (Multi-seed) ← needs full retraining with 3 seeds
7. Re-run Test 5 (Per-source)
8. Re-run Test 6 (Baselines) ← may need to retrain baselines on new split
9. Re-run Test 7 (Imbalanced) ← check if threshold 0.60 still optimal
10. Re-run Test 8 (Qualitative FN analysis) ← needs new FN set
11. Re-run scanner pipeline with new model + new threshold
12. Re-run Test C (Calibration) ← after scanner
13. Update RESEARCH_NOTES.md, PAPER_TODO.md
14. Reassess paper narrative (null vs negative result)
```

> [!IMPORTANT]
> **Step 6 (Multi-seed)** requires retraining the model 3 times with different seeds using the new methodology (validation split + early stopping). This is compute-intensive and needs to be done on Kaggle/GPU.
>
> **Step 8 (Baselines)** may require retraining MLP/LR baselines on the new 82/8/10 split for a fair comparison.
