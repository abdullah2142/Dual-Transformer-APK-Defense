# Superseded test scripts

Kept for provenance. **Do not run anything in here** — each produced a number the
project has since withdrawn, and re-running one costs a full GPU session to
reproduce a result we know is wrong.

## `test_3_multiseed_warmstart/`

Previously `test_scripts/test_3_multiseed_broken_down/`. Three notebooks that
produced Table 3's ±0.10% training-stability figure.

**Why it was withdrawn** (PAPER.md §3.3a): they set

```
pretrained_encoder = ".../graphcodebert-train-text-only/saved_models/best_model_text_only.bin"
```

— our own fine-tuned checkpoint, trained at seed 42 on this exact training set.
Each "seed" deep-copies that converged encoder, re-initialises only the
classifier head, and continues training. All three runs start inside the same
basin having already seen every training sample, so ±0.10% measures head-init
and data-order jitter rather than fine-tuning seed variance — and it is biased
low. Table 3 is the yardstick for judging whether Table 2's 0.410pp delta is
noise, so the bias runs in the direction that flatters the paper.

They also ran at a 5-epoch ceiling while Tables 1–2 use 10 / 2.

**Replaced by** `test_scripts/test_3_multiseed/test-3-seed{42,123,2025}.ipynb`,
which cold-start from `microsoft/graphcodebert-base`.

The committed outputs in `results/test3_seed*_results.txt` came from these
notebooks and are stale on a third count: they predate the duplicate filter.
