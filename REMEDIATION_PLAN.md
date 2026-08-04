# Remediation Plan — Verified Status and Execution Sequence

> **Authoritative action list.** Supersedes the "Fix" and "Re-run checklist" sections of
> [SPLIT_MISMATCH.md](SPLIT_MISMATCH.md), which were written before the second and third
> issues were found and whose "do not re-run" list is wrong for tests 4, 6 and 7.
>
> **Status**: step 1 done (2026-08-03), step 3 done (2026-08-04, → `new_tests_ran/`).
> A fourth problem — the epoch ceiling — was found on 2026-08-04; see §5.3.
> Last verified 2026-08-04.
> **Cost to complete**: 2 GPU training runs + 6 evaluation re-runs, plus up to 3 more
> GPU runs if Table 3 is re-measured at the new ceiling.

---

## 1. TL;DR

Four separate problems were found. Three are serious and must be fixed; the third is a
disclosure, not a defect.

| # | Problem | Effect | Fix |
|---|---|---|---|
| 1 | CodeBERT trained on a different split than every grader rebuilds | reads 93.4% vs its honest 88.56% | ~~retrain CodeBERT ×2~~ **done 2026-08-04** |
| 2 | Tests 4, 6, 7 build a different split than training used | **89.9% of their test set is data the model trained on** | delete ~8 lines from each; re-run |
| 3 | 6.88% of the test set is byte-identical to a training sample | ~0.7pp inflation, applies to all models equally | disclose in Limitations |
| 4 | Two text-only runs hit the 5-epoch cap with validation still rising; early stopping never fired in any 5-epoch run | their accuracies are floors, and the CodeBERT DFG delta reverses sign | raise the ceiling; retrain 2 (§5.3) |

**The paper's core finding is unaffected.** "DFG does not help on decompiled code" rests on
within-backbone comparisons — same backbone, same partition, both sides trained and graded
identically. Problems 1–3 do not touch it.

**The paper's explanation of that finding is affected.** Section 8 (top-20 false negatives,
patterns P5a/P5b/P1) comes from test-7, which is on the contaminated partition.

---

## 2. Three partitions exist

All three target 82/8/10 stratified, seed 42. They are different sets.

| Partition | Built by | Used in |
|---|---|---|
| **N** | `stratified_three_way_split` / `get_stratified_indices` — `random.Random(42)`, per-source shuffle. `infer_source` returns `"unknown"` for every entry, so it degenerates to one group = a plain random shuffle | GraphCodeBERT ×2, UniXcoder ×2, test-2, test-3, test-5, test-8 |
| **S** | same function, but `infer_source` has a **filename-prefix fallback** that recovers the real source → 4 groups | test-4, test-6, test-7 |
| **B** | `sklearn.train_test_split(random_state=42, stratify=...)` | CodeBERT ×2 |

**Target end state: everything on Partition N.**

---

## 3. Verified evidence

Measured against the real `dataset/dataset_graphcodebert.jsonl` (199,960 entries), not estimated.

### 3.1 Partition N is confirmed to be what training used
- Simulated N yields `train=163,967 val=15,997 test=19,996` — byte-identical to the split
  sizes printed in every training notebook's saved output.
- Every notebook's stored final test ROC-AUC matches `results/models/*.txt` exactly:
  CodeBERT 0.9610, CodeBERT+DFG 0.9604, GCB text 0.9596, UniXcoder+DFG 0.9602,
  UniXcoder text 0.9622 (5/5). **Table 1's provenance is verified end to end.**

### 3.2 Tests 2, 3, 5 are provably clean
Rebuilding their test set gives **symmetric difference = 0** against the notebook test set.

### 3.3 Tests 4, 6, 7 are contaminated — measured
```
test_S overlapping the true test set :  2,018  (10.09%)
test_S sitting in TRAINING           : 16,427  (82.15%)   <- leaked
test_S sitting in VALIDATION         :  1,551  ( 7.76%)
                                        -> 89.91% previously seen
```

### 3.4 CodeBERT's leakage — empirical
| Model | own notebook | test-2 (Partition N) |
|---|---:|---:|
| UniXcoder text | 89.0778% | 89.0778% (exact) |
| CodeBERT text | 88.5627% | **93.3987%** |
| CodeBERT+DFG | 88.5427% | **93.1186%** |

Nothing in the repo's history produces 93% honestly (the old-methodology CodeBERT was
88.4777%), so leakage is the only explanation.

### 3.5 Dataset audit — `results/test0_leakage_audit.txt`
- Keys are exactly `code, dfg, label, filename`. None of `source/dataset/origin/project`
  exist → `infer_source` returns `"unknown"` for all 199,960 entries. **The split is not
  stratified.** `results/models/codebert_results.txt` claiming "source-stratified" is false.
- `filename` = `LVDAndro_279755_file`; prefix partitions cleanly into
  LVDAndro 75,000 / Draper 75,000 / Juliet 25,000 / Devign 24,960.
- **All 199,960 filenames are unique** → no filename-group leakage. But APK-level provenance
  is not preserved, so same-APK leakage is unmeasurable without regenerating the corpus.
- Exact duplicates: 1,375 / 19,996 test entries (6.88%) are byte-identical to a training
  sample. By source: **Juliet 26.68%, Draper 9.19%, Devign 0.38%, LVDAndro 0.01%**.
  Largest duplicate group = 813 identical copies of one Juliet function.
- 51 groups carry contradictory labels (102 entries).

---

## 4. What is safe, what is broken

| Paper claim | Source | Partition | Status |
|---|---|---|---|
| **DFG doesn't help** (Tables 1, 2) | `models/*.txt` + test-8 | N | **safe**, but the CodeBERT and GCB **text-only** rows are floors until §5.3's retrain; the CodeBERT DFG delta currently reverses sign |
| Training stability ±0.10% (Table 3) | test-3 | N | **safe**, but measured on the 5-epoch config — see §5.3 |
| Transformers beat TF-IDF | test-5 | N | **safe** |
| Cross-architecture gap (Table 2b) | test-8 | N vs B | **broken** — CodeBERT artifact |
| Per-source generalisation (Table 4) | test-4 | S | **broken** |
| Deployment behaviour (Table 5) | test-6 | S | **broken** + model changed (§5.2) |
| **Why DFG fails** (Section 8) | test-7 | S | **broken** |
| Real APK calibration (Test 9) | APK reports | none | **safe** |

---

## 5. Execution sequence

| # | Step | Depends on | Cost |
|---|---|---|---|
| 1 | ~~Edit tests 4, 6, 7 — delete the filename fallback; add the duplicate filter to tests 2, 4, 5, 6, 7~~ **DONE 2026-08-03** | — | text edit |
| 2 | Re-run test-4, test-7, **test-6** | already-trained checkpoints | GPU inference |
| 3 | ~~Retrain CodeBERT text + CodeBERT+DFG~~ **DONE 2026-08-04** → `new_tests_ran/` | — | 2 GPU training runs |
| 3b | **Raise the epoch ceiling and retrain `codebert-train-text` + `graphcodebert-train-text-only`** (§5.3) | — | **2 GPU training runs** |
| 4 | Re-run test-2 | step 3b checkpoints | GPU inference |
| 5 | Re-run test-8 | test-2's `.npy` | CPU, seconds |
| 6 | Re-run test-5 | test-2's `.txt` | CPU |
| 7 | Re-run test-3 ×3 seeds, **or** relabel Table 3 as measuring the 5-epoch config (§5.3) | step 3b | 3 GPU runs, or a doc edit |

Step 2 blocks on nothing — tests 4 and 7 use GraphCodeBERT+DFG and test-6 now uses UniXcoder
text-only, all already trained. So **Table 4, Table 5 and Section 8 can all be fixed before
any GPU training starts.** Only test-2 (and its two downstream CPU steps) waits on the
CodeBERT retrain.

Steps 5 and 6 can be appended as cells in the same Kaggle notebook as step 4, avoiding two
dataset uploads: test-5 reads `/kaggle/working/test2_auc_results.txt` and test-8 searches
`/kaggle/working` for the `.npy` files.

### Why each

- **test-4** → Table 4. Per-source numbers (LVDAndro 97.07%, Juliet 100%, Devign 68.91%)
  measured on seen data.
- **test-7** → Section 8. The top-20 false negatives may be training samples, so the
  P5a/P5b/P1 mechanism rests on the wrong examples. **Highest priority** — it is what turns
  the negative result into a contribution.
- **test-6** → Table 5. Split mismatch, *and* the model changed to UniXcoder text-only with
  the ensemble removed (§5.2). No longer depends on CodeBERT.
- **CodeBERT ×2** → Table 2b. The "−4.55%, p≈1e-114" row is entirely artifact; the real gap
  is 0.02%.
- **test-2** → regenerates the `.npy` files everything downstream reads, plus the ROC/PR figure.
- **test-8** → new McNemar p-values. Expect Table 2b to collapse to non-significant. **This is
  the pass/fail check for the whole exercise.**
- **test-5** → pulls its transformer rows from `test2_auc_results.txt`.

### 5.1 Duplicate filter at evaluation time (folds into steps 1–7)

Training data is **not** changed and no retraining is added. The filter removes test entries
whose `code` is byte-identical to a train/val entry, so the model is measured only on code it
never saw. Drop-in implementation: **`new_tests/split_and_filter.py`** — paste
`get_split_indices()` into test-2, test-4, test-6, test-7, replacing their existing
`get_test_indices` / `get_stratified_indices` / `get_test_indices_by_source`.

**Kaggle: no path change and no new upload.** Hashes are computed from the same JSONL the
scripts already read. The function also streams the file instead of holding all 199,960
records (with their `dfg` arrays) in RAM.

The same block also removes the filename fallback from tests 4/6/7 — so step 1 and this
filter are one edit, not two.

Measured effect (verified 2026-08-03):

```
Split: train=163,967  val=15,997  test=19,996
Filter: dropped 1,455 (7.28%)  ->  18,541 clean test entries
```

| Source | test | clean | dropped | % |
|---|---:|---:|---:|---:|
| LVDAndro | 7,483 | 7,482 | 1 | 0.0% |
| Draper | 7,626 | 6,856 | 770 | 10.1% |
| Juliet | 2,489 | 1,815 | 674 | 27.1% |
| Devign | 2,398 | 2,388 | 10 | 0.4% |
| **TOTAL** | **19,996** | **18,541** | **1,455** | **7.3%** |

> **Note on 1,455 vs the audit's 1,375.** `results/test0_leakage_audit.txt` counted overlap
> with the *training* set only. The filter also removes overlap with *validation*, which is
> correct — validation drove checkpoint selection, so those samples are not clean either.
> Use **1,455 / 7.28% / 18,541** in the paper.

### 5.2 test-6 model change — OPEN DECISION on the scanner

`test-6` now evaluates **UniXcoder text-only** (89.0778%, best in Table 1) and the **ensemble
has been removed** (commit `0596f64`). Rationale: GCB+DFG is the weaker variant of the middle
backbone, so using it for the deployment table contradicts the paper's own null-DFG finding;
`PAPER_TODO.md:86` already carried this as an open item, and `README.md:221` already described
test-6's inputs as UniXcoder while Table 5 reported GCB+DFG. The ensemble was a plain 50/50
probability average of GCB+DFG and CodeBERT text, never defined in any document despite being
reported in three of them.

**Consequence — test-6 moves from Wave 2 to Wave 1.** It no longer needs CodeBERT, so it can
run alongside tests 4 and 7 before any retraining.

**Consequence — Table 5 changes shape**: four rows (GCB+DFG ×2, Ensemble ×2) become two rows
(UniXcoder ×2). The current 94.64% / 94.14% / 5.31% figures are superseded twice over — the
model changed *and* the test set is now duplicate-filtered.

> #### ⚠ OPEN: the scanner still deploys GraphCodeBERT+DFG
>
> `README.md:29` routes the pipeline through `GraphCodeBERT + DFG` at threshold 0.60, and
> `test_scripts/scanner-pipeline.ipynb` loads that checkpoint. With test-6 now measuring
> UniXcoder text-only, **Table 5 characterises a configuration the system does not ship** —
> the deployment table and the deployed system disagree.
>
> Three options:
>
> | Option | Work | Consequence |
> |---|---|---|
> | Switch the scanner to UniXcoder text-only | re-run scanner over 13 APKs, then re-run Test 9 | consistent throughout; Test 9's calibration numbers (84.0% / 8.9% / 7.1%) and all per-APK flag rates change |
> | Keep the scanner on GCB+DFG, revert test-6 | none | back to contradicting the null-DFG finding |
> | Keep both, state the split explicitly | doc edit only | Table 5 = "best model under deployment-realistic imbalance"; Section 7 = "deployed configuration". Defensible but needs saying plainly, and invites "why not deploy the best model?" |
>
> Decide before writing Section 7. The first option is the only one where the paper's
> deployment story is internally consistent, but it is the only one that costs GPU time.
> Also note `PAPER_DEFENSE.md` §7's threshold-0.60 defence was derived on GCB+DFG; if the
> scanner changes, the threshold sweep must be re-derived on UniXcoder.

### 5.3 Epoch ceiling — decided 2026-08-04

**Decision: raise the epoch ceiling for the runs that hit it with validation still improving,
and retrain them.**

#### What was actually configured

Verified against the `Args` block of all six training notebooks, not the docs:

| Run | Max epochs | Patience | Best epoch | How it ended |
|---|:---:|:---:|:---:|---|
| `codebert-train-text` (retrain) | 5 | 2 | **5** | hit cap, still improving |
| `codebert-final-dfg` (retrain) | 5 | 2 | 4 | hit cap at patience 1/2 |
| `graphcodebert-train-text-only` | 5 | 2 | **5** | hit cap, still improving |
| `graphcodebert-train-dfg` | **10** | **3** | 5 | had genuine room |
| `unixcoder-text-only` | 5 | 2 | 4 | hit cap at patience 1/2 |
| `unixcoder-dfg-final` | 5 | 2 | 4 | hit cap at patience 1/2 |

Two findings from this:

1. **The docs were wrong.** `README.md` and `RESEARCH_NOTES.md` Part 2 both claimed *both*
   GraphCodeBERT models had the 10 / 3 ceiling. Only the DFG one does.
   `RESEARCH_NOTES.md` Decision 3 (Part 5) had it right, so Part 2 and Part 5 contradicted
   each other. Both are now corrected.
2. **Early stopping never fired in any of the five 5-epoch runs.** Every one terminated on
   `num_train_epochs`. What the paper describes as validation-based early stopping operated in
   practice as a fixed 5-epoch budget with best-checkpoint selection. `PAPER_DEFENSE.md` §4
   defends the protocol on the grounds that it lets each model "train until it reaches its true
   capability upper bound" — that defence does not survive as written.

#### Which runs are affected

Validation trajectories (accuracy %, per epoch):

```
codebert-train-text            86.64  87.84  88.09  88.26  88.31   <- new best on the LAST epoch
graphcodebert-train-text-only  86.45  87.90  88.71  88.86  89.04   <- new best on the LAST epoch
codebert-final-dfg             86.63  87.74  87.89  88.32  88.15       peaked at 4
unixcoder-dfg-final            86.77  87.96  88.44  88.71  88.29       peaked at 4
unixcoder-text-only            87.22  88.55  88.94  88.99    —         peaked at 4
```

Both truncated runs are **text-only arms**, which cuts differently per backbone:

- **GraphCodeBERT** — the protocol already favoured the DFG arm (10 / 3 against 5 / 2) and DFG
  still lost by 0.37pp. Giving text its fair ceiling can only widen that gap. The null-DFG
  conclusion is safe here and probably strengthened.
- **CodeBERT** — both arms shared the 5 / 2 cap, but only text was still climbing at it, and
  after the Partition-N retrain text is the arm that *lost* (88.2476% against 88.5527%, a
  +0.31pp win for DFG that reverses the sign of the old −0.02pp). This is the one place in the
  study where the epoch cap could be manufacturing the result, and it is the row a reviewer
  will go after.

#### Cost and consequences

- **2 GPU training runs** (`codebert-train-text`, `graphcodebert-train-text-only`).
- **Step 4 (test-2) now waits on step 3b**, not step 3 — the CodeBERT text checkpoint from
  `new_tests_ran/` will be superseded. Steps 5 and 6 follow test-2 as before.
- **Table 3 (multi-seed) is implicated.** `test-3-seed{42,123,2025}` train GCB text-only at
  5 / 2 — the same truncated configuration. If GCB text-only moves to a higher ceiling, the
  ±0.10% stability figure no longer measures the configuration in Table 1. Either re-run the
  three seed notebooks at the new ceiling (3 more GPU runs) or state plainly that Table 3
  characterises the 5-epoch configuration. This matters because ±0.10% is the yardstick
  `PAPER_DEFENSE.md` §2 uses to judge whether the DFG deltas are noise.
- `PAPER_DEFENSE.md` §4 needs rewriting either way (see finding 2 above).

#### Open: what ceiling, and for whom

Raising the ceiling *only* for the runs that hit it is **data-dependent stopping** — extra
budget goes exactly to the models that would benefit from it. It is defensible if stated
plainly, but the cleaner protocol is to put all six on a common 10 / 3 budget and let early
stopping actually decide. That costs 4 more GPU runs (6 total rather than 2). Decide before
writing Section 3; the paper has to describe one protocol, uniformly applied.

### Not touched
- **test-3** (3 seed notebooks) — same split logic as training; split seed pinned at 42 while
  only the training seed varies. Correct as-is. (Its reported accuracy is on the unfiltered
  test set; either re-run with the filter for consistency or state that Table 3 is unfiltered.)
- **test-9 / scanner** — no split dependency. Re-run only if the deployed checkpoint changes.
- **GraphCodeBERT ×2, UniXcoder ×2** — notebooks and graders already agree.

---

## 6. Decisions already made

- **Deduplication of TRAINING data: skipped.** It would change the partition and cost 9 GPU
  runs instead of 2, and it cancels out of a within-backbone difference anyway.
- **Deduplication of the TEST set: adopted** (§5.1). Costs nothing, removes the memorisation
  component from every reported metric, and yields Juliet's real accuracy on 1,815 unseen
  samples instead of 100% on a memorised 2,489.
- **Release artifact: ship the deduplicated corpus.** Contribution 2 is the corpus itself, so
  releasing it with a known duplication bug undercuts the contribution.
  `dataset/dataset_graphcodebert_dedup.jsonl` (189,938 entries) is already generated and
  verified. State plainly: *"the released corpus is deduplicated; models here were trained on
  the pre-deduplication version and evaluated on a deduplicated test partition."*
- **Fix direction for problem 2: strip the fallback from tests 4/6/7**, rather than adding
  stratification to the notebooks. Both are correct; this one costs no retraining.
- **Original dataset is untouched.** `dataset_graphcodebert.jsonl` still has its
  Dec 28 2025 timestamp; the dedup script only ever read it.

---

## 7. Required write-up changes

- **Drop the Juliet 100% claim.** 27.1% of Juliet's test set is verbatim in train/val. Report
  the filtered accuracy on 1,815 clean samples, as a synthetic sanity check rather than
  capability. (`LIMITATIONS.md` L4.5 already argues this — now there is a number.)
- **Disclose duplication with its cause** (both mechanisms confirmed in
  `dataset_creation_scripts/`; no dedupe step exists anywhere in that pipeline):
  > "7.3% of test samples were byte-identical to a training or validation sample and are
  > excluded from all reported metrics. Two corpus-construction artifacts account for them:
  > Draper functions carrying multiple CWE labels were emitted once per CWE and the
  > distinguishing `CWE_ID` field was dropped at the merge step (`finalizedataset.py`),
  > collapsing them into duplicates (8,281 copies, all label=1); and Juliet's per-file
  > `good()` dispatcher methods — test scaffolding containing no vulnerability logic — were
  > captured by a `startswith('good')` rule in `julietprocess.py` (7,016 copies, 5,851
  > label=0; the largest single group is 813 identical copies). LVDAndro, on which all
  > Android claims rest, is unaffected at 0.01%. The 51 code bodies carrying contradictory
  > labels are all Devign."
- **Corpus-description fixes for the released artifact** (optional, post-submission): keep
  `CWE_ID` or emit one row per Draper function; exclude Juliet methods whose body contains
  only calls to `goodG2B`/`goodB2G`.
- **Stop calling the split "stratified."** It is a plain random shuffle.
  `results/models/codebert_results.txt` says "source-stratified" — false.
- **Per-source test counts change** to 7,483 / 7,626 / 2,489 / 2,398 (LVDAndro / Draper /
  Juliet / Devign). The tidy 7,500 / 7,500 / 2,500 / 2,496 in Table 4 was the artifact.
- Fix `README.md`: Test 4 and Test 7 are described as running on UniXcoder; both scripts
  load GraphCodeBERT.
- `PAPER_DEFENSE.md` §10 calibration figures are stale (says 89.2%/5.2%/5.6%;
  `results/test9_scanner_calibration.txt` says 84.0%/8.9%/7.1%). §1 cites 1,184 FNs; the
  qualitative run used UniXcoder+DFG at 1,125. §7 defends threshold 0.60 with a sweep that
  `test7_imbalanced_results.txt` no longer contains.
- `LIMITATIONS.md` still describes the abandoned fixed-3-epoch / no-validation methodology.

---

## 8. Open items

- **Checkpoint provenance.** Every `weights` field in the test scripts is a blank `# TODO`.
  Fill in and commit after the runs — this is what let the mismatch hide for two months.
- **Unexplained drift.** test-2 reports GCB text at 88.78% / ROC 0.9612 and UniXcoder+DFG at
  89.07% / ROC 0.9621, but their notebooks say 88.93% / 0.9596 and 88.37% / 0.9602. Same
  partition, so they should match. Likely a wrong checkpoint path in a Kaggle run. Confirm
  during step 4.
- **`graphcodebert-train-dfg.ipynb` has cleared outputs** — the one model whose numbers
  could not be cross-checked against its own notebook.
- **`test_3_multiseed.py` trains GraphCodeBERT+DFG**, but the three seed notebooks train
  text-only and Table 3 reports text-only. The notebooks are canonical; that `.py` should be
  deleted, not fixed. (Resolves the open question in `RESEARCH_NOTES.md` Part 8.)
- **Split guard**: `new_tests/test-2-roc-auc.py` now asserts test indices against a saved
  file. The notebooks write `saved_models_codebert/test_indices.npy`; test-2 reads from the
  Kaggle *input* dir — needs a manual copy between runs.
- **AMP**: `new_tests/codebert-train-text.ipynb` still uses the deprecated
  `torch.cuda.amp` import. `codebert-final-dfg.ipynb` is already on `torch.amp`.

---

## 9. File inventory

**Ready in `new_tests/`** (split fix verified byte-identical to the GraphCodeBERT reference,
`val_ratio=0.08` correct, fail-closed split guard, `test8_` output filename fixed):
`codebert-train-text.ipynb`, `codebert-final-dfg.ipynb`, `test-2-roc-auc.py`,
`test-6-imbalanced-eval.py`, `test-8-significance-testing.py`

**Tooling written and run**: `new_tests/test-0-leakage-audit.py`,
`new_tests/make_dedup_dataset.py` → `results/test0_leakage_audit.txt`,
`results/test0_dedup_report.txt`

### Step 1 completed — 2026-08-03

All five evaluation scripts now live in `new_tests/` and each was verified by executing its
own split block against the real dataset. Every one reproduces
`train=163,967 val=15,997 test=19,996 → 18,541 clean`.

| File | Fallback removed | Duplicate filter | Verified |
|---|:---:|:---:|:---:|
| `test-2-roc-auc.py` | n/a (already correct) | ✓ *after* the split guard | ✓ |
| `test-4-per-source.py` | ✓ | ✓ | ✓ |
| `test-5-mlp-baseline.py` | n/a (already correct) | ✓ | ✓ |
| `test-6-imbalanced-eval.py` | ✓ | ✓ | ✓ |
| `test-7-qualitative-analysis.py` | ✓ | ✓ | ✓ |

Incidental fixes made along the way:

- **test-2**: the duplicate filter is applied **after** the split guard. The guard compares
  against `test_indices.npy` written by the training notebooks, which holds the full 19,996;
  filtering first would fail the guard spuriously and look like a split mismatch.
- **test-4**: source logic split in two — `infer_source()` builds the split and deliberately
  finds nothing; `source_for_reporting()` recovers the source from the filename prefix for
  table rows only.
- **test-5**: `get_stratified_indices` now streams instead of materialising all 199,960
  entries (each carrying a large `dfg` array) on top of the TF-IDF matrices; hashes are
  collected in that same pass.
- **test-7**: false negatives now record their index into the original JSONL
  (`corpus_idx`) plus `source`, so they are traceable and comparable across models/runs —
  Section 8's hand-classification depends on stable identifiers.
- **test-7**: **added a results writer** — previously it printed to stdout only, so the
  top-20 false negatives existed nowhere but a Kaggle console log. Now writes
  `test7_qualitative_results.txt` (summary + top-20 table + full code for classification)
  and `test7_false_negatives.json` (all FNs, code omitted). Fixed numpy `float32`/`int64`
  casts that would have made `json.dump` raise at the very end of the run.
- `hashlib` imports added to tests 2, 4, 5, 6, 7; `val_ratio = 0.08` added to test-7's `Args`.

### Output-filename offset (documented, not changed)

Scripts 3–6 write results files numbered one higher than the script. Renaming only test-6
would make this *less* consistent, so it is all four or none — deferred until after results
are final, when the docs are being edited anyway.

| Script | Writes | |
|---|---|---|
| test-2-roc-auc | `test2_*` | ✓ |
| test_3_multiseed | `test4_multiseed_results.txt` | +1 |
| test-4-per-source | `test5_per_source_*` | +1 |
| test-5-mlp-baseline | `test6_baseline_*` | +1 |
| test-6-imbalanced | `test7_imbalanced_*` | +1 |
| test-7-qualitative | `test7_qualitative_*` (new) | — |
| test-8-significance | `test8_significance_*` | ✓ |
| test_9_scanner | `test9_*` | ✓ |

A rename would break the image embed at `README.md:132`
(`results/test7_precision_recall_bar.png`) and source pointers at
`RESEARCH_NOTES.md:490-491`.
