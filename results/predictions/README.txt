Per-sample predictions from test-2, 2026-08-20.

Six test_probs_<model>.npy of shape (18541, 2) float32, plus test_labels.npy
of shape (18541,) int64. The duplicate-filtered test partition.

These are the raw evidence behind Tables 1, 2 and 2b. Kept so test-8 can be
re-run without re-running test-2: its SEARCH_ROOTS covers /kaggle/input, so
attaching this directory is enough.

Verified on arrival: every model's filtered accuracy sits BELOW its unfiltered
figure in results/models/*.txt (by 0.06-0.96pp), which is the only direction
possible once memorised samples are removed. No model sits more than 2pp above
the pack median, so the leakage guard passes.

  graphcodebert_dfg   87.8593%      graphcodebert_text  88.2692%
  codebert_dfg        87.5196%      codebert_text       87.6814%
  unixcoder_dfg       88.3124%      unixcoder_text      88.3447%

---------------------------------------------------------------------------
test6_{probs,labels}_{balanced,imbalanced}.npy -- from test-6, 2026-08-30.

GraphCodeBERT text-only scored on the same 18,541-sample filtered partition,
in both the balanced 50/50 and the deployment-realistic 90/10 conditions.

Kept for the same reason: test-6 used to discard these, so every question
about the decision threshold cost a full GPU run. Any future sweep is now a
CPU script over these files.
