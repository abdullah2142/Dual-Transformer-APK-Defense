# 📝 Paper To-Do

**Unified paper structure — three angles:**
1. **Ablation** — DFG-aware attention reduces missed malware by ~28% (Test 3, updated) ← LEAD CONTRIBUTION
2. **Android-Domain Specialisation** — 99% on LVDAndro proves targeted Android fitness; Devign 66% reframed as expected domain gap, not generalisation failure
3. **Dataset-as-vehicle** — 200k multi-source corpus with parsed DFGs enables large-scale structural ablation + transparent per-source analysis

> **Decisions locked:**
> - All controlled comparisons use **72/8/20 split, seed 42, sizes 143971/15996/39993**
> - Production model uses **3 epochs + gradient clipping** — to be retrained with clean split
> - Ablation (Test 3) and baselines all use **3 epochs** under identical conditions
> - Test 4 stays at **1 epoch**, reframed as optimisation stability probe (not final accuracy)
> - **Standalone GCB+DFG** is primary system; ensemble reported as sensitivity variant
> - Devign 66% → Limitations section only; LVDAndro 99% → Section 6 headline
> - LineVul / VulBERTa → **closed** (unavailable); replaced by ReGVD as graph-based baseline
> - MobSF comparison uses **vulnerable function rate** (not binary APK verdict)
> - Recall figure corrected: **93.13%** (standalone GCB, Test 7) — not 94.38%

---

## 🔴 Phase 1 — Retrain foundation (everything depends on this)

- [ ] **Retrain model2 with clean split** — modify training notebook:
  - Replace unseeded 90/10 split with `torch.Generator().manual_seed(42)`, sizes `143971/15996/39993`
  - Add gradient clipping (`scaler.unscale_(optimizer)` + `clip_grad_norm_(..., 1.0)`) before `scaler.step()`
  - Keep all other hyperparameters identical: `lr=2e-5`, `batch_size=16`, `num_train_epochs=3`
  - Save new checkpoint — this becomes the new model2 used everywhere
  - Runtime: ~5–8 hours on Kaggle GPU

---

## 🔴 Phase 2 — Fix and rerun ablation (depends on Phase 1)

- [ ] **Update Test 3 notebook** — now that new model2 matches ablation conditions:
  - Revert Condition A back to **loading new model2 checkpoint** (no need to train inside notebook)
  - Remove `train_with_dfg()`, `train_ds_dfg`, `val_ds_dfg` — no longer needed
  - Keep Condition B (`train_no_dfg()`) with 3 epochs, same split, gradient clipping
  - Confirm `num_train_epochs = 3` in Args
  - Confirm `val_ratio` comment corrected to 8% (not 10%)
  - Confirm hardcoded split sizes match: `train_n=143971, val_n=15996, test_n=39993`
  - Rerun and save new `test3_ablation_results.txt`
  - Update paper numbers: accuracy delta, ROC-AUC delta, FN reduction (~28%)

---

## 🔴 Phase 3 — Rerun all dependent tests (depends on Phase 1, can parallelise)

- [ ] **Rerun Test 2** — ROC-AUC and PR-AUC with new model2
  - Expected: ROC-AUC ~0.979, PR-AUC ~0.979 (may shift slightly)
  - Update PAPER_TODO numbers after run

- [ ] **Rerun Test 5** — per-source breakdown with new model2
  - Check LVDAndro 99% headline still holds
  - Check Devign gap still present (expected yes — architectural, not split-dependent)

- [ ] **Rerun Test 7** — imbalanced evaluation with new model2
  - Report standalone GCB numbers only as primary
  - Ensemble row as sensitivity variant
  - Confirm recall figure — target ~93% range
  - Update Section 8 framing accordingly

- [ ] **Rerun Test 8** — false negative analysis with new model2
  - New FN count will differ from 663 — update
  - Re-check whether 7 qualitative patterns still hold
  - If pattern distribution shifts, update Limitations section notes

---

## 🟠 Phase 4 — Fix Test 4 (independent, do anytime)

- [ ] **Fix Test 4 split and rerun** — already identified fix:
  - Move `random_split` outside the for loop
  - Fix generator: `torch.Generator().manual_seed(42)`
  - Keep `num_train_epochs = 1`
  - Fix `val_ratio` comment: change `0.10` note to `0.08`
  - Reframe in paper as **optimisation stability probe**: "variance across random initialisations after one epoch of fine-tuning"
  - Update numbers in TODO after run (previous stale numbers: 87.12% ± 0.16%, ROC 0.9543 ± 0.0003)

---

## 🟠 Phase 5 — Build unified baseline comparison (depends on Phase 1)

- [ ] **Build unified baseline notebook** — one notebook, three models:
  - **CodeBERT** (`microsoft/codebert-base`) — same `SimpleModel` architecture as training notebook
  - **UnixCoder** (`microsoft/unixcoder-base`) — identical to CodeBERT, swap model name and tokenizer
  - **ReGVD** (`rebuff/regvd-model`) — graph-based baseline; needs its own forward pass, same training loop
  - All three: 72/8/20 split, seed 42, 3 epochs, `lr=2e-5`, `batch_size=16`, gradient clipping
  - Evaluate all three on same held-out `test_ds` (39,993 samples)
  - Report: Accuracy, ROC-AUC, PR-AUC, FN, FP at threshold 0.45

- [ ] **Write comparison table** (Section 7):

  | Model | Structure-aware | Accuracy | ROC-AUC | FN |
  |---|---|---|---|---|
  | MLP / TF-IDF | No | ~71% | — | high |
  | CodeBERT | No | TBD | TBD | TBD |
  | UnixCoder | No | TBD | TBD | TBD |
  | ReGVD | Yes (graph) | TBD | TBD | TBD |
  | **GCB + DFG (ours)** | **Yes (DFG)** | **TBD** | **TBD** | **TBD** |

  Note in table: "All models trained for 3 epochs under identical conditions (72/8/20 split, seed 42)."

---

## 🟠 Phase 6 — Real-world evaluation / MobSF (independent, do locally)

- [ ] **Collect APK sample**:
  - 15–20 confirmed malicious APKs from AndroZoo (filter VirusTotal detections > 5)
  - 15–20 clean APKs from F-Droid
  - 30–40 total

- [ ] **Run existing pipeline** on all APKs — collect `vulnerable_function_rate` per APK:
  ```python
  rate = vulnerable_functions_count / total_functions_scanned
  ```

- [ ] **Set up MobSF locally**:
  ```bash
  docker pull opensecurity/mobile-security-framework-mobsf:latest
  docker run -it -p 8000:8000 opensecurity/mobile-security-framework-mobsf
  ```
  Submit each APK via REST API, collect CVSS risk score per APK

- [ ] **Compare ranking AUC** — not binary verdict:
  - Compute ROC-AUC of `vulnerable_function_rate` against ground truth maliciousness labels
  - Compute ROC-AUC of MobSF CVSS score against same labels
  - Report both in Section 8 as triage utility comparison

- [ ] **Note for paper framing**: pipeline produces vulnerability density signal, not binary APK verdict. Higher rate in malicious APKs confirms signal validity. Precision at function level is expected to be ~50% (consistent with Test 7 imbalanced results).

---

## 🟢 Writing — do last, after all numbers are final

Write sections in this order:

- [ ] **Section 3**: Dataset & Experimental Setup
  - Sources: LVDAndro, Juliet, Draper, Devign
  - DFG parsing pipeline — highlight this as a dataset contribution, not just curation
  - Class balance enforcement, 72/8/20 split, seed 42
  - One sentence covering training regime consistency: "All controlled comparisons use a fixed 72/8/20 split (seed 42). The ablation and baseline comparisons use 3-epoch training. Multi-seed stability (Test 4) uses a 1-epoch regime to probe optimisation variance independently of convergence."

- [ ] **Section 4**: Ablation Study
  - Lead with −28% FN reduction, +3.68% accuracy, +0.0212 ROC-AUC
  - Mention both FN *and* FP reduction — DFG helps both directions
  - Ensemble as single paragraph: "The soft ensemble reduces FN by a further 144 at the cost of 2× inference time and lower imbalanced-class F1 (0.6236 vs 0.6585). We adopt standalone GCB+DFG for all reported results."
  - Figure 1: `test3_ablation_bar.png`

- [ ] **Section 5**: System Architecture
  - Threshold tuning (0.45 asymmetric — justify in PAPER_DEFENSE §9)
  - APK pipeline diagram (decompile → parse → DFG → batch inference)
  - Sliding window for long functions
  - Kotlin support
  - Dual-configuration note: standalone for throughput, ensemble for maximum sensitivity

- [ ] **Section 6**: Per-Source Analysis (Android-Domain Specialisation)
  - LVDAndro 99% as headline
  - Draper and Juliet results
  - Devign 66% mentioned here briefly, explained fully in Limitations
  - Frame as: model is fit-for-purpose for Android, not a general cross-domain claim

- [ ] **Section 7**: Baseline Comparison
  - Full table: MLP → CodeBERT → UnixCoder → ReGVD → GCB+DFG
  - Note LineVul and VulBERTa unavailable for direct comparison; cite original papers
  - Note all models evaluated on same split under same training budget

- [ ] **Section 8**: Real-World Deployment
  - Test 7 imbalanced results (93.13% recall, F1 0.6585, standalone GCB)
  - Vulnerable function rate framing — triage filter, not binary verdict
  - MobSF ranking AUC comparison
  - Obfuscation degradation (Test D — ProGuard defeats package filtering)
  - Test C calibration: 23,005 functions, near-zero false-positive hallucinations

- [ ] **Section 9**: Limitations
  - 7 FN failure patterns from Test 8 (verify count against rerun results)
  - Inter-procedural vulnerability scope limitation
  - Decompiled code DFG degradation
  - Devign domain gap
  - Obfuscation vulnerability

- [ ] **Abstract and Introduction** — write last once all numbers are confirmed

- [ ] **Pick target venue**:
  - **MSR** — strongest fit given dataset contribution + empirical depth; submit here first
  - **ISSTA / ASE** — viable after baseline table complete and ReGVD comparison added
  - **ICSE** — stretch target; needs stronger novelty framing around Android pipeline

---

## ✅ Already Done (pre-retraining numbers — will update after Phase 1–3)

- [x] 3-way split design verified — zero optimism bias confirmed (Test 1)
- [x] ROC-AUC 0.9798, PR-AUC 0.9797 standalone GCB (Test 2 — will rerun)
- [x] DFG ablation: +3.68% accuracy, −635 FN, ~28% fewer missed malware (Test 3 — on held-out test set)
- [x] Multi-seed stability: 87.12% ± 0.16%, ROC 0.9543 ± 0.0003 — **stale, split bug present, rerun pending** (Test 4)
- [x] Per-source breakdown: LVDAndro 99% vs Devign 66% (Test 5 — will rerun)
- [x] MLP/TF-IDF baseline: 71% reduction in FN vs MLP (Test 6 — no rerun needed, independent)
- [x] Imbalanced evaluation 90/10: 93.13% recall, F1 0.6585, standalone GCB (Test 7 — will rerun)
- [x] Qualitative error analysis: FN patterns identified and documented (Test 8 — will rerun)
- [x] APK decompilation pipeline — JADX + Tree-sitter, Java + Kotlin, manifest-aware filtering
- [x] Sliding window inference for long functions
- [x] Threshold sensitivity table: precision/recall/F1 at 0.40–0.65
- [x] End-to-end inference system (Tests A & B)
- [x] Obfuscation degradation test (Test D) — ProGuard defeats targeted package filtering
- [x] Confidence calibration in the wild (Test C) — 23,005 functions, near-zero false positives
- [x] Ensemble comparison: soft/hard, 50/50, 70/30, triple variants all evaluated
- [x] PAPER_DEFENSE.md — preemptive reviewer responses drafted

---

## 📊 Numbers to update after retraining (current stale values for reference)

| Metric | Current (stale) | Status |
|---|---|---|
| Test 2 ROC-AUC | 0.9798 | Rerun after Phase 1 |
| Test 2 PR-AUC | 0.9797 | Rerun after Phase 1 |
| Test 3 FN reduction | ~28% / −635 FN | Rerun after Phase 2 |
| Test 3 accuracy delta | +3.68% | Rerun after Phase 2 |
| Test 4 accuracy | 87.12% ± 0.16% | Rerun after Phase 4 |
| Test 4 ROC-AUC | 0.9543 ± 0.0003 | Rerun after Phase 4 |
| Test 7 recall (standalone) | 93.13% | Rerun after Phase 1 |
| Test 7 F1 (standalone, imbalanced) | 0.6585 | Rerun after Phase 1 |
| Test 8 total FN count | 663 | Rerun after Phase 1 |
| LVDAndro per-source accuracy | 99% | Rerun after Phase 1 |
