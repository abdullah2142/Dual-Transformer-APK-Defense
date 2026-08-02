# 📝 Paper To-Do (2026-08-02)

**Status**: All experiments complete. All pre-writing tasks complete. Ready to write.
**Target**: MSR (primary) | EMSE/IST (fallback) | ASE tool track (also viable)

---

## ✅ Completed pre-writing tasks

### Task 1 — Statistical significance testing
- [x] McNemar's test on all within-backbone pairs → all p > 0.05 (null confirmed)
- [x] Cross-architecture pairs also tested → GCB+DFG vs CodeBERT+DFG significant (p≈0.0000)
- [x] Results saved to `results/test8_significance_results.txt`
- [x] Paper sentence unlocked: "Within-backbone DFG differences are not statistically
      significant (McNemar's test, all p > 0.05)."

### Task 1b — Multi-seed stability (Test 3)
- [x] Ran `test-3-seed42.ipynb`, `test-3-seed123.ipynb`, `test-3-seed2025.ipynb` on Kaggle
- [x] Results: 88.93% ± 0.10% accuracy, ROC 0.9598 ± 0.0009
- [x] Saved to `results/test3_seed*.txt`

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
| GCB text-only | 88.93%, ROC 0.9596, FN 1241 |
| CodeBERT | 88.56%, ROC 0.9610, FN 1180 |
| CodeBERT+DFG | 88.54%, ROC 0.9604, FN 1248 |
| UniXcoder | 89.08%, ROC 0.9622, FN 1238 |
| UniXcoder+DFG | 88.37%, ROC 0.9602, FN 1125 |
| LR + TF-IDF | 84.45%, ROC 0.9271, FN 1685 |
| MLP + TF-IDF | 85.48%, ROC 0.9385, FN 1425 |
| Test 2 ROC curves | Generated → `results/test2_roc_pr_curves.png` |
| Test 3 Stability | 88.93% ± 0.10%, ROC 0.9598 ± 0.0009 |
| Test 4 Per-source | LVDAndro 97.07%, Devign 68.91%, Juliet 100% |
| Test 5 MLP baseline | LR 84.45%, MLP 85.48% |
| Test 6 Imbalanced | GCB+DFG recall 94.14%, FPR 5.31% |
| Test 7 Qualitative | 8 patterns, P5a+P5b = 8/20 dominant |
| Test 8 Significance | All within-backbone p > 0.05 |
| Test 9 Scanner | 23,005 functions, 7.1% flagged |

---

## 🟢 Writing order (after Tasks 1 and 2)

- [ ] **Section 4** — Model comparison and empirical results ← START HERE
  - Table 1: full 8-model comparison (2 baselines + 6 transformers)
  - Table 2: cross-backbone DFG delta with p-values (GCB p=0.25, CB p=0.06, UX p=1.0)
  - Table 3: stability (88.93% ± 0.10%)
  - Draft sentences in RESEARCH_NOTES Part 6

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
LR + TF-IDF     84.45%   0.9271  0.9270   1,685 FN
MLP + TF-IDF    85.48%   0.9385  0.9408   1,425 FN
CodeBERT        88.56%   0.9610  0.9625   1,180 FN
CodeBERT+DFG    88.54%   0.9604  0.9622   1,248 FN
GCB Text        88.93%   0.9596  0.9611   1,241 FN
GCB+DFG         88.56%   0.9585  0.9597   1,196 FN
UniXcoder       89.08%   0.9622  0.9636   1,238 FN
UniXcoder+DFG   88.37%   0.9602  0.9612   1,125 FN
```

**Table 2 — Cross-backbone DFG delta**
```
CodeBERT   88.56%→88.54%   −0.02%   FN+68    p=0.0565
GCB        88.93%→88.56%   −0.37%   FN−45    p=0.2496
UniXcoder  89.08%→88.37%   −0.71%   FN−113   p=1.0000
```

**Table 3 — Stability**
```
88.93% ± 0.10%   ROC 0.9598 ± 0.0009
```

**Table 4 — Per-source**
```
LVDAndro  97.07%   0.9957   133 FN
Draper    86.67%   0.9264   303 FN
Juliet   100.00%   1.0000     0 FN
Devign    68.91%   0.7729   222 FN
```

**Table 5 — Imbalanced evaluation (90/10)**
```
GCB+DFG → Recall 94.14%   F1 0.7782   FPR 5.31%   FN 65
Ensemble → Recall 94.68%   F1 0.7675   FPR 5.78%   FN 59
```

**Table 6 — FN pattern distribution (top-20)**
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
