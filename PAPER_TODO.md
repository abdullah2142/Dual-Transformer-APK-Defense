# 📝 Paper To-Do

**Unified paper structure** — three angles:
1. **Ablation** — DFG-aware attention reduces missed malware by 25% (Test 3)
2. **System** — Ensemble + threshold tuning for deployment-ready Android security; end-to-end APK decompilation pipeline
3. **Dataset-as-vehicle** — 200k multi-source corpus enables large-scale DFG ablation; per-source analysis shows cross-corpus generalisability

---

## 🔴 Critical (needed before submission)

*(Test 6 baseline and Test 7 imbalanced evaluation completed and moved to Already Done)*

---

## 🟠 High Priority

- [ ] **APK decompilation pipeline** — end-to-end script:
  1. Decompile `.apk` → Java source with `jadx`
  2. Extract function bodies
  3. Generate DFGs via Tree-sitter (reuse existing pipeline)
  4. Classify with `model.bin`
  - This is the concrete system contribution; turns the paper from "model" to "working scanner"
  - Estimated: 2–3 weeks engineering work

---

## 🟡 Medium Priority

- [ ] **Error analysis on ~50 false negatives** — identify patterns (truncated functions, unusual CWE types, short code)
- [ ] **Calibration check** — confidence histogram for correct vs incorrect predictions
- [ ] **Threshold sensitivity table** — precision/recall/F1 at 0.40, 0.45, 0.50, 0.55 (formalise Test 2 output)
- [ ] **Update README** with per-source breakdown results once Test 5 is run

---

## 🟢 Writing

- [ ] Section 3: Dataset & Experimental Setup (sources, DFG pipeline, class balance, splits)
- [ ] Section 4: Ablation Study (DFG vs no-DFG — use `test3_ablation_bar.png` as Figure 1)
- [ ] Section 5: Ensemble & System (soft/weighted voting, threshold tuning, APK pipeline diagram)
- [ ] Section 6: Per-Source Analysis (cross-corpus generalisation table)
- [ ] Section 7: Baseline Comparison (Test 6) — Justify deep learning over traditional ML
- [ ] Section 8: Real-World Deployment / Imbalance (Test 7) — Frame model as high-recall triage filter
- [ ] Pick target venue:
  - **ISSTA / ASE / ICSE** — software engineering + ML framing (best fit)
  - **USENIX Security / IEEE S&P** — only if APK pipeline is complete
  - **MSR** — lighter venue, dataset + findings framing

---

## ✅ Already Done

- [x] 3-way train/val/test split — zero optimism bias (−0.018%) confirmed (Test 1)
- [x] ROC-AUC 0.9804, PR-AUC 0.9803 for ensemble (Test 2)
- [x] DFG ablation: +3.11% accuracy, −282 FN, −25% missed malware vs no-DFG (Test 3)
- [x] Multi-seed stability: 87.36% ± 0.27%, ROC 0.9559 ± 0.0004 across 3 seeds (Test 4)
- [x] Full ensemble comparison (standalone, 50/50, 70/30 weighted, triple soft/hard)
- [x] All 4 test notebooks + result images pushed to repo
- [x] README updated with all results and inline figures
- [x] Per-source accuracy breakdown (Test 5) — LVDAndro 99% vs Devign 66% gap transparently reported
- [x] MLP/TF-IDF baseline comparison (Test 6) — 71% reduction in false negatives vs MLP
- [x] Imbalanced evaluation 90/10 (Test 7) — 94.38% recall maintained, precision drops to 46.57%
