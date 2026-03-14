# 📝 Paper To-Do

**Unified paper structure** — three angles:
1. **Ablation** — DFG-aware attention reduces missed malware by 25% (Test 3) ← LEAD CONTRIBUTION
2. **Android-Domain Specialisation** — 99% on LVDAndro proves targeted Android fitness; Devign 66% reframed as expected domain gap, not generalisation failure
3. **Dataset-as-vehicle** — 200k multi-source corpus enables large-scale DFG ablation + transparent per-source analysis

> **Decisions made (2026-03-13)**:
> - Devign 66% → reframed as **Android specialisation finding**, NOT a cross-corpus generalisation claim
> - [ ] **Ensemble** — demoted to "reference baseline" (gap too small: +0.05% acc, −144 FN vs standalone GCB; GCB achieves higher F1 in imbalanced scenarios)
> - Compare with **LineVul** and **VulBERTa** on our exact test split ← new High Priority task

---

## 🔴 Critical (needed before submission)

- [ ] **Section drafting** — start with Section 4 (Ablation). Everything else builds from it.

---

## 🟠 High Priority

- [x] **Run Kaggle scanner pipeline** — re-run `scanner-pipeline-previous.ipynb` to obtain the exact `all_probabilities` array for the 23k+ scanned functions.
- [x] **Regenerate Test C graph** — use the updated JSON reports to plot the exact Test C confidence histogram (replacing the exponential decay approximation).
- [ ] **Run LineVul on our test split** — clone `davidhin/linevul`, load their checkpoint, evaluate on our 39,993-sample held-out test set with standard 0.5 threshold. Record Accuracy / FN / FP / F1.
- [ ] **Run VulBERTa on our test split** — same procedure using `ChengyueLiu/vulberta` at 0.5 threshold. Both models operate on single functions, same as us, so comparison is principled.
- [ ] **Write the comparison table** — format: `Model | Accuracy | FN | ROC-AUC | Training Data`, with a note that our numbers are not cherry-picked because all models are evaluated on the same split we trained on.
- [x] **Rewrite README Sections 8, 9, 10** — update the main repository README with the latest baseline comparisons, qualitative findings, and narrative framing (Section 10 done).

---

## 🟡 Medium Priority

- [ ] **Rewrite Section 5 / Contribution 2** — focus on Standalone GraphCodeBERT + DFG as the primary system. One sentence: "We adopt Standalone GraphCodeBERT + DFG as the production system due to its optimal balance of F1 performance (0.9182), high recall, and 2x inference throughput compared to ensemble variants."
- [ ] **Rewrite Devign section** — use new framing: "Android-Domain Specialisation". Move Devign 66% to Limitations. LVDAndro 99% becomes the headline for Section 6.
- [ ] **Qualitative error analysis write-up** (Test 8 done) — 5 failure patterns identified; write 2–3 paragraphs for Limitations section (see analysis in research notes §9)

---

## 🟢 Writing

- [ ] Section 3: Dataset & Experimental Setup (sources, DFG pipeline, class balance, splits)
- [ ] Section 4: Ablation Study (DFG vs no-DFG — use `test3_ablation_bar.png` as Figure 1; ensemble as a baseline comparison variant)
- [ ] Section 5: System Architecture (threshold tuning, APK pipeline diagram, Kotlin support)
- [ ] Section 6: Per-Source Analysis — **reframed** as Android specialisation; LVDAndro 99% headline; Devign gap moved to Limitations
- [ ] Section 7: Baseline Comparison (Test 6 + LineVul/VulBERTa comparison table)
- [ ] Section 8: Real-World Deployment / Imbalance (Test 7) — frame Standalone GCB as high-recall triage filter (F1: 0.6585)
- [ ] Section 9: Limitations — include 5 FN patterns from Test 8 qualitative analysis
- [ ] Pick target venue:
  - **ISSTA / ASE / ICSE** — best fit after adding comparison table
  - **MSR** — fallback if comparison table can't be completed in time

---

## ✅ Already Done

- [x] 3-way train/val/test split — zero optimism bias (−0.018%) confirmed (Test 1)
- [x] ROC-AUC 0.9798, PR-AUC 0.9797 for Standalone GraphCodeBERT (Test 2)
- [x] DFG ablation: +3.11% accuracy, −282 FN, −25% missed malware vs no-DFG (Test 3)
- [x] Multi-seed stability: 87.36% ± 0.27%, ROC 0.9559 ± 0.0004 across 3 seeds (Test 4)
- [x] Full ensemble comparison (standalone, 50/50, 70/30 weighted, triple soft/hard)
- [x] Per-source accuracy breakdown (Test 5) — LVDAndro 99% vs Devign 66% gap transparently reported
- [x] MLP/TF-IDF baseline comparison (Test 6) — 71% reduction in false negatives vs MLP
- [x] Imbalanced evaluation 90/10 (Test 7) — 93.13% recall maintained, F1 score 0.6585 (Standalone GCB)
- [x] **Qualitative Error Analysis (Test 8)** — 663 FNs analysed; 5 failure patterns identified and documented
- [x] APK decompilation pipeline — end-to-end scanner script deployed natively on Kaggle (now with Kotlin + manifest-aware filtering)
- [x] Calibration check — confidence histogram for correct vs incorrect predictions
- [x] Threshold sensitivity table — precision/recall/F1 at 0.40, 0.45, 0.50, 0.55
- [x] End-to-End Inference System (Test A & B) — built Kaggle notebook with batch GPU inference
- [x] Obfuscation Degradation Test (Test D) — ProGuard defeats targeted package filtering
- [x] Confidence calibration in the wild (Test C) — 23,005 individual Java and Kotlin functions, near-zero false-positive hallucinations
