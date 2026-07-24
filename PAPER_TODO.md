# 📝 Paper To-Do (2026-03-22)

**Status**: All experiments complete. One pre-writing task remains. Then write.
**Target**: MSR (primary) | EMSE/IST (fallback) | ASE tool track (also viable)

---

## 🔴 Must do before writing (1 task)

### Task 1 — Statistical significance testing
- [ ] Create a short notebook that loads `test_probs.npy` + `test_labels.npy` from
      each training run
- [ ] Run McNemar's test on every model pair from Table 3:
  - GCB+DFG vs GCB no-DFG
  - CodeBERT vs CodeBERT+DFG
  - UniXcoder vs UniXcoder+DFG
  - GCB Text vs GCB+DFG
- [ ] Expected result: all p > 0.05 (confirming null result is statistically valid)
- [ ] Record p-values — add to Section 4 ablation table
- [ ] Paper sentence to unlock: "Differences between all transformer configurations
      are not statistically significant (McNemar's test, p > 0.05 for all pairs)"
      *Note: Must be re-run with latest `.npy` files from the re-train to confirm.*

### Task 1b — Re-run Test 3 (Multi-seed stability)
- [ ] Run `test-3-seed42.ipynb`, `test-3-seed123.ipynb`, and `test-3-seed2025.ipynb` on Kaggle in parallel.
- [ ] The original notebook timed out at 12 hours. It is now split into three with `tqdm` output suppressed.
- [ ] After they finish, run `test_scripts/test_3_multiseed.py` (or a local aggregator script) to get the final mean/std numbers.

```python
from statsmodels.stats.contingency_tables import mcnemar
preds_a = (probs_a[:, 1] >= 0.5).astype(int)
preds_b = (probs_b[:, 1] >= 0.5).astype(int)
b = np.sum((preds_a == labels) & (preds_b != labels))
c = np.sum((preds_a != labels) & (preds_b == labels))
result = mcnemar([[0, b], [c, 0]], exact=False)
print(f"p = {result.pvalue:.4f}")
```

## ✅ Completed pre-writing task

### Task 2 — Confidence calibration histogram (new model)
- [x] Replaced the notebook plan with `test_c_calibration_newmodel.py`
- [x] Auto-discovered all downloaded `*_vuln_report.json` files in the workspace
- [x] Generated `test_c_confidence_histogram_newmodel.png`
- [x] Generated `test_c_per_apk_histogram_newmodel.png`
- [x] Generated `test_c_calibration_newmodel.txt`
- [x] Verified non-flat calibration on 13 APK reports / 23,005 functions
- [x] Final aggregate: 89.2% below 0.10, 5.6% at or above 0.60, 4.1% above 0.90

---

## ✅ All experimental results complete

| Test | Result |
|---|---|
| GCB+DFG training | 88.56%, ROC 0.9585, FN 1196 |
| CodeBERT | 88.56% |
| CodeBERT+DFG | 88.54% |
| UniXcoder | 89.08% |
| UniXcoder+DFG | 88.37% |
| Test 2 ROC curves | Generated |
| Test 3 Stability | [TBD] |
| Test 4 Per-source | [TBD] |
| Test 5 MLP | [TBD] |
| Test 6 Imbalanced | [TBD] |
| Test 7 Qualitative | [TBD] |
| Scanner | [TBD] |

---

## 🟢 Writing order (after Tasks 1 and 2)

- [ ] **Section 4** — Model comparison and empirical results ← START HERE
  - Table 1: full 6-model comparison
  - Table 2: cross-backbone DFG delta (with p-values from Task 1)
  - Table 3: stability (87.53% ± 0.11%)
  - Draft sentences in RESEARCH_NOTES Part 5

- [ ] **Section 8** — Limitations and qualitative analysis ← WRITE ALONGSIDE 4
  - 8 failure patterns with paper paragraphs from RESEARCH_NOTES Part 3
  - P5a + P5b = 8/20 dominant failures — the mechanistic link to Section 4
  - Concrete examples: class_336, method_1192, field_1000
  - P1, P7, P2, P3, P6, P4 with paragraphs

- [ ] **Section 3** — Dataset and pipeline
- [ ] **Section 6** — Per-source analysis
- [ ] **Section 5** — System architecture (threshold 0.60)
- [ ] **Section 7** — Real-world deployment (scanner + calibration histogram from script output)
  - [ ] Configure `test_scripts/scanner-pipeline.ipynb` to use the best empirical model (UniXcoder Text-only or UniXcoder+DFG).
- [ ] **Section 2** — Related work
- [ ] **Section 9** — Conclusion
- [ ] **Section 1** — Introduction (write last)
- [ ] **Abstract** (write very last)

---

## 📊 All numbers ready for writing

**Table 1**
```
MLP/TF-IDF      [TBD]      [TBD]  [TBD]   [TBD] FN
CodeBERT        88.56%   0.9610  0.9625   1,180 FN
CodeBERT+DFG    88.54%   0.9604  0.9622   1,248 FN
GCB Text        88.93%   0.9596  0.9611   1,241 FN
GCB+DFG         88.56%   0.9585  0.9597   1,196 FN
UniXcoder       89.08%   0.9622  0.9636   1,238 FN
UniXcoder+DFG   88.37%   0.9602  0.9612   1,125 FN
```

**Table 2 — Cross-backbone DFG delta**
```
CodeBERT   88.56%→88.54%   −0.02%   FN+68    p=TBD
GCB        88.93%→88.56%   −0.37%   FN−45    p=TBD
UniXcoder  89.08%→88.37%   −0.71%   FN−113   p=TBD
```

**Table 3 — Stability**
```
[TBD] ± [TBD]   ROC [TBD] ± [TBD]
```

**Table 4 — Per-source**
```
LVDAndro  [TBD]   [TBD]   [TBD] FN
Draper    [TBD]   [TBD]  [TBD] FN
Juliet   [TBD]   [TBD]    [TBD] FN
Devign    [TBD]   [TBD]  [TBD] FN
```

**Table 5 — Threshold sensitivity**
```
0.60 → Recall [TBD]   F1 [TBD]   FPR [TBD]   FN [TBD]
```

**Table 6 — FN pattern distribution (top-20)**
```
P5a (full obfuscation)       [TBD]/[TBD]
P1  (structural fragment)    [TBD]/[TBD]
P5b (Kotlin/lambda)          [TBD]/[TBD]
P7  (inter-procedural)       [TBD]/[TBD]
P2  (benign surface)         [TBD]/[TBD]
P3  (arithmetic edge case)   [TBD]/[TBD]
P6  (flag/control flow)      [TBD]/[TBD]
P4  (API semantic bypass)    [TBD]/[TBD]
```
