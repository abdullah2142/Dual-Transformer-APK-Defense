Superseded outputs. Kept only so a reader who finds a stale number elsewhere
can trace where it came from. Do not cite anything in here.

test6_imbalanced_results_2026-08-15.txt
test6_precision_recall_bar_2026-08-15.png
---------------------------------------------------------------------------
Superseded by the 2026-08-30 run, for two reasons.

1. It is LABELLED "UniXcoder text-only" but was not a UniXcoder run. Commit
   83a9ed4 had already re-pointed test-6's weights, backbone and code_length
   to GraphCodeBERT on 08-12; only the display strings still said UniXcoder,
   and those were fixed in 462e105. The 08-30 re-run differs from this file
   in labels ONLY -- every metric matches to four decimals across all eight
   shared sweep rows, which is only possible if both used the same checkpoint.

2. Its threshold sweep stops at 0.65, where F1 was still rising. The maximum
   therefore sat outside the swept range, so the file cannot support any claim
   about an F1-optimal threshold. The 08-30 sweep extends to 0.95 and finds
   the real peak at 0.90.

The current file is results/test6_imbalanced_results.txt.
