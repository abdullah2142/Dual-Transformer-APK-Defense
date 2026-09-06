# Test 3 — three cold-start seeds WITHOUT LR warmup (superseded)

~28 GPU hours, 2026-09-05. **Not Table 3.** Kept because they answer one question
cleanly and are confounded on another, and both facts are worth recording.

| seed | accuracy | ROC-AUC | F1 | FN / FP | stopped |
|---|---:|---:|---:|---:|---|
| 42 | 88.0050% | 0.9561 | 0.8763 | 1,278 / 946 | early @7 |
| 123 | 88.1883% | 0.9570 | 0.8789 | 1,208 / 982 | early @6 |
| 2025 | 87.9348% | 0.9582 | 0.8745 | 1,362 / 875 | early @6 |

mean **88.0427%**, sample sd **0.1309pp**, range 0.2535pp.

Config: GraphCodeBERT text-only, cold start from `microsoft/graphcodebert-base`,
512 train / 384 eval, 10 epochs / patience 2, filtered 18,541 partition, split
seed 42 fixed. All three internally consistent.

## Why superseded

`num_warmup_steps = 0`, while `graphcodebert-train-text-only.ipynb` — which
produced Table 1's checkpoint — uses `int(total_steps * 0.1)`. Everything else
matched. Measured cost of that one difference on seed 42: **−0.2642pp**
(88.0050% against Table 1's 88.2692%).

## What they establish, and it survives the defect

All three runs share the config, so the seed comparison among them is valid.
Per-sample, on the same 18,541 rows:

| comparison | classified differently | \|b−c\| | McNemar p |
|---|---:|---:|---:|
| seed 42 vs 123 | 1,376 (7.42%) | 34 | 0.374 |
| seed 42 vs 2025 | 1,341 (7.23%) | 13 | 0.743 |
| seed 123 vs 2025 | 1,247 (6.73%) | 47 | 0.193 |
| **GCB text vs GCB+DFG** (test-8) | **1,298 (7.00%)** | **76** | **0.037** |

**Changing only the random seed moves as many predictions as changing the
architecture does.** Reseeding flips ~7% of classifications; swapping text→DFG
flips ~7%. What separates the DFG comparison is not the volume of churn but its
directional imbalance (76 against 13–47), which is precisely what McNemar tests.

All three seeds agree on 16,559 samples (89.31%); at least one dissents on 1,982
(10.69%). Seed choice alone moves false negatives by up to 154 and false
positives by up to 107.

## What they CANNOT establish — the confound

Comparing each of these text models against the GCB+DFG checkpoint gives
p = 0.480 / 0.107 / 0.725, none significant, against test-8's 0.037. **That is
not evidence the GCB result is fragile.** The DFG checkpoint has warmup and these
do not, so the text arm carries a ~0.26pp handicap in every one of those
comparisons — comparable in size to the 0.410pp effect under test.

Adding the measured warmup shift back:

| seed | observed delta vs DFG | projected with warmup |
|---|---:|---:|
| 42 | +0.146pp | +0.410pp |
| 123 | +0.329pp | +0.593pp |
| 2025 | +0.076pp | +0.340pp |

Mean projected **+0.448pp**, straddling Table 1's +0.410 rather than falling
below it. The question is open; this data cannot close it.

## Files

`test3_seed{42,123,2025}_results.txt` and `_probs.npy` (float64, aligned to the
sorted filtered test indices; accuracies recompute exactly from the arrays).
`00_seed42_first_run_notes.txt` is the original write-up of the seed-42 run made
before 123 and 2025 finished.
