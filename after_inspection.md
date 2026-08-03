Both notebooks now use Split A. Now let me verify the details — especially the `8/90` double-adjustment gotcha I flagged.

Both fixed the `8/90` gotcha and added the `test_indices.npy` guard. Now the critical question: does the function produce the *same* partition as GraphCodeBERT/UniXcoder?

`stratified_three_way_split` differs. Let me see exactly how — cosmetic or semantic.

The split logic itself is byte-identical — only assert messages and print statements changed. Now `load_entries`, since entry order determines the indices:

`load_entries` is identical too — same file, same order, so the partition will match. Let me now check the two `.py` scripts, and one thing that caught my eye: the DFG notebook builds a `SimpleDataset`.

`SimpleDataset` in the DFG notebook does build `p_ids`/`attn_mask` — confusingly named, but genuinely DFG-aware. No problem there. Last check:

Yes — the core fix is correct. I verified it structurally rather than by eye:

## The split fix is right

| Check | Result |
|---|---|
| `stratified_three_way_split` logic vs GraphCodeBERT reference | **identical** (only assert *messages* and prints differ) |
| `infer_source`, `allocate_counts` | byte-identical |
| `load_entries` | identical body, same file, same order |
| `sklearn train_test_split` | **gone** from both notebooks |
| `test_ratio=0.10`, `val_ratio=0.08` | the `8/90` double-adjustment trap **avoided** |

Same function, same RNG, same seed, same entry order ⇒ the CodeBERT partition will now be identical to GraphCodeBERT's and UniXcoder's. That's the bug closed.

Two bonus checks: hyperparameters are untouched (384 / 16 / 2e-5 / 5 epochs / patience 2), and I confirmed `SimpleDataset` in `codebert-final-dfg.ipynb` really does build `p_ids`/`attn_mask` — the name is misleading, but CodeBERT+DFG is genuinely DFG-aware.

`test-6` also picked up two improvements I'd flagged: `OPT_THRESHOLD` 0.5 → 0.60, and the threshold sweep is now written to the results file — which is what PAPER_DEFENSE §7 needs to justify 0.60.

## Five things still to tighten

**1. The split guard is fail-open** — this is the one I'd actually fix before running.

```python
guard_path = '/kaggle/input/.../test_indices.npy'
if os.path.exists(guard_path):        # ← file missing = guard silently skipped
```

If you forget to upload the file, the guard prints nothing and passes. The exact failure it exists to catch would slip through again. Make it fail-closed:

```python
assert os.path.exists(guard_path), f'Split guard file missing: {guard_path}'
saved_indices = np.load(guard_path)
assert np.array_equal(test_indices, saved_indices), 'Split mismatch!'
print('Split guard check passed.')
```

**2. Guard path mismatch.** The notebooks save to `saved_models_codebert/test_indices.npy` (Kaggle *output*), but `test-2` reads from `/kaggle/input/datasets/.../test_indices.npy` (the *dataset* input). That needs a manual copy between runs — and combined with #1, forgetting it means silent skip.

**3. The guard can only check CodeBERT against itself.** The GraphCodeBERT and UniXcoder notebooks save split indices as **JSON** (`split_indices_path`), not `.npy`. So there's no npy from them to compare against. Given the split code is now provably identical across all six, this is belt-and-braces — but if you want a real cross-model check, have `test-2` read the JSON format too.

**4. Checkpoint paths are still blank.** All eight `weights` fields in both scripts remain `"" # TODO`. This is what let the mismatch hide for two months. Fill them in and commit after the runs.

**5. `test-8` writes the wrong filename** — `out_path = '/kaggle/working/test9_significance_results.txt'`, but the repo file is `test8_significance_results.txt`. Cosmetic, but it's the same naming confusion that already caused one rename in your history. (`test-8` is otherwise unchanged, which is correct — it just consumes the `.npy` files.)

## One consequence to plan for

Moving `test-6` to threshold 0.60 changes Table 5's headline numbers. README currently reports those rows explicitly labeled "threshold 0.5" (recall 94.14%, F1 0.7782, FPR 5.31%). Those will all shift, and the table caption needs updating with them.

Want me to patch items 1, 2, and 5 directly in `new_tests/`? They're small and mechanical — the guard is the only one with real consequences.