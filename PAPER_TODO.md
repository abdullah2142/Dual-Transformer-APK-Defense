# 📝 Paper To-Do

The paper combines three angles into one unified contribution:
1. **Dataset** — multi-source, cross-language Android vulnerability dataset
2. **Ablation** — quantified proof that DFG attention is essential (+3.11% acc, −25% FN)
3. **System** — DFG ensemble with threshold tuning for deployment-ready Android security

---

## 🔴 Critical (needed before submission)

- [ ] **Add baseline comparisons on your dataset**
  - CodeBERT alone ✅ (already done, 90.44%)
  - Simple MLP / TF-IDF baseline (lower bound)
  - At least one Android-specific tool: MaMaDroid or DLDroid
- [ ] **Evaluate on Devign test split in isolation** (no mixing with other datasets) — needed for apples-to-apples comparison with published numbers
- [ ] **Run Test 4 (multi-seed, 3 seeds)** to get mean ± std for all ablation metrics — turns single-run observations into statistical claims

---

## 🟠 High Priority

- [ ] **Imbalanced evaluation** — re-run final evaluation at a realistic 90% safe / 10% malicious ratio to show real-world robustness
- [ ] **Per-class / per-vulnerability-type breakdown** — which vulnerability categories (buffer overflow, use-after-free, logic errors) does DFG help most? Use LVDAndro labels for this analysis
- [ ] **Update README Results section** with Test 3 ablation numbers (DFG vs no-DFG table)
- [ ] **Push test notebooks** (test_2, test_3, test_4) to the repo once all are finalised

---

## 🟡 Medium Priority

- [ ] **Error analysis on misclassified samples** — inspect ~50 false negatives from GraphCodeBERT+DFG; identify patterns (e.g. long functions truncated, uncommon CWE types)
- [ ] **Calibration check** — plot confidence histogram for correct vs incorrect predictions to verify the model isn't overconfident
- [ ] **Threshold sensitivity table** — formalise the threshold sweep (Test 2 output) as a table showing precision/recall/F1 at 0.40, 0.45, 0.50, 0.55 for the paper

---

## 🟢 Polish / Writing

- [ ] Write Section 3 (Dataset Construction): sources, DFG pipeline, class balance, splits
- [ ] Write Section 4 (Ablation Study): DFG vs no-DFG, use `test3_ablation_bar.png` as Figure 1
- [ ] Write Section 5 (Ensemble): soft vs weighted vs hard voting, use `test2_roc_curve.png` and `test2_pr_curve.png` as figures
- [ ] Pick target venue:
  - **USENIX Security / Oakland (IEEE S&P)** — security-first framing
  - **ISSTA / ASE / ICSE** — software engineering + ML framing
  - **MSR** — if dataset is the primary contribution

---

## ✅ Already Done

- [x] 3-way train/val/test split with zero optimism bias (Test 1: −0.018%)
- [x] ROC-AUC 0.9804, PR-AUC 0.9803 for ensemble (Test 2)
- [x] DFG ablation: +3.11% accuracy, −282 FN vs no-DFG (Test 3)
- [x] Full ensemble comparison (standalone, 50/50, 70/30 weighted, triple soft/hard)
- [x] All results documented in README.md
