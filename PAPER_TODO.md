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
  - GCB+DFG vs UniXcoder (best vs ours)
- [ ] Expected result: all p > 0.05 (confirming null result is statistically valid)
- [ ] Record p-values — add to Section 4 ablation table
- [ ] Paper sentence to unlock: "Differences between all transformer configurations
      are not statistically significant (McNemar's test, p > 0.05 for all pairs)"

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
| GCB+DFG training | 88.71%, ROC 0.9616, FN 1184 |
| CodeBERT | 88.48%, ROC 0.9610, FN 1072 |
| CodeBERT+DFG | 88.45%, ROC 0.9609, FN 1089 |
| UniXcoder | 89.28%, ROC 0.9652, FN 1051 |
| UniXcoder+DFG | 89.40%, ROC 0.9651, FN 1043 |
| Test 2 ROC curves | Generated |
| Test 3 Ablation | Δ −0.01%, −10 FN (null) |
| Test 4 Stability | 87.53% ± 0.11% |
| Test 5 Per-source | LVD 98.34%, Dev 67.58% |
| Test 6 MLP | ~71% |
| Test 7 Imbalanced | Threshold 0.60, F1 0.6585 |
| Test 8 Qualitative | 1184 FNs, 8 patterns classified |
| Scanner | 13 APK reports, threshold 0.60 |

---

## 🟢 Writing order (after Tasks 1 and 2)

- [ ] **Section 4** — Model comparison and ablation ← START HERE
  - Table 1: full 6-model comparison
  - Table 2: ablation (null result)
  - Table 3: cross-backbone DFG delta (with p-values from Task 1)
  - Table 4: stability (87.53% ± 0.11%)
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
- [ ] **Section 2** — Related work
- [ ] **Section 9** — Conclusion
- [ ] **Section 1** — Introduction (write last)
- [ ] **Abstract** (write very last)

---

## 📊 All numbers ready for writing

**Table 1**
```
MLP/TF-IDF      ~71%      —       —        high FN
CodeBERT        88.48%   0.9610  0.9616   1,072 FN
CodeBERT+DFG    88.45%   0.9609  0.9616   1,089 FN
GCB+DFG (ours)  88.71%   0.9616  0.9622   1,184 FN
UniXcoder       89.28%   0.9652  0.9657   1,051 FN
UniXcoder+DFG   89.40%   0.9651  0.9657   1,043 FN
```

**Table 2**
```
GCB+DFG    88.71%   0.9616   1,184 FN
GCB no-DFG 88.72%   0.9612   1,194 FN
Δ          −0.01%  +0.0004    −10 FN   p=TBD (Task 1)
```

**Table 3 — Cross-backbone DFG delta**
```
CodeBERT   88.48%→88.45%   −0.03%   FN+17   p=TBD
GCB        88.72%→88.71%   −0.01%   FN−10   p=TBD
UniXcoder  89.28%→89.40%   +0.12%   FN−8    p=TBD
```

**Table 4 — Stability**
```
87.53% ± 0.11%   ROC 0.9565 ± 0.0003
```

**Table 5 — Per-source**
```
LVDAndro  98.34%   0.9978   51 FN
Draper    89.43%   0.9507  439 FN
Juliet   100.00%   1.0000    0 FN
Devign    67.58%   0.7633  449 FN
```

**Table 6 — Threshold sensitivity**
```
0.60 → Recall 83.41%   F1 0.6585   FPR 7.77%   FN 186
```

**Table 7 — FN pattern distribution (top-20)**
```
P5a (full obfuscation)       5/20
P1  (structural fragment)    4/20
P5b (Kotlin/lambda)          3/20
P7  (inter-procedural)       3/20
P2  (benign surface)         2/20
P3  (arithmetic edge case)   1/20
P6  (flag/control flow)      1/20
P4  (API semantic bypass)    1/20
```
