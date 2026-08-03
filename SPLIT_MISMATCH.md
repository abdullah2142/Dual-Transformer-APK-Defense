# Split Mismatch — Data Leakage in CodeBERT Results

> ### ⚠ Partially superseded — see [REMEDIATION_PLAN.md](REMEDIATION_PLAN.md)
> This document's diagnosis of the **CodeBERT** bug is correct and still stands. Its §6 "Fix"
> and "Re-run checklist" are **not** — two further problems were found afterwards:
> tests 4, 6 and 7 build a different partition again (89.9% of their test set is training
> data), and 6.88% of the test set is byte-duplicated in training. In particular the
> "do not re-run" list below is **wrong for tests 4, 6 and 7**, and the claim that the
> qualitative FN analysis is unaffected is **wrong**. Use REMEDIATION_PLAN.md for the
> action list.

> **Status**: Open. Blocks Table 2b, the CodeBERT row of Table 2, the CodeBERT ROC/PR curves,
> and the Ensemble rows of Table 5.
> **Does not block**: Table 1, the null-DFG finding, or the scanner.
> **Identified**: 2026-08-02

---

## 1. Summary

The repository contains **two different implementations of the 82/8/10 train/val/test split**.
The CodeBERT training notebooks use one; every other training notebook and *every* evaluation
script uses the other. The two produce different test partitions of the same 199,960-sample corpus.

Consequence: when an evaluation script grades a CodeBERT checkpoint, it rebuilds a test set that
was largely inside CodeBERT's **training** data. CodeBERT's evaluation-script scores are inflated
by roughly 4.8 percentage points of memorisation.

---

## 2. Background — why the split matters

The corpus is 199,960 samples. A 10% test partition (19,996 samples) is held back so the model is
graded on code it has never seen. A test score is only meaningful if the partition used at grading
time is the same one that was withheld at training time.

Two splits can both be correct, fair, and stratified — and still be *different sets*. Ten samples
split 80/20 might yield test = `{3, 7}` under one method and test = `{5, 9}` under another. Both
are valid. But a model trained under the first method has memorised sample 5, so grading it with
the second method's test set produces a score that measures recall of training data, not
generalisation.

---

## 3. Root cause

### Split A — `stratified_three_way_split()`

Per-source shuffle with `random.Random(seed)`, test taken as the leading slice of each source group.

```python
def stratified_three_way_split(entries, test_ratio=0.10, val_ratio=0.08, seed=42):
    rng = random.Random(seed)
    source_to_indices = defaultdict(list)
    for idx, entry in enumerate(entries):
        source_to_indices[infer_source(entry)].append(idx)
    for indices in source_to_indices.values():
        rng.shuffle(indices)
    ...
    test_alloc = allocate_counts(target_test, source_to_indices, test_ratio)
    for source, indices in source_to_indices.items():
        take = min(test_alloc[source], len(indices))
        test_indices.extend(indices[:take])
        trainval_groups[source] = indices[take:]
    ...
```

### Split B — `sklearn.train_test_split`

Two-stage stratified split driven by `numpy.random.RandomState` inside scikit-learn.

```python
all_indices = np.arange(len(full_dataset))
all_sources = np.array(full_dataset.sources)

trainval_indices, test_indices = train_test_split(
    all_indices, test_size=args.test_size,
    random_state=args.seed, stratify=all_sources)

trainval_sources = all_sources[trainval_indices]
train_indices, val_indices = train_test_split(
    trainval_indices, test_size=args.val_size_within_trainval,
    random_state=args.seed, stratify=trainval_sources)
```

Both target 82/8/10 stratified by source with `seed = 42`. They are nonetheless **independent
partitions**: `random.Random(42).shuffle` and scikit-learn's `RandomState(42).permutation` are
different generators consumed in different orders. Two independent 10% subsets of the same corpus
overlap in only about 10% of their members — meaning roughly 90% of one method's test set sits in
the other method's training set.

### Who uses which

| File | Split |
|---|:---:|
| `training_notebooks/re_train/graphcodebert-train-dfg.ipynb` | A |
| `training_notebooks/re_train/graphcodebert-train-text-only.ipynb` | A |
| `training_notebooks/re_train/unixcoder-dfg-final.ipynb` | A |
| `training_notebooks/re_train/unixcoder-text-only.ipynb` | A |
| **`training_notebooks/re_train/codebert-train-text.ipynb`** | **B** |
| **`training_notebooks/re_train/codebert-final-dfg.ipynb`** | **B** |
| `test_scripts/test-2-roc-auc.py` | A |
| `test_scripts/test-4-per-source.py` | A |
| `test_scripts/test-5-mlp-baseline.py` | A |
| `test_scripts/test-6-imbalanced-eval.py` | A |
| `test_scripts/test-7-qualitative-analysis.py` | A |
| `test_scripts/test_3_multiseed.py` | A |

The CodeBERT notebooks are the only files on Split B. Every grader is on Split A.

---

## 4. Evidence

Each model's own notebook grades it on its own (correct) partition. `test-2-roc-auc.py` grades
every model on Split A. For a model whose notebook is already on Split A, the two must agree.

| Model | Own notebook (`results/models/*.txt`) | `test-2` (`results/test2_auc_results.txt`) | Difference |
|---|:---:|:---:|:---:|
| UniXcoder text | 89.0778% | 89.0778% | **0.0000** |
| GraphCodeBERT+DFG | 88.5600% | 88.5727% | +0.013 |
| **CodeBERT text** | **88.5627%** | **93.3987%** | **+4.836** |
| **CodeBERT+DFG** | **88.5427%** | **93.1186%** | **+4.576** |

UniXcoder text matches to four decimal places — its notebook and the grader share Split A. Both
CodeBERT variants jump by nearly five points. A fixed checkpoint does not become five points more
accurate between two gradings; the only thing that changed is which samples it was asked about.

---

## 5. Impact

### Invalidated

| Artifact | Reason |
|---|---|
| **Table 2b** — cross-architecture McNemar | `GCB+DFG vs CodeBERT+DFG: Δ=−4.55%, p≈7.3e-114` is the memorisation bonus. On honest Table 1 numbers the gap is 88.5427% vs 88.5600% = **0.02%**. |
| Claim *"model choice matters more than DFG structure"* (RESEARCH_NOTES Part 3, Test 8) | Rests entirely on the row above. |
| **Table 2, CodeBERT row** (`p=0.0565`) | Both CodeBERT checkpoints scored on leaked data. |
| **`results/test2_roc_pr_curves.png`** | The two CodeBERT curves are inflated. |
| **Table 5, "Ensemble" rows** | The ensemble is GraphCodeBERT+DFG **+ CodeBERT** (`test-6-imbalanced-eval.py:279-287`), scored on Split A. |
| `results/test2_auc_results.txt`, `results/test8_significance_results.txt` | Contain the affected rows. |

### Safe — no action needed

- **Table 1** in full. Every row in `results/models/*.txt` was produced by that model's own
  notebook on its own matching partition. CodeBERT's 88.5627% / 88.5427% are honest.
- **The headline null-DFG finding.** It comes from within-backbone comparisons (text vs DFG on the
  same backbone), and both halves of every pair always share one split.
- **Table 2, GraphCodeBERT and UniXcoder rows** — both members of each pair are on Split A.
- Test 3 (multi-seed), Test 4 (per-source), Test 5 (baselines), Test 7 (qualitative FN), Test 9
  (scanner calibration).

---

## 6. Fix

### Decision: standardise on Split A

| Option | Retraining cost | Other work |
|---|:---:|---|
| **Standardise on Split A** | **2 runs** (CodeBERT ×2) | none — all graders already use A |
| Standardise on Split B | 4 runs (GCB ×2, UniXcoder ×2) | rewrite all 6 test scripts |

Split A is strictly cheaper. Re-grading the existing CodeBERT checkpoints under Split A is **not**
an option — they were trained on Split B, which overlaps Split A's test set, so no honest test
partition remains for those particular checkpoints. They must be retrained.

### Code change

In **both** `codebert-train-text.ipynb` and `codebert-final-dfg.ipynb`:

1. Delete the `train_test_split` block quoted in §3 (Split B).
2. Paste in `infer_source`, `allocate_counts`, and `stratified_three_way_split` verbatim from
   `graphcodebert-train-text-only.ipynb`, plus the call site:

```python
entries = load_entries(args.train_file)
assert len(entries) == len(full_dataset)

train_indices, val_indices, test_indices = stratified_three_way_split(
    entries,
    test_ratio=args.test_ratio,   # 0.10
    val_ratio=args.val_ratio,     # 0.08
    seed=args.seed,               # 42
)
```

3. Rename the `Args` fields to match: `test_size` → `test_ratio` (0.10), and replace
   `val_size_within_trainval = 8/90` with `val_ratio = 0.08`. `stratified_three_way_split` derives
   the within-trainval ratio itself, so passing `8/90` would double-adjust it.
4. Leave all hyperparameters untouched — 384 tokens, batch 16/32, lr 2e-5, AdamW, max norm 1.0,
   FP16, max 5 epochs, patience 2.

### Re-run checklist

**Retrain (GPU, Kaggle):**

- [ ] `codebert-train-text.ipynb` → new `results/models/codebert_results.txt`
- [ ] `codebert-final-dfg.ipynb` → new `results/models/codebert_dfg_results.txt`

**Re-run (inference / CPU only, no retraining):**

- [ ] `test-2-roc-auc.py` → new `test_probs_*.npy`, `test2_auc_results.txt`, `test2_roc_pr_curves.png`
- [ ] `test-8-significance-testing.py` → new `test8_significance_results.txt` (seconds, CPU)
- [ ] `test-6-imbalanced-eval.py` → new `test7_imbalanced_results.txt`, `test7_precision_recall_bar.png`

**Do not re-run:** Test 3 (×3 seed notebooks), Test 4, Test 5, Test 7, Test 9, and the four
GraphCodeBERT/UniXcoder training notebooks.

**Total: 2 GPU training runs + 3 cheap re-runs.**

### Expected outcome

Table 2b's −4.55% gap should collapse to roughly 0.02% and become non-significant. If it does, the
cross-architecture claim is retired and the paper reports a clean result: *all six configurations
converge to an 88–89% band; neither DFG augmentation nor backbone choice moves the needle beyond
seed noise.* That is a stronger and more defensible story than the current one.

---

## 7. Open questions to resolve during the re-run

### 7.1 Unexplained drift on Split A models

Two models on Split A still disagree between their notebook and `test-2`, which should be
impossible:

| Model | Own notebook | `test-2` | Gap |
|---|:---:|:---:|:---:|
| GraphCodeBERT text | 88.9300% | 88.7828% | −0.147 |
| UniXcoder+DFG | 88.3727% | 89.0728% | +0.700 |

Most likely a wrong checkpoint path pasted into a Kaggle run. Table 2's GraphCodeBERT and
UniXcoder p-values depend on these files, so confirm before writing Section 4.

### 7.2 Checkpoint provenance is not recorded

Every `weights` field in `test_scripts/*.py` is a blank `# TODO` placeholder:

```python
gcb_dfg_weights       = "" # TODO: /kaggle/input/.../model.bin
codebert_dfg_weights  = "" # TODO: /kaggle/input/.../model.bin
```

No run's model provenance exists anywhere in the repo. Fill these in and commit them so every
number is traceable to a checkpoint. This is what allowed the mismatch to go unnoticed.

### 7.3 Add a split-consistency guard

To prevent recurrence, have each training notebook write its test indices to disk, and have each
evaluation script assert against them:

```python
np.save(f'{args.output_dir}/test_indices.npy', np.array(test_indices))
# in every test script:
assert np.array_equal(test_indices, np.load('.../test_indices.npy')), 'split mismatch'
```

---

## 8. Related documentation corrections

Independent of this bug, found while tracing it:

- `README.md` states Test 4 (per-source) and Test 7 (qualitative FN) run on UniXcoder. Both
  scripts actually load GraphCodeBERT. Validity is unaffected — both are Split A — but the
  description must be corrected before it reaches the paper.
- `PAPER_DEFENSE.md` §10 cites calibration as 89.2% / 5.2% / 5.6%; `results/test9_scanner_calibration.txt`
  says 84.0% / 8.9% / 7.1%. Same section cites InsecureShop 4.8% vs AntennaPod 8.4%; results say
  3.0% vs 9.3% — the counterintuitive inversion is *wider* than the defense assumes.
- `PAPER_DEFENSE.md` §1 cites "1,184 false negatives"; the qualitative analysis ran on
  UniXcoder+DFG, which has 1,125.
- `PAPER_DEFENSE.md` §7 defends threshold 0.60 with "F1 maximised at 0.60, 83.4% recall, 7.8% FPR".
  `results/test7_imbalanced_results.txt` contains no threshold sweep — it evaluates only at 0.5.
  The scanner ships at 0.60, so this needs a sweep or the claim must be dropped.
- `LIMITATIONS.md` still describes the abandoned fixed-3-epoch / no-validation-set methodology
  (L1.1), reports significance testing as pending (L1.4), and cites stale figures (Juliet n=2,533,
  Devign 67.58%).
