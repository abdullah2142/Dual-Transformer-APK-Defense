# Does Structure Matter?
## An Empirical Study of Data Flow Graphs in Transformers for Decompiled Android Bytecode

**Single source of truth for this project.** Every number, decision, limitation and drafted
paragraph lives here. `README.md` describes the repository and deliberately carries no results —
having numbers in two places is what let six documents drift apart.

**Last verified**: 2026-08-04 · **Target venue**: IEEE Access

> **Reading rule.** Every result below carries a status tag. Only ✅ figures may be written into
> the paper as-is.
>
> | Tag | Meaning |
> |---|---|
> | ✅ **verified** | reproduced from a checkpoint's own notebook on the correct partition |
> | ⚠️ **provisional** | honest, but will change — the run hit its epoch ceiling, or the duplicate filter is not yet applied |
> | ❌ **broken** | measured on a contaminated partition or a superseded model; do not cite |

---

# Part 1 — Status board

## 1.1 Where the work stands

| # | Step | State |
|---|---|---|
| 1 | Fix eval scripts: strip filename fallback, add duplicate filter | ✅ done 2026-08-03 |
| 2 | Re-run test-4, test-6, test-7 | ⬜ blocked on checkpoint paths (§7.1) |
| 3 | Retrain CodeBERT text + CodeBERT+DFG on Partition N | ✅ done 2026-08-04 → `training_notebooks/re_train/` |
| 3b | Raise epoch ceiling, retrain `codebert-train-text` + `graphcodebert-train-text-only` | 🟡 notebooks updated 2026-08-04, **ready to run** — 2 GPU runs (§4.3) |
| 4 | Re-run test-2 (ROC/PR, regenerates the `.npy` everything downstream reads) | ⬜ waits on 3b |
| 5 | Re-run test-8 (McNemar) | ⬜ CPU, seconds, waits on 4 |
| 6 | Re-run test-5 (TF-IDF baselines) | ⬜ CPU, waits on 4 |
| 7 | Re-run test-3 ×3 seeds, **or** relabel Table 3 as the 5-epoch config | ⬜ decision (§4.3) |

**Cost to finish**: 2 GPU training runs + 6 evaluation re-runs, plus 3 more GPU runs if Table 3
is re-measured.

## 1.2 What the paper can and cannot claim today

| Claim | Evidence | Status |
|---|---|---|
| **DFG provides no consistent benefit** | within-backbone comparisons, Table 2 | ✅ **safe** — the core finding survives everything below |
| DFG *uniformly degrades* accuracy | Table 2 | ❌ **false as of 2026-08-04** — reverses on CodeBERT (§3.2) |
| Training stability ±0.10% | test-3 | ⚠️ measured on the 5-epoch config, unfiltered |
| Transformers beat TF-IDF | test-5 | ⚠️ unfiltered; re-runs with test-2 |
| Cross-architecture gap (Table 2b) | test-8 | ❌ entirely a leakage artifact |
| Per-source generalisation (Table 4) | test-4 | ❌ contaminated partition |
| Deployment behaviour (Table 5) | test-6 | ❌ contaminated partition *and* model changed |
| Why DFG fails (Section 8) | test-7 | ❌ contaminated partition — mechanism plausible, examples unreliable |
| Real-APK calibration (Test 9) | scanner reports | ✅ **safe** — no split dependency |

**The headline result is safe; much of its supporting evidence is not.** That distinction drives
everything in Part 5.

## 1.3 Open decisions

| # | Decision | Blocks | §  |
|---|---|---|---|
| D1 | Epoch ceiling: raise only where it was hit, or move all six to a common 10 / 3 budget | Section 3 | §4.3 |
| D2 | Table 3: re-run at the new ceiling, or label it as the 5-epoch config | Table 3 | §4.3 |
| D3 | Scanner ships GCB+DFG but test-6 now measures UniXcoder text-only | Section 7 | §5.5 |
| D4 | Whether Table 1 is the unfiltered 19,996 or the duplicate-filtered 18,541 | Tables 1–5 | §5.4 |
| D5 | Sequence lengths differ between the arms of two backbones — disclose, or retrain to match | Tables 1–2, Section 4 | §4.3 |

---

# Part 2 — The paper

## 2.1 Thesis

This project began as a positive claim — *"DFG-aware attention reduces missed malware by 28%."*
Rigorous re-evaluation showed that claim was an artifact of flawed methodology. Correcting it
revealed a more interesting and more publishable truth: **all modern transformer models converge
to the same performance on decompiled Android vulnerability data, whether or not graph structure
is incorporated.** The paper then explains mechanistically *why* DFG fails in this setting.

**Three-sentence summary**

> We build the first end-to-end system for DFG-aware vulnerability detection on decompiled
> Android bytecode at scale. Through a systematic empirical evaluation across three encoder
> backbones, we find that DFG-aware attention provides no consistent benefit over standard
> text-only transformers in this setting. Qualitative analysis of the most confident false
> negatives reveals the cause: JADX decompilation strips identifier semantics from DFG edges,
> leaving graph structure present but informationally empty.

## 2.2 Contributions

1. **End-to-end Android APK pipeline** — first published system for DFG extraction from
   decompiled bytecode at scale across Java, Kotlin and C/C++.
2. **200k DFG-annotated vulnerability corpus** — large, balanced, not otherwise available
   publicly. Released deduplicated (§5.4).
3. **Informative negative finding with a mechanistic explanation** — the field assumes DFG helps
   on code; this is the first evidence it does not help on *decompiled* code, with a
   qualitative account of why.

> **IEEE Access framing.** The repo's older notes targeted MSR / EMSE / ASE, where the empirical
> study alone carries the paper. IEEE Access expects a system contribution alongside the
> empirical one, so **contribution 1 is promoted to co-equal** rather than supporting material,
> and **Related Work must be written from scratch** — nothing in this repository drafts it.

## 2.3 Section plan

| § | Content | Ready? |
|---|---|---|
| 1 | Introduction | draft sentence in §8.1; write last |
| 2 | Related work | **nothing written** — from scratch |
| 3 | Dataset and pipeline | draft in §8.2; needs D1 settled first |
| 4 | Model comparison and ablation | draft in §8.3; needs step 3b + test-2 |
| 5 | System architecture (threshold 0.60) | needs the threshold sweep re-derived (§6.7) |
| 6 | Per-source analysis | needs test-4 |
| 7 | Real-world deployment | needs D3 |
| 8 | Limitations and qualitative analysis | prose in Parts 6–7; needs test-7 |
| 9 | Conclusion | — |

---

# Part 3 — Results

All accuracies below are on the **unfiltered 19,996-sample test set** unless stated. See §5.4
for the duplicate-filtered 18,541 alternative and decision D4.

## 3.1 Table 1 — Full model comparison

| Model | Backbone | Structure | Accuracy | ROC-AUC | PR-AUC | FN | FP | Best epoch | Status |
|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| LR + TF-IDF | — | none | 84.4519% | 0.9271 | 0.9270 | 1,685 | — | — | ⚠️ |
| MLP + TF-IDF | — | none | 85.4821% | 0.9385 | 0.9408 | 1,425 | — | — | ⚠️ |
| CodeBERT | codebert-base | text | 88.2476% | 0.9584 | 0.9597 | 1,217 | 1,133 | **5** | ⚠️ ceiling |
| CodeBERT + DFG | codebert-base | DFG attn | 88.5527% | 0.9601 | 0.9617 | 1,222 | 1,067 | 4 | ✅ |
| GraphCodeBERT | graphcodebert | text | 88.9300% | 0.9596 | 0.9611 | 1,241 | 972 | **5** | ⚠️ ceiling |
| GraphCodeBERT + DFG | graphcodebert | DFG attn | 88.5600% | 0.9585 | 0.9597 | 1,196 | 1,091 | 5 | ✅ |
| UniXcoder | unixcoder-base | text | **89.0778%** | **0.9622** | **0.9636** | 1,238 | 946 | 4 | ✅ |
| UniXcoder + DFG | unixcoder-base | DFG attn | 88.3727% | 0.9602 | 0.9612 | 1,125 | 1,200 | 4 | ✅ |

**Provenance**: every transformer row comes from that model's own training notebook, graded on
its own partition, and is mirrored in `results/models/*.txt`. The two CodeBERT rows are from the
2026-08-04 Partition-N retrain; the other four were each confirmed to match their notebook's
stored output exactly. Partition N reproduces `163,967 / 15,997 / 19,996` byte-for-byte as
printed in every notebook.

**All eight models sit in an 84.45–89.08% band; the six transformers in a 0.83pp band
(88.25–89.08%).** That convergence — not any individual number — is the paper's substantive
observation.

## 3.2 Table 2 — DFG effect per backbone

Delta is text-only minus DFG-aware, so **positive means text-only wins**.

| Backbone | Text-only | DFG-aware | Δ Accuracy | Δ FN | Verdict |
|---|:---:|:---:|:---:|:---:|---|
| CodeBERT | 88.2476% | 88.5527% | **−0.305%** | −5 | ⚠️ **DFG wins** — but text hit its ceiling |
| GraphCodeBERT | 88.9300% | 88.5600% | +0.370% | −45 | text wins |
| UniXcoder | 89.0778% | 88.3727% | +0.705% | −113 | text wins |

**Two of three backbones favour text-only; one now favours DFG.** McNemar p-values are *not*
reproduced here — the existing ones were computed on the leaked CodeBERT predictions and are
void until test-8 re-runs.

> ### ⚠️ The CodeBERT row reversed sign on 2026-08-04
>
> Before the retrain, CodeBERT read 88.5627% text vs 88.5427% DFG (−0.02%, text ahead). On the
> corrected Partition N it reads 88.2476% vs 88.5527% — DFG ahead by 0.31pp. By the paper's own
> yardstick this is not dismissable as noise: §3.3's seed variance is ±0.10%, so 0.31pp is ~3σ.
>
> **But the comparison is not clean, and the confound points the right way.** The text-only arm
> selected its best checkpoint on the *final* epoch with validation still rising; the DFG arm
> peaked at epoch 4 and declined. The losing arm is the truncated one. Supporting this: on
> validation the two are effectively tied — 88.3103% (text) vs 88.3228% (DFG), 0.012pp apart.
> The 0.31pp gap appears **only on test**. That reads as sampling noise over an under-trained
> text arm, not a structural DFG advantage. Step 3b (§4.3) settles it.
>
> **Write "no consistent benefit", never "uniformly degrades."** The stronger phrasing appeared
> in `README.md` and `instructions/README.md` and is now false.

## 3.3 Table 3 — Training stability (multi-seed) ⚠️

GraphCodeBERT text-only, retrained from an identical pretrained encoder across 3 seeds. Split
seed pinned at 42; only the training seed varies.

| Seed | Accuracy | ROC-AUC | PR-AUC | F1 (macro) |
|:---:|:---:|:---:|:---:|:---:|
| 42 | 88.8278% | 0.9588 | 0.9596 | 0.8883 |
| 123 | 88.8928% | 0.9609 | 0.9625 | 0.8889 |
| 2025 | 89.0728% | 0.9596 | 0.9617 | 0.8907 |
| **mean ± std** | **88.93% ± 0.10%** | **0.9598 ± 0.0009** | **0.9613 ± 0.0012** | **0.8893 ± 0.0010** |

This ±0.10% is the yardstick used throughout to judge whether a delta is noise, so its own
status matters. It is ⚠️ on two counts: measured on the unfiltered test set, and measured on the
5-epoch GCB text-only configuration that decision D2 may change.

## 3.4 Table 2b — Cross-architecture significance ❌

| Comparison | Δ Accuracy | McNemar p | Verdict |
|---|:---:|:---:|---|
| GCB+DFG vs CodeBERT+DFG | −4.546% | p ≈ 7.3e-114 | ❌ **artifact** |
| GCB+DFG vs UniXcoder+DFG | −0.500% | p = 0.0121 | ❌ recompute |

The −4.55% gap is the memorisation bonus from CodeBERT being graded on its own training data.
On honest Table 1 numbers the real gap is 88.5527% vs 88.5600% ≈ **0.01%**. Expect this row to
collapse to non-significant when test-8 re-runs — **that collapse is the pass/fail check for the
entire remediation.** The claim *"model choice matters more than DFG structure"* rests entirely
on this row and must be retired if it collapses.

## 3.5 Table 4 — Per-source breakdown ❌

Contaminated (Partition S). Retained only to show what changes.

| Source | N (reported) | Accuracy | ROC-AUC | F1 | FN |
|---|:---:|:---:|:---:|:---:|:---:|
| LVDAndro | 7,500 | 97.0667% | 0.9957 | 0.9707 | 133 |
| Draper | 7,500 | 86.6667% | 0.9264 | 0.8664 | 303 |
| Juliet | 2,500 | 100.0000% | 1.0000 | 1.0000 | 0 |
| Devign | 2,496 | 68.9103% | 0.7729 | 0.6844 | 222 |

**The tidy 7,500 / 7,500 / 2,500 / 2,496 counts are themselves the artifact.** Correct counts on
Partition N are **7,483 / 7,626 / 2,489 / 2,398**, and after the duplicate filter
**7,482 / 6,856 / 1,815 / 2,388**.

**Juliet's 100% must be dropped** — 27.1% of its test partition is verbatim in train/val. Report
the filtered accuracy on 1,815 clean samples, framed as a synthetic sanity check rather than
capability.

## 3.6 Table 5 — Deployment threshold (imbalanced 90/10) ❌

Superseded twice over: contaminated partition, **and** the model changed (§5.5). Four rows
(GCB+DFG ×2, Ensemble ×2) collapse to two (UniXcoder ×2).

| Model | Condition | Accuracy | Recall | F1 | FPR | FN |
|---|---|:---:|:---:|:---:|:---:|:---:|
| GCB+DFG | balanced 50/50 | 94.59% | 94.48% | 0.9459 | 5.31% | 552 |
| GCB+DFG | imbalanced 90/10 | 94.64% | 94.14% | 0.7782 | 5.31% | 65 |
| Ensemble | balanced 50/50 | 94.58% | 94.93% | 0.9460 | 5.78% | 507 |
| Ensemble | imbalanced 90/10 | 94.27% | 94.68% | 0.7675 | 5.78% | 59 |

## 3.7 Test 9 — Real-world APK scanner calibration ✅

13 APK reports, 23,005 functions. No split dependency, so unaffected by everything in Part 5.

| Aggregate metric | Value |
|---|---:|
| Confidently safe (< 0.10) | 84.0% |
| Uncertain (0.10 – 0.60) | 8.9% |
| Flagged (≥ 0.60) | 7.1% |
| Highly confident vuln (> 0.90) | 5.5% |
| Mean / median | 0.0991 / 0.0053 |

| APK | Type | Functions | Flagged | Rate |
|---|---|:---:|:---:|:---:|
| Vuldroid | deliberately vulnerable | 47 | 10 | 21.3% |
| dvba_v1.1.0 | deliberately vulnerable | 77 | 16 | 20.8% |
| allsafe | vulnerable test app | 149 | 26 | 17.4% |
| InsecureBankv2 | deliberately vulnerable | 88 | 10 | 11.4% |
| de.danoeh.antennapod | FOSS podcast | 6,169 | 576 | 9.3% |
| org.schabi.newpipe | FOSS media | 11,070 | 728 | 6.6% |
| AndroGoat | deliberately vulnerable | 371 | 23 | 6.2% |
| com.beemdevelopment.aegis | FOSS 2FA | 1,428 | 84 | 5.9% |
| Neo_Store_1.2.4 | FOSS app | 2,939 | 153 | 5.2% |
| InsecureShop | intentionally vulnerable | 336 | 10 | 3.0% |
| net.thunderbird.android | FOSS email | 95 | 2 | 2.1% |
| calendar-fdroid-release | FOSS app | 236 | 1 | 0.4% |
| istark.vpn.starkreloaded | commercial sample | 0 | 0 | 0.0% |

The distribution is sharply concentrated near 0.0 with a small high-confidence tail — not flat,
not centred near 0.5. Three of the four deliberately-vulnerable apps are the three
highest-flagged; **InsecureShop at 3.0% is the exception and is addressed in §6.10.**

> **Do not use 89.2% / 5.2% / 5.6% / 4.1%.** Those figures circulated in the pre-consolidation
> defence notes and are stale. The correct values are the table above.

---

# Part 4 — Methodology

## 4.1 Corpus

199,960 samples, strict 1:1 safe-to-vulnerable, four sources:

| Source | N | Content |
|---|:---:|---|
| LVDAndro | 75,000 | decompiled Android Java — **all Android claims rest here** |
| Draper | 75,000 | C/C++ NVD/SARD CVEs |
| Juliet | 25,000 | synthetic CWE test suite |
| Devign | 24,960 | C/C++ QEMU/FFmpeg |

Keys are exactly `code`, `dfg`, `label`, `filename`. All 199,960 filenames are unique, so there
is no filename-group leakage — but APK-level provenance is not preserved, so **same-APK leakage
is unmeasurable without regenerating the corpus.**

## 4.2 Split

82 / 8 / 10 train/val/test, seed 42 → **163,967 / 15,997 / 19,996**.

> **Stop calling it "stratified."** `infer_source` looks for keys `source`, `dataset`, `origin`,
> `project` — **none of which exist in this corpus.** Every entry resolves to `"unknown"`, the
> split degenerates to a single group, and the result is a plain random shuffle.
> `results/models/codebert_results.txt` claims "source-stratified"; that is false. The paper
> must say **random shuffle, seed 42**.

This partition is called **N** in Part 5. It is the target end state for everything.

## 4.3 Training protocol — and the epoch-ceiling problem

| Parameter | Value |
|---|---|
| Checkpoint selection | best validation accuracy |
| Batch size | 16 train / 32 eval |
| Learning rate | 2e-5, AdamW, eps 1e-8, linear warmup |
| Gradient clipping | max norm 1.0 |
| Precision | FP16 (AMP) |
| Code length | 384 tokens |
| DFG node budget | 128 |
| Decision threshold | 0.60 |
| Max epochs / patience | **10 / 3** for the two runs being retrained and for `graphcodebert-train-dfg`; **5 / 2** for the other three |
| Evaluation precision | FP16 (`autocast`) — **see finding 3 below; this was not uniform** |

> **Correction (2026-08-04).** The pre-consolidation notes said *both* GraphCodeBERT models were
> given the 10 / 3 ceiling. **Only the DFG one was.**
> `graphcodebert-train-text-only.ipynb` runs at 5 / 2 like the other four. Verified against the
> `Args` block of all six notebooks.

### What actually happened

| Run | Ceiling | Best epoch | Validation trajectory (%) | How it ended |
|---|:---:|:---:|---|---|
| `codebert-train-text` | 5 | **5** | 86.64 → 87.84 → 88.09 → 88.26 → **88.31** | hit cap, **still improving** |
| `codebert-final-dfg` | 5 | 4 | 86.63 → 87.74 → 87.89 → **88.32** → 88.15 | hit cap at patience 1/2 |
| `graphcodebert-train-text-only` | 5 | **5** | 86.45 → 87.90 → 88.71 → 88.86 → **89.04** | hit cap, **still improving** |
| `graphcodebert-train-dfg` | 10 | 5 | outputs cleared | had genuine room |
| `unixcoder-text-only` | 5 | 4 | 87.22 → 88.55 → 88.94 → **88.99** → — | hit cap at patience 1/2 |
| `unixcoder-dfg-final` | 5 | 4 | 86.77 → 87.96 → 88.44 → **88.71** → 88.29 | hit cap at patience 1/2 |

**Early stopping never fired in any of the five 5-epoch runs.** Every one terminated on
`num_train_epochs`, not on exhausted patience. What the paper describes as validation-based
early stopping operated in practice as a **fixed 5-epoch budget with best-checkpoint
selection** — a materially different protocol, and one that §6.4's defence does not cover.

### Finding 3 — the two CodeBERT arms were scored at different precision

Found 2026-08-04 while sizing the retrain. Every model trains under FP16 autocast, but
*evaluation* precision was never made uniform:

| Run | Eval precision | Matches its pair? |
|---|:---:|:---:|
| `codebert-train-text` | **FP32** | ❌ |
| `codebert-final-dfg` | FP16 | ❌ |
| `graphcodebert-train-text-only` | FP16 | ✅ |
| `graphcodebert-train-dfg` | FP16 | ✅ |
| `unixcoder-text-only` | FP32 | ✅ |
| `unixcoder-dfg-final` | FP32 | ✅ |

**CodeBERT is the only backbone whose two arms were evaluated at different precision** — and it
is the same backbone whose DFG delta reversed sign. So that 0.31pp carried *two* independent
confounds, not one: a truncated text arm and a precision mismatch against its own comparator.
GraphCodeBERT and UniXcoder are each internally consistent, so their deltas are unaffected.

It also explains a timing oddity: CodeBERT text-only validation took 7:03 per epoch against the
DFG variant's 2:09, despite the DFG dataset doing strictly more work per sample.

Cross-backbone comparisons (Table 2b) mix FP16- and FP32-scored models, which is a further
reason those numbers are not clean — secondary, since Table 2b is already broken for leakage.

### Changes applied to the notebooks (2026-08-04) — ready to run

| Notebook | Before | After |
|---|---|---|
| `codebert-train-text.ipynb` | 5 / 2, FP32 eval | **10 / 3, FP16 eval**, wall-clock guard |
| `graphcodebert-train-text-only.ipynb` | 5 / 2, FP16 eval | **10 / 3**, wall-clock guard |

- **Ceiling 10 / patience 3** matches `graphcodebert-train-dfg`, the only run that ever had room
  to converge. For GraphCodeBERT this makes the backbone's two arms *exactly* matched.
- **CodeBERT text-only moves to FP16 evaluation** to match `codebert-final-dfg` (finding 3).
  Changing the DFG arm to FP32 instead would have cost a third GPU run.
- **Wall-clock guard** (`time_budget_hours = 11.0`): measured cost is ~62 min/epoch training plus
  ~2 min validation once FP16 eval lands, so 10 epochs ≈ 10.7 h against Kaggle's 12 h session
  limit. The guard stops after the last epoch that fits and proceeds to the test evaluation,
  which otherwise would be lost to a session kill. The LR schedule now stretches over 10 epochs
  rather than 5, so these are genuinely new runs, not continuations.
- **Stored outputs cleared** on both, since the source no longer matches them. The superseded
  runs' figures are preserved in `results/models/*.txt` and in the trajectory table above.

### ⚠️ Finding 4 — sequence lengths are not uniform either (2026-08-04, UNRESOLVED)

Read from the `Args` block of all six notebooks:

| Backbone | text `code_length` | DFG `code_length` (+ dfg) | DFG total | Code context matched? | Total matched? | Winner |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| CodeBERT | 384 | 384 (+128) | 512 | ✅ **yes** | ❌ | **DFG** +0.31 |
| GraphCodeBERT | **512** | 384 (+128) | 512 | ❌ text sees +128 | ✅ yes | text +0.37 |
| UniXcoder | 384 | **256** (+64) | 320 | ❌ text sees +128 | ❌ text sees +64 | text +0.71 |

`unixcoder-dfg-final` additionally uses **train_batch_size 8** where every other run uses 16.

**The one backbone that matches code context between its arms is the only one where DFG does not
lose.** In the other two the text arm was given 128 more tokens of code than its DFG counterpart,
so "no DFG" is confounded with "more code". This does not overturn *"no consistent benefit"* —
that claim survives — but it changes what the comparison measures:

- **CodeBERT** asks *"does adding DFG help, holding code context fixed?"*
- **GraphCodeBERT** asks *"are 128 positions better spent on DFG nodes or on more code?"* —
  a legitimate question, but a different one, and the honest answer from its row is *more code*.
- **UniXcoder** cleanly asks neither: its DFG arm has less code, a smaller total budget, *and*
  half the batch size, so its 0.71pp is the **least** trustworthy of the three, not the most.

**Not fixed, deliberately.** The step-3b retrain changes the epoch ceiling; changing sequence
length in the same run would confound the very comparison it exists to clean up. Options, once
3b lands:

| Option | Cost | Effect |
|---|---|---|
| Disclose in Limitations, keep the runs | none | honest; reframes GCB/UniXcoder rows as a budget-allocation question |
| Set GCB text-only to 384 and retrain | 1 run | CodeBERT and GCB share one convention; also re-opens D2, since Table 3's seeds ran at 512 |
| Make all three uniform | several runs | requires retraining DFG arms too |

### Decision (2026-08-04): raise the ceiling and retrain

The two bolded runs are retrained so early stopping, not the cap, decides when training stops.
Both are **text-only arms**, which cuts differently per backbone:

- **GraphCodeBERT** — the protocol already favoured the DFG arm (10 / 3 against 5 / 2) and DFG
  still lost by 0.37pp. Giving text its fair ceiling can only widen that gap. The null-DFG
  conclusion is safe here and probably strengthened. **This is a good fact to hold for a
  reviewer**: the one backbone where the budget was asymmetric, it was asymmetric in DFG's
  favour and DFG still lost.
- **CodeBERT** — both arms shared the 5 / 2 cap, but only text was still climbing, and text is
  the arm that lost. This is the one place in the study where the cap could be manufacturing the
  result, and it is the row a reviewer will go after.

**D1 — open**: raising the ceiling *only* where it was hit is **data-dependent stopping**; extra
budget goes exactly to the models that benefit. Defensible if stated plainly. The cleaner
protocol is a common 10 / 3 budget across all six, letting early stopping genuinely decide —
4 more GPU runs (6 total rather than 2). **The paper must describe one protocol, uniformly
applied.** Settle before writing Section 3.

**D2 — open**: `test-3-seed{42,123,2025}` train GCB text-only at 5 / 2, the same configuration
being changed. If GCB text-only moves, ±0.10% no longer measures what Table 1 reports. Either
re-run the three seed notebooks (3 GPU runs) or state that Table 3 characterises the 5-epoch
configuration.

## 4.4 Historical note

An earlier version used a fixed 3-epoch schedule with **no validation set**, selecting the
checkpoint on the same 10% partition later reported as test — circular evaluation. That produced
92.02%; the honest figure under held-out evaluation was 88.71%. The 3.31pp gap was entirely
optimism bias. Do not cite 92.02% anywhere.

---

# Part 5 — Data integrity

Four problems were found. Three required fixes; one is a disclosure.

## 5.1 Problem 1 — CodeBERT trained on a different split ✅ FIXED

Three incompatible 82/8/10 partitions coexisted, all seed 42:

| Partition | Built by | Was used by |
|---|---|---|
| **N** | `stratified_three_way_split`, `random.Random(42)`; `infer_source` finds nothing → one group → plain shuffle | GCB ×2, UniXcoder ×2, tests 2, 3, 5, 8 |
| **S** | same function **plus a filename-prefix fallback** → 4 real groups | tests 4, 6, 7 |
| **B** | `sklearn.train_test_split(random_state=42, stratify=…)` | CodeBERT ×2 only |

Two independent 10% subsets of one corpus overlap in ~10% of members — so ~90% of one method's
test set sits in the other's training set. When a grader on N evaluated a CodeBERT checkpoint
trained on B, it was largely asking about training data.

**Measured:**

| Model | own notebook | graded on N |
|---|---:|---:|
| UniXcoder text | 89.0778% | 89.0778% (exact — same partition) |
| CodeBERT text | 88.5627% | **93.3987%** |
| CodeBERT+DFG | 88.5427% | **93.1186%** |

A fixed checkpoint does not gain five points between two gradings. Nothing in the repo's history
produces 93% honestly (old-methodology CodeBERT was 88.4777%), so leakage is the only
explanation.

**Fixed** by retraining both CodeBERT variants on Partition N (2026-08-04); the executed
notebooks with their outputs are `training_notebooks/re_train/codebert-{train-text,final-dfg}.ipynb`.
Re-grading the old checkpoints was not an option — they were trained on B, which overlaps N's
test set, so no honest test partition remained for them.

## 5.2 Problem 2 — Tests 4, 6, 7 built Partition S ✅ FIXED IN CODE, RE-RUNS PENDING

```
test_S overlapping the true test set :  2,018  (10.09%)
test_S sitting in TRAINING           : 16,427  (82.15%)   <- leaked
test_S sitting in VALIDATION         :  1,551  ( 7.76%)
                                        -> 89.91% previously seen
```

The filename-prefix fallback has been stripped from all three. Tests 2, 3, 5 were verified clean
independently — rebuilding their test set gives **symmetric difference = 0** against the notebook
test set.

## 5.3 Problem 3 — Test-set duplication 📢 DISCLOSE

**1,455 of 19,996 test entries (7.28%) are byte-identical to a train or validation sample.**

| Source | test | clean | dropped | % |
|---|---:|---:|---:|---:|
| LVDAndro | 7,483 | 7,482 | 1 | 0.0% |
| Draper | 7,626 | 6,856 | 770 | 10.1% |
| Juliet | 2,489 | 1,815 | 674 | 27.1% |
| Devign | 2,398 | 2,388 | 10 | 0.4% |
| **Total** | **19,996** | **18,541** | **1,455** | **7.28%** |

> **Use 1,455 / 7.28% / 18,541, not 1,375 / 6.88%.** The audit's 1,375 counted overlap with
> *training* only. The filter also removes overlap with *validation* — correct, because
> validation drove checkpoint selection, so those samples are not clean either.

**LVDAndro, on which every Android claim rests, is unaffected at 0.01%.** 51 code bodies carry
contradictory labels (102 entries); all are Devign.

**Both causes are confirmed in `dataset_creation_scripts/`; no dedupe step exists anywhere in
that pipeline.** Draft disclosure paragraph:

> "7.3% of test samples were byte-identical to a training or validation sample and are excluded
> from all reported metrics. Two corpus-construction artifacts account for them: Draper
> functions carrying multiple CWE labels were emitted once per CWE and the distinguishing
> `CWE_ID` field was dropped at the merge step (`finalizedataset.py`), collapsing them into
> duplicates (8,281 copies, all label=1); and Juliet's per-file `good()` dispatcher methods —
> test scaffolding containing no vulnerability logic — were captured by a `startswith('good')`
> rule in `julietprocess.py` (7,016 copies, 5,851 label=0; the largest single group is 813
> identical copies). LVDAndro, on which all Android claims rest, is unaffected at 0.01%. The 51
> code bodies carrying contradictory labels are all Devign."

## 5.4 Deduplication decisions

- **Training data: NOT deduplicated.** It would change the partition and cost 9 GPU runs
  instead of 2, and it cancels out of a within-backbone difference anyway.
- **Test set: deduplicated at evaluation time.** Costs nothing, removes the memorisation
  component from every metric, and yields Juliet's real accuracy on 1,815 unseen samples rather
  than 100% on a memorised 2,489. Implemented in `test_scripts/split_and_filter.py`.
- **Released artifact: ship the deduplicated corpus.** Contribution 2 *is* the corpus, so
  releasing it with a known duplication bug undercuts it.
  `dataset/dataset_graphcodebert_dedup.jsonl` (189,938 entries) is generated and verified.
  State plainly: *"the released corpus is deduplicated; models here were trained on the
  pre-deduplication version and evaluated on a deduplicated test partition."*
- **Original dataset untouched** — `dataset_graphcodebert.jsonl` still carries its
  Dec 28 2025 timestamp.

Dedup report:

| Source | before | after | removed |
|---|---:|---:|---:|
| LVDAndro | 75,000 | 74,994 | 6 |
| Draper | 75,000 | 70,740 | 4,260 |
| Juliet | 25,000 | 19,346 | 5,654 |
| Devign | 24,960 | 24,858 | 102 |
| **Total** | **199,960** | **189,938** | **10,022** |

Class ratio 50.0/50.0 before, 50.1/49.9 after. Juliet's internal balance shifts (its safe class
was the most duplicated) — **report Juliet separately from headline metrics.**

**D4 — open**: is Table 1 the unfiltered 19,996 or the filtered 18,541? The training notebooks
produce the former; the eval scripts produce the latter. They will disagree by roughly 0.5–1pp.
Pick one and apply it to Tables 1–5 uniformly.

## 5.5 test-6 model change, and the scanner inconsistency

`test-6` now evaluates **UniXcoder text-only** (89.0778%, best in Table 1); the **ensemble has
been removed**. Rationale: GCB+DFG is the weaker variant of the middle backbone, so using it for
the deployment table contradicts the paper's own null-DFG finding. The ensemble was a plain
50/50 probability average of GCB+DFG and CodeBERT text — never defined in any document despite
being reported in three of them, and built on the leaked CodeBERT besides.

> ### ⚠️ D3 — the scanner still deploys GraphCodeBERT+DFG
>
> `test_scripts/scanner-pipeline.ipynb` loads the GCB+DFG checkpoint at threshold 0.60. With
> test-6 now measuring UniXcoder text-only, **Table 5 characterises a configuration the system
> does not ship.**
>
> | Option | Work | Consequence |
> |---|---|---|
> | Switch the scanner to UniXcoder text-only | re-run scanner over 13 APKs, then Test 9 | consistent throughout; Test 9's 84.0 / 8.9 / 7.1 and every per-APK rate change |
> | Keep GCB+DFG, revert test-6 | none | back to contradicting the null-DFG finding |
> | Keep both, state the split explicitly | doc edit | Table 5 = "best model under deployment-realistic imbalance"; Section 7 = "deployed configuration". Defensible, but invites *"why not deploy the best model?"* |
>
> Option 1 is the only internally consistent story and the only one costing GPU time. Note also
> that §6.7's threshold-0.60 defence was derived on GCB+DFG; if the scanner changes, the sweep
> must be re-derived on UniXcoder.

---

# Part 6 — Reviewer defences

Use these paragraphs directly. Numbers inside them are current as of 2026-08-04 unless flagged.

## 6.1 The null result as a contribution

*Attack*: "A negative result is not publishable — you failed to show DFG helps."

> "Our controlled empirical study reveals that DFG-aware attention provides no consistent
> benefit over standard transformer encoding on decompiled Android bytecode — a null result that
> is itself a contribution. Prior work demonstrating DFG's utility operated on clean,
> source-level code with meaningful identifier names. We provide the first systematic evaluation
> of DFG attention on *decompiled* code across three leading transformer backbones. We find that
> because JADX replaces identifiers with machine-generated tokens (`class_336`, `method_1192`),
> DFG edges connect semantically empty tokens; the graph is structurally present but
> informationally empty. Our qualitative analysis of the most confident false negatives confirms
> this mechanism empirically. The finding is actionable: it shows that graph-augmented
> vulnerability detection fails post-decompilation, saving the community compute and directing
> future work toward identifier reconstruction or alternative structural representations."

> ⚠️ Earlier drafts cited "1,184 false negatives" here. The qualitative run used UniXcoder+DFG,
> which has **1,125**. Fix the count when test-7 re-runs.

## 6.2 Cross-backbone inconsistency

*Attack*: "DFG helps one of your backbones — your null claim is wrong."

> ⚠️ **Rewrite required.** The previous paragraph asserted DFG harms all three backbones
> (−0.02%, −0.37%, −0.71%). After the Partition-N retrain, CodeBERT reverses to **+0.31% in
> DFG's favour**. The attack this section anticipates is now the actual situation. Rewrite after
> step 3b around this shape:

> "Across three encoder backbones, DFG augmentation fails to produce a consistent directional
> effect: it slightly favours CodeBERT, and harms GraphCodeBERT (−0.37%) and UniXcoder (−0.71%).
> A genuine structural advantage would produce consistent gains across all backbones. Instead
> the sign of the effect depends on the backbone, and every magnitude is comparable to the
> ±0.10% variation we measure across random seeds. Notably, in the one backbone where the
> training budget was asymmetric it favoured the DFG arm — GraphCodeBERT+DFG received a 10-epoch
> ceiling against text-only's 5 — and DFG still lost."

## 6.3 No SOTA comparison

*Attack*: "Why no comparison to LineVul, VulBERTa, or ReGVD?"

> "LineVul, VulBERTa and ReGVD were not available as reproducible fine-tunable checkpoints at
> the time of this study. Rather than approximating their performance through reimplementation —
> which introduces confounding implementation differences — we provide a principled
> cross-architecture comparison evaluating DFG-aware attention on three encoder backbones under
> identical training conditions. This answers a more precise question: does graph structure help
> on this data type, independent of which backbone is used?"

## 6.4 Training protocol

*Attack*: "Why did some models train for 4 epochs and others 5? Unfair comparison."

> ⚠️ **Rewrite required.** The previous paragraph claimed the protocol lets each model "train
> until it reaches its true capability upper bound." §4.3 shows early stopping never fired in
> any 5-epoch run — every one hit the cap. That defence is not supported. Rewrite after D1 is
> settled, describing whatever uniform protocol is actually adopted, and disclose that two runs
> were retrained at a raised ceiling because they reached the cap while still improving.

## 6.5 Dataset construction

*Attack*: "Why fractional sampling? Are you cherry-picking?"

> "Each source dataset was sampled rather than used in its entirety to enforce a strict 1:1
> safe-to-vulnerable ratio. Vulnerability datasets suffer severe class imbalance — Draper
> contains substantially more samples than Devign, and LVDAndro's malicious fraction varies by
> APK source. Using full datasets without rebalancing would cause the model to learn statistical
> priors (predict 'safe' by default) rather than semantic vulnerability patterns."

## 6.6 The LVDAndro–Devign gap

*Attack*: "Devign at 68.91% shows your model doesn't generalise."

> "The gap between LVDAndro and Devign reflects a documented scope boundary. The model is
> designed as an Android vulnerability scanner, and its accuracy on decompiled Android Java
> confirms fitness for that purpose. Devign's Linux kernel C presents three compounding
> challenges: kernel idioms are underrepresented in training; kernel functions routinely exceed
> the 384-token context window — we observed sequences up to 2,543 tokens; and Devign
> vulnerabilities are predominantly inter-procedural. We report this gap transparently and do
> not generalise Android-domain claims to kernel C analysis."

> ⚠️ Both numbers come from the contaminated test-4. Do not fill them in until it re-runs. Older
> drafts cite LVDAndro at 98.34% in a heading and 97.07% in the body — neither is usable.

## 6.7 Threshold 0.60

*Attack*: "Why 0.60 rather than the standard 0.50?"

> "We calibrate the decision threshold under deployment-realistic conditions — a 90% safe / 10%
> malicious distribution simulating production APK scanning. Threshold sensitivity analysis
> shows F1 is maximised at 0.60. The standard 0.50 threshold yields lower F1 under imbalance, as
> it flags too many safe functions. At 0.60 the system functions as a high-precision triage
> filter."

> ⚠️ **The supporting numbers do not exist.** Older drafts cite "83.4% recall at 7.8% FPR", but
> `results/test7_imbalanced_results.txt` contains **no threshold sweep** — it evaluates only at
> 0.5. test-6 now writes a sweep, so this becomes re-derivable, but on UniXcoder rather than the
> GCB+DFG it was originally claimed for. Blocked on D3.

## 6.8 The sliding window

*Attack*: "Functions exceeding 384 tokens are truncated."

> "For functions exceeding 384 tokens the pipeline generates overlapping chunks (stride =
> code_length / 2), processes each independently, and takes the maximum vulnerability
> probability across chunks as the function-level score. This ensures signals in the tail of
> long functions are evaluated rather than silently discarded. For extremely long functions —
> up to 2,543 tokens in Devign kernel code — the sliding window cannot fully resolve inter-chunk
> dependencies."

## 6.9 Cross-language fusion (Java + C/C++)

*Attack*: "Java and C++ have different vulnerability classes."

> "Modern Android applications routinely use JNI to call compiled C++ shared libraries. An
> Android security scanner processing only Java misses the native attack surface. By training on
> both Java (LVDAndro) and C/C++ (Draper, Devign, Juliet) patterns, the model acquires
> cross-language knowledge reflecting the hybrid reality of production APKs. Per-source
> evaluation confirms this does not harm Java performance."

## 6.10 The InsecureShop result

*Attack*: "InsecureShop is intentionally vulnerable but flags fewer functions than your clean
apps. Your scanner doesn't work."

> "InsecureShop — a deliberately vulnerable Android training application — yields a lower
> vulnerable-function rate (3.0%) than the clean AntennaPod application (9.3%). This reflects
> the training distribution boundary: InsecureShop's intentional vulnerabilities include
> hardcoded credentials, SQL injection and insecure SharedPreferences — textbook patterns that
> may be expressed differently at the decompiled bytecode level than the CVE-labelled patterns
> on which the model was trained."

> ⚠️ Older drafts cite 4.8% vs 8.4%. The real figures are **3.0% vs 9.3%** — the inversion is
> *wider* than the defence assumed, so the paragraph must own it rather than minimise it.

## 6.11 Static over dynamic analysis

*Attack*: "Dynamic analysis is more accurate."

> "While dynamic analysis can resolve runtime-dependent vulnerability conditions, it lacks
> scalability for arbitrary APK analysis. Executing an unknown APK requires a full Android
> runtime, JNI bridge mocking, interaction simulation and significant compute per APK. Static
> analysis via our decompilation pipeline processes an entire APK's developer logic in minutes
> on a single GPU. We frame the system explicitly as a triage filter: it surfaces functions
> warranting analyst attention, not definitive verdicts."

## 6.12 Juliet at 100%

*Attack*: "100% on Juliet inflates your metrics."

> "Juliet Test Suite samples are reported separately and excluded from capability claims. 27.1%
> of Juliet's test partition was byte-identical to a training sample and is removed by our
> duplicate filter; the remaining 1,815 samples are reported as a synthetic sanity check. Their
> structured, non-obfuscated form makes them substantially easier than real decompiled code. All
> capability claims reference LVDAndro and Draper exclusively."

---

# Part 7 — Qualitative analysis (Section 8 material)

> ❌ **Every count in this Part comes from test-7, which ran on the contaminated Partition S.**
> The top-20 most confident false negatives may themselves be training samples, so the specific
> examples and the 5/4/3/3/2/1/1/1 distribution must be re-derived. **The mechanism is likely to
> survive — it is grounded in decompiler behaviour, not in any particular sample — but the
> evidence for it does not yet exist in usable form. This is the highest-priority re-run: it is
> what turns the negative result into a contribution.**
>
> test-7 now records `corpus_idx` and `source` per false negative, so the re-derived list will be
> traceable and comparable across models and runs.

## 7.1 Distribution (to be re-derived)

| Pattern | Description | top-20 | Source |
|---|---|:---:|---|
| P5a | full machine-generated obfuscation | 5 | LVDAndro |
| P1 | structural fragmentation | 4 | LVDAndro |
| P5b | Kotlin/lambda synthetic obfuscation | 3 | LVDAndro |
| P7 | inter-procedural access | 3 | LVDAndro |
| P2 | benign surface appearance | 2 | LVDAndro |
| P3 | arithmetic edge case | 1 | LVDAndro |
| P6 | control-flow / flag logic | 1 | Draper |
| P4 | Android API semantic bypass | 1 | LVDAndro |

P5a + P5b = 8/20 — obfuscation-driven DFG degradation dominates. P5a + P1 + P5b = 12/20 —
three-quarters of top failures are decompilation artifacts.

## 7.2 P5a — Full machine-generated identifier obfuscation

> "The dominant failure mode is complete identifier obfuscation (P5a). JADX strips all symbolic
> information when the APK was compiled with ProGuard or R8: classes become `class_336`, methods
> `method_1192`, fields `field_1000`, local variables generic numeric indices (`n21`, `n22`).
> The DFG edges built over these tokens are syntactically valid — the parser correctly
> identifies data flows between definitions and uses — but semantically empty. When every node
> carries a machine-generated token, the attention mechanism has no basis for distinguishing a
> vulnerable data flow from a benign one. The model assigns 99.99% confidence of safety,
> reflecting not uncertainty but the complete absence of discriminative signal. This provides
> the mechanistic explanation for the null ablation result: under full obfuscation, DFG-aware
> attention reduces to standard attention over a graph of meaningless connections."

## 7.3 P5b — Kotlin/lambda synthetic obfuscation

> "A Kotlin-specific variant (P5b) accounts for a further set of false negatives. The Kotlin
> compiler generates synthetic class names for lambda expressions (e.g.
> `-$$Lambda$Sounds$iJSOl-pseCunlcJXFFxU9chQx24`) and coroutine state machines (e.g.
> `MediaParsingService$updateStorages$2`) that are non-semantic by design. Beyond obfuscated
> names, Kotlin-decompiled code produces distinctive patterns — coroutine continuation passing,
> `Intrinsics.checkExpressionValueIsNotNull` calls, `CollectionsKt`/`StringsKt` wrapper
> invocations — that differ structurally from the Java-centric LVDAndro training samples,
> creating an additional distributional gap."

## 7.4 P1 — Structural fragmentation

> "Structural fragmentation (P1) arises because JADX occasionally produces syntactically
> impossible Java: `package` declarations inside method bodies, `import` statements after
> executable code, field declarations interleaved with method invocations. The dataset pipeline
> wraps each snippet in a `DummyClass` container, but this cannot repair an interior that
> violates Java grammar. Tree-sitter parses these fragments with best-effort recovery, producing
> ASTs and DFGs that correspond to no semantically coherent program. The model's 99.9%+ safe
> confidence reflects that no valid Java program would ever look like this — the structural
> impossibility itself signals 'not malicious' to a model trained primarily on syntactically
> valid code."

## 7.5 P7 — Inter-procedural access patterns

> "Inter-procedural access patterns (P7) represent a fundamental architectural limitation. In
> one case the vulnerable code directly accesses credential fields (`userId`, `token`) from a
> parent Activity through a class cast; whether this constitutes a vulnerability depends
> entirely on the calling context — who invokes the method, under what conditions, and whether
> access is appropriately gated. In another, the vulnerability lies in how externally-provided
> data flows through multiple method boundaries before reaching a dangerous operation.
> Single-function analysis is structurally incapable of detecting these patterns: the evidence
> is distributed across the call graph."

## 7.6 P2, P3, P6, P4 — the remaining patterns

> **P2 (benign surface)**: "One case implements a synchronized random number generator with
> clean, idiomatic structure; the vulnerability is a threading race where the synchronized block
> does not protect all shared state. Another implements a systematic API version check with
> structured error reporting; the vulnerability is an incomplete error-handling path that looks
> defensive. Both follow patterns likely prevalent in the safe training class."

> **P3 (arithmetic edge case)**: "An animation interpolation function containing repeated
> floating-point division guarded by identity checks. The vulnerability is a divide-by-zero when
> two distinct keyframes share a timestamp — a case the identity guard does not cover. Detecting
> it requires understanding the guard's semantics and reasoning about valid input ranges."

> **P6 (control flow / flag logic)**: "A C signal function whose bitmask expression contains a
> duplicate flag (`DjVuFile::DECODE_STOPPED` appears twice in the OR condition). The DFG
> correctly captures data flows but cannot reason about the semantics of bitmask operations or
> identify redundant flag combinations."

> **P4 (Android API semantic bypass)**: "Misuse of Android API contracts — unvalidated
> `getStringExtra` calls and hardcoded resource identifiers. Detecting this requires knowledge
> of which specific API usage patterns are dangerous, semantic knowledge that cannot be derived
> from intra-function data flow analysis alone."

---

# Part 8 — Draft paper sentences

## 8.1 Introduction

> "Android malware has grown to encompass millions of applications, making automated static
> analysis at scale an urgent practical need. Data Flow Graph augmented transformers have
> demonstrated promising results for code understanding on clean source code, yet their
> applicability to decompiled Android bytecode — the only representation available for
> closed-source APKs — remains empirically untested. This paper makes three contributions: (1) we
> present the first end-to-end vulnerability scanning pipeline for arbitrary Android APKs,
> including DFG extraction from decompiled Java and Kotlin bytecode at scale; (2) we publicly
> release a 200,000-sample DFG-annotated multi-source vulnerability corpus; (3) through
> controlled ablation across three encoder backbones, we find that DFG-aware attention provides
> no consistent benefit on decompiled code, and explain this mechanistically through qualitative
> analysis of false negatives."

## 8.2 Dataset and pipeline

> "Our training corpus comprises 199,960 balanced samples drawn from four sources: LVDAndro
> (decompiled Android Java), Draper (C/C++ NVD/SARD CVEs), Devign (C/C++ QEMU/FFmpeg), and the
> Juliet Test Suite (synthetic CWEs), with a strict 1:1 safe-to-vulnerable ratio enforced across
> all sources."

> "All six transformer models are trained identically: an 82/8/10 train/val/test partition
> assigned by random shuffle with fixed seed 42, AdamW (lr 2e-5, ε 1e-8), gradient clipping at
> max norm 1.0, FP16 mixed precision, and validation-based checkpoint selection. The best
> validation checkpoint is evaluated once on the held-out test partition."

> ⚠️ The epoch budget sentence is deliberately omitted pending D1.

## 8.3 Model comparison and ablation

> "Table 1 presents the full comparison. All six transformer models cluster within a
> percentage-point accuracy band regardless of whether graph-augmented attention is applied.
> This convergence suggests the performance ceiling on decompiled Android vulnerability
> detection is determined by the data domain rather than model architecture."

> "Our controlled ablation yields no consistent directional effect from DFG augmentation across
> the three backbones; the sign of the effect depends on the backbone, and every magnitude is
> comparable to the variation measured across random seeds."

## 8.4 Limitations and qualitative analysis

> "The null DFG result is not architecturally inevitable — GraphCodeBERT's DFG attention
> demonstrably improves performance on clean source-level code. To understand why it fails on
> decompiled bytecode we analyse the most confident false negatives from our held-out test set.
> The mistakes reveal a coherent picture dominated by complete identifier obfuscation and
> structural fragmentation — decompilation artifacts that degrade DFG signal before it reaches
> the attention mechanism."

---

# Part 9 — Limitations

Ordered by severity. Those marked 🔄 changed materially on 2026-08-04.

## 9.1 Training and evaluation

**L1.1 🔄 — Epoch ceiling truncated two runs.** `codebert-train-text` and
`graphcodebert-train-text-only` selected their best checkpoint on the final epoch with
validation still rising, and early stopping never fired in any 5-epoch run. Their reported
accuracies are floors. Both are retrained at a raised ceiling (§4.3). *Supersedes the older
"fixed 3-epoch budget may undertrain the DFG mechanism" limitation, which described an abandoned
methodology and pointed the opposite way — under early stopping it is the text-only arms that
were undertrained.*

**L1.2 — DFG built over parser-recovery wrappers.** Decompiled fragments frequently lack
enclosing class or method context required for valid Java parsing. Each is wrapped in
`public class DummyClass { public void dummyMethod() { … } }`, applied uniformly regardless of
label. The DFG therefore includes wrapper-token edges alongside real ones. For long functions
this is a small fraction; for short obfuscated fragments — disproportionately the hard cases —
it is larger. This is an engineering necessity, not a flaw: excluding incomplete fragments would
discard a large, unrepresentable fraction of real decompiled code and bias the corpus toward
easier samples. The residual question — whether wrapper edges interfere with
vulnerability-relevant ones — cannot be answered without syntactically complete inputs that do
not exist for all samples.

**L1.3 — Test-set duplication.** 7.28% of the test partition is byte-identical to a training or
validation sample; removed from all reported metrics (§5.3).

**L1.4 — Same-APK leakage is unmeasurable.** All 199,960 filenames are unique, so there is no
filename-group leakage, but APK-level provenance was not preserved during corpus construction.
Whether two functions from the same APK straddle the train/test boundary cannot be determined
without regenerating the corpus.

## 9.2 Data and preprocessing

**L2.1 — Identifier semantics stripped by decompilation.** JADX replaces class, method and field
names with machine-generated tokens under ProGuard/R8. DFG attention was designed to track
meaningful flows between named variables; when names carry no information, edges connect tokens
the model cannot interpret. This is the primary explanation for the null result — and it limits
the text-only models too.

**L2.2 — Kotlin synthetic identifiers.** Lambda compilation and coroutines produce names like
`-$$Lambda$ClassName$hashcode`, non-semantic by design and structurally different from both
clean and ProGuard-obfuscated Java. Underrepresented in training.

**L2.3 — Structural fragmentation.** JADX sometimes emits output violating Java grammar. The
`DummyClass` wrapper cannot repair a syntactically invalid interior.

**L2.4 — Fractional sampling.** Each source was sampled, not used in full, to enforce class
balance. The sampled subset may not represent the full within-source distribution; Devign in
particular was selected without stratification by vulnerability type, function length or
language subset.

**L2.5 — DFG node budget.** Capped at 128 nodes. Long, complex functions — more common in Draper
and Devign — are likelier to hit the cap, potentially discarding vulnerability-relevant edges.

**L2.6 — 51 contradictory-label groups** (102 entries), all Devign.

## 9.3 Model and architecture

**L3.1 — Sliding-window DFG filtering is imprecise.** Chunk DFG nodes are filtered by substring
match (`node[0] in chunk_code`). For obfuscated code with single-letter variables (`a`, `i`,
`n`) this produces false matches — `i` matches any chunk containing the letter. Filtering by
character offset would be correct. Given the null result the practical impact is likely minimal,
but it means the sliding window's DFG quality is lower than achievable.

**L3.2 — Single-function analysis scope.** Models classify functions in isolation, with no
access to calling context, class-level state or inter-function flows. A substantial fraction of
real vulnerabilities are inter-procedural (pattern P7) and no single-function model can detect
them regardless of architecture.

**L3.3 — Context window truncation.** 384 tokens; the sliding window cannot recover signals
spanning chunk boundaries. Sequences up to 2,543 tokens were observed in Devign.

## 9.4 Evaluation and deployment

**L4.1 — Real-APK evaluation lacks ground truth.** 13 reports, 23,005 functions, reported as
rates and probability distributions. No labelling of which specific functions are genuinely
vulnerable, so precision and recall cannot be computed. The calibration result is an indirect
inference, not a direct measurement.

**L4.2 — InsecureShop flags below clean apps** (3.0% vs AntennaPod's 9.3%). The system cannot be
used as an APK-level binary classifier; it is a function-level triage signal.

**L4.3 — Commercial obfuscation defeats targeted filtering.** ProGuard/DexGuard collapse package
namespaces to single-letter paths, defeating the manifest-aware developer-code filter. The most
security-sensitive production apps are precisely those most likely to use it.

**L4.4 — Static analysis scope.** No access to runtime state, dynamic values, external
configuration or interaction flows.

**L4.5 — Juliet.** Reported separately, excluded from capability claims (§6.12).

## 9.5 External validity

**L5.1 — Devign domain gap** limits any C/C++ claim. The system should not be presented as a
general C/C++ vulnerability detector.

**L5.2 — Source imbalance.** LVDAndro and Draper contribute 75,000 each; Devign and Juliet
25,000 each. Learned representations are dominated by the first two.

**L5.3 — No SOTA comparison** (§6.3).

---

# Part 10 — Repository and provenance

## 10.1 Layout

| Path | Role |
|---|---|
| `dataset/dataset_graphcodebert.jsonl` | training corpus, 199,960 entries — **untouched** |
| `dataset/dataset_graphcodebert_dedup.jsonl` | released corpus, 189,938 entries |
| `training_notebooks/re_train/` | the six training notebooks, each carrying its own run's outputs |
| `training_notebooks/old_train/` | the pre-remediation notebooks — historical, do not run |
| `test_scripts/` | all evaluation scripts, plus `split_and_filter.py` and `scanner-pipeline.ipynb` |
| `test_scripts/test_3_multiseed_broken_down/` | the three multi-seed notebooks |
| `dataset_creation_scripts/` | raw APK → JSONL pipeline, plus `make_dedup_dataset.py` |
| `results/models/*.txt` | per-model training results |
| `results/` | evaluation outputs and figures |
| `APKs/` | the 13 APKs used for Test 9 |

**Everything is in one place as of 2026-08-04.** The `new_tests/` and `new_tests_ran/` staging
directories were folded into the canonical tree: the corrected evaluation scripts replaced their
predecessors in `test_scripts/`, and the executed CodeBERT retrains replaced the old Partition-B
notebooks in `training_notebooks/re_train/`. Two files were deleted rather than moved —
`test_scripts/test_3_multiseed.py`, which trained GraphCodeBERT+DFG while Table 3 reports
text-only, and the three duplicate `test-3-seed*.ipynb` copies that sat in the repository root.

## 10.2 Output-filename offset (documented, not fixed)

Scripts 3–6 write results numbered one higher than the script. Fixing only some would make it
less consistent, so it is all four or none — deferred until results are final.

| Script | Writes | |
|---|---|---|
| test-2-roc-auc | `test2_*` | ✓ |
| test_3_multiseed | `test4_multiseed_results.txt` | +1 |
| test-4-per-source | `test5_per_source_*` | +1 |
| test-5-mlp-baseline | `test6_baseline_*` | +1 |
| test-6-imbalanced | `test7_imbalanced_*` | +1 |
| test-7-qualitative | `test7_qualitative_*` | — |
| test-8-significance | `test8_*` | ✓ |
| test_9_scanner | `test9_*` | ✓ |

A rename breaks the figure filenames referenced throughout this document.

## 10.3 Fixes already applied to the evaluation scripts

| File | Fallback removed | Duplicate filter | Verified |
|---|:---:|:---:|:---:|
| `test-2-roc-auc.py` | n/a | ✓ *after* the split guard | ✓ |
| `test-4-per-source.py` | ✓ | ✓ | ✓ |
| `test-5-mlp-baseline.py` | n/a | ✓ | ✓ |
| `test-6-imbalanced-eval.py` | ✓ | ✓ | ✓ |
| `test-7-qualitative-analysis.py` | ✓ | ✓ | ✓ |

Each was verified by executing its own split block against the real dataset; all five reproduce
`163,967 / 15,997 / 19,996 → 18,541 clean`.

Incidental fixes made along the way:

- **test-2**: the duplicate filter runs *after* the split guard. The guard compares against
  `test_indices.npy` from the training notebooks, which holds the full 19,996; filtering first
  would fail the guard spuriously and look like a split mismatch.
- **test-2**: the guard is **fail-closed** and searches `/kaggle/input` and `/kaggle/working`
  recursively — a missing file is an error, not a silent skip.
- **test-4**: source logic split in two — `infer_source()` builds the split and deliberately
  finds nothing; `source_for_reporting()` recovers the source from the filename prefix for table
  rows only.
- **test-5**: streams the corpus instead of materialising all 199,960 entries with their `dfg`
  arrays on top of the TF-IDF matrices.
- **test-6**: threshold moved 0.5 → 0.60, and the threshold sweep is now written to the results
  file — which is what §6.7 needs.
- **test-7**: false negatives now record `corpus_idx` and `source`, so they are traceable across
  models and runs. **A results writer was added** — previously the top-20 existed nowhere but a
  Kaggle console log. Now writes `test7_qualitative_results.txt` and
  `test7_false_negatives.json`; numpy `float32`/`int64` casts fixed so `json.dump` no longer
  raises at the end of the run.
- **CodeBERT notebooks**: source-key loading streams the file instead of parsing all 199,960
  entries a second time, which was OOMing the kernel before epoch 1.

## 10.4 Blockers and loose ends

1. **🔴 Checkpoint paths are blank.** Every `weights` field in the eval scripts is `"" # TODO`.
   **Nothing in steps 2, 4, 5, 6 can run until these are filled.** This is precisely what let
   the split mismatch hide for two months — fill them in and commit them so every number is
   traceable to a checkpoint.
2. **Split guard needs a manual copy.** Training notebooks write `test_indices.npy` into their
   own output dirs; test-2 searches the Kaggle input dir. Upload the training run's output as a
   dataset and attach it.
3. **Unexplained drift.** test-2 reports GCB text at 88.78% / ROC 0.9612 and UniXcoder+DFG at
   89.07% / ROC 0.9621, but their notebooks say 88.93% / 0.9596 and 88.37% / 0.9602. Same
   partition, so they should match — likely a wrong checkpoint path in a Kaggle run. **Confirm
   during step 4.**
4. **`graphcodebert-train-dfg.ipynb` has cleared training outputs** — the one model whose numbers
   cannot be cross-checked against its own notebook.
5. **`test_3_multiseed.py` trains GraphCodeBERT+DFG**, but the three seed notebooks train
   text-only and Table 3 reports text-only. The notebooks are canonical; that `.py` should be
   **deleted, not fixed.**
6. **test-4 and test-7 run on GraphCodeBERT+DFG**, not UniXcoder as the pre-consolidation docs
   claimed. Validity is unaffected — both are on Partition N once fixed — but describe them
   correctly in Section 4.
7. **AMP**: `unixcoder-dfg-final.ipynb` is the only notebook still importing the deprecated
   `torch.cuda.amp`; the other five are on `torch.amp`. (An earlier note named
   `codebert-train-text.ipynb` here — that was wrong, it was already on `torch.amp`.)

## 10.5 Corpus-description fixes for the released artifact (post-submission)

Keep `CWE_ID` or emit one row per Draper function; exclude Juliet methods whose body contains
only calls to `goodG2B` / `goodB2G`.

---

## Document history

Consolidated 2026-08-04 from `README.md` (results sections), `RESEARCH_NOTES.md`,
`PAPER_DEFENSE.md`, `PAPER_TODO.md`, `REMEDIATION_PLAN.md`, `SPLIT_MISMATCH.md`,
`LIMITATIONS.md`, `after_inspection.md`, `analysis_results.md` and `instructions/README.md`.
Contradictions between those files were resolved against the code and the result files; stale
material was dropped rather than carried forward. The originals remain in git history.
