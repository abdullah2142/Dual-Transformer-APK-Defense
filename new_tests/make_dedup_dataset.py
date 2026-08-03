"""
Step 0.1 — Build the deduplicated corpus.

Run this ONCE. Every training notebook and evaluation script then points at the
output file. Do not dedupe inside individual scripts: fifteen files each
re-deriving indices is exactly how the original split mismatch happened.

Policy (see SPLIT_MISMATCH.md / after_inspection.md):
  * duplicate = byte-identical `code` string (md5), matching the Test 0 audit
  * groups whose copies carry CONTRADICTORY labels are dropped entirely
    (the label is provably unreliable; 51 groups / 102 entries)
  * every other duplicate group keeps its FIRST occurrence, preserving
    original file order
  * NO rebalancing — the surviving class ratio is reported, not engineered

Expected output: 189,938 entries, 50.1% safe / 49.9% vulnerable.

Usage:
    python3 make_dedup_dataset.py <in.jsonl> [out.jsonl]
"""

import sys, json, hashlib
from collections import defaultdict, Counter

IN = sys.argv[1] if len(sys.argv) > 1 else \
    "/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else IN.replace(".jsonl", "_dedup.jsonl")
REPORT = "results/test0_dedup_report.txt"


def code_key(entry):
    return hashlib.md5(str(entry.get("code", "")).encode("utf-8", "ignore")).hexdigest()


def source_of(entry):
    """Source lives in the filename prefix (LVDAndro_279755_file). The `source`
    key does not exist in this corpus — see Test 0 audit, section A."""
    return str(entry.get("filename", "")).split("_")[0] or "unknown"


# ── Pass 1: group line offsets by code hash ──────────────────────────────────
print(f"Pass 1/2  scanning {IN}")
groups = defaultdict(list)          # md5 -> [line_no, ...]
line_label, line_src = {}, {}
n_in = 0
with open(IN, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        e = json.loads(line)
        groups[code_key(e)].append(i)
        line_label[i] = int(e.get("label", 0)) if e.get("label") is not None else 0
        line_src[i] = source_of(e)
        n_in += 1
        del e
        if n_in % 25000 == 0:
            print(f"  {n_in:,} ...")
print(f"  {n_in:,} entries, {len(groups):,} distinct code bodies")

# ── Decide which lines survive ───────────────────────────────────────────────
conflicting = {h for h, v in groups.items() if len({line_label[i] for i in v}) > 1}
keep = set()
for h, v in groups.items():
    if h in conflicting:
        continue
    keep.add(v[0])                  # first occurrence wins; file order preserved

n_conflict_entries = sum(len(groups[h]) for h in conflicting)
print(f"\n  conflicting-label groups dropped : {len(conflicting):,} "
      f"({n_conflict_entries:,} entries)")
print(f"  duplicate copies dropped         : "
      f"{n_in - len(keep) - n_conflict_entries:,}")
print(f"  surviving entries                : {len(keep):,}")

# ── Pass 2: stream the survivors out ─────────────────────────────────────────
print(f"\nPass 2/2  writing {OUT}")
n_out = 0
with open(IN, "r", encoding="utf-8") as fin, open(OUT, "w", encoding="utf-8") as fout:
    for i, line in enumerate(fin):
        if i in keep:
            fout.write(line if line.endswith("\n") else line + "\n")
            n_out += 1
assert n_out == len(keep), f"wrote {n_out}, expected {len(keep)}"
print(f"  wrote {n_out:,} entries")

# ── Composition report ───────────────────────────────────────────────────────
SRC = ["LVDAndro", "Draper", "Juliet", "Devign"]
before_src = Counter(line_src.values())
after_src = Counter(line_src[i] for i in keep)
before_lab = Counter(line_label.values())
after_lab = Counter(line_label[i] for i in keep)

lines = []
lines.append("Step 0.1 - Deduplicated Corpus")
lines.append("=" * 64)
lines.append(f"input  : {IN}")
lines.append(f"output : {OUT}")
lines.append("rule   : byte-identical code (md5); conflicting-label groups dropped;")
lines.append("         first occurrence kept; no rebalancing")
lines.append("")
lines.append(f"{'source':<12}{'before':>10}{'after':>10}{'removed':>10}"
             f"{'safe':>9}{'vuln':>9}")
lines.append("-" * 64)
for s in SRC:
    a = sum(1 for i in keep if line_src[i] == s)
    lines.append(f"{s:<12}{before_src[s]:>10,}{a:>10,}{before_src[s]-a:>10,}"
                 f"{sum(1 for i in keep if line_src[i]==s and line_label[i]==0):>9,}"
                 f"{sum(1 for i in keep if line_src[i]==s and line_label[i]==1):>9,}")
lines.append("-" * 64)
lines.append(f"{'TOTAL':<12}{n_in:>10,}{len(keep):>10,}{n_in-len(keep):>10,}"
             f"{after_lab[0]:>9,}{after_lab[1]:>9,}")
lines.append("")
lines.append(f"class ratio before : {before_lab[0]/n_in:.1%} safe / {before_lab[1]/n_in:.1%} vuln")
lines.append(f"class ratio after  : {after_lab[0]/len(keep):.1%} safe / {after_lab[1]/len(keep):.1%} vuln")
lines.append("")
lines.append("Report these figures in the paper's dataset section verbatim.")
lines.append("Note: Juliet's internal balance shifts (its safe class was the most")
lines.append("heavily duplicated); report Juliet separately from headline metrics.")

report = "\n".join(lines)
print("\n" + report)
try:
    with open(REPORT, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    print(f"\nSaved -> {REPORT}")
except OSError:
    print(f"\n(could not write {REPORT}; report printed above)")

print("\nNEXT: point every train_file at the deduped path, then re-run "
      "test-0-leakage-audit.py against it to confirm leakage ~0%.")
