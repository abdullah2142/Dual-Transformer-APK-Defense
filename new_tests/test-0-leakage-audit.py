"""
Test 0 — Dataset leakage audit.  RUN THIS BEFORE ANY RESULTS ARE WRITTEN UP.

Answers four questions about dataset_graphcodebert.jsonl:
  A. Which keys actually exist?           -> settles whether infer_source() works
  B. Does `filename` encode the source?   -> settles the stratification fix
  C. Are there exact-duplicate code bodies, and do they straddle the split?
  D. Do entries sharing a filename straddle the split?

CPU only, no GPU, no model. Runtime ~1-2 min on the 199,960-entry corpus.
Reproduces the notebooks' split exactly so the numbers describe the real partition.
"""

import os, sys, json, math, random, hashlib
from collections import defaultdict, Counter

TRAIN_FILE = os.environ.get(
    "TRAIN_FILE",
    "/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl",
)
if len(sys.argv) > 1:
    TRAIN_FILE = sys.argv[1]
SEED, TEST_RATIO, VAL_RATIO = 42, 0.10, 0.08

# Streamed load: the `dfg` field dominates the file size and is irrelevant here,
# so keep only what the audit needs (md5 of code, label, filename, key names).
# Peak memory stays ~50 MB instead of several GB.
def infer_source_asis(entry):
    """Verbatim copy of infer_source() as shipped in the training notebooks."""
    for key in ("source", "dataset", "origin", "project"):
        v = entry.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return "unknown"

print(f"Streaming {TRAIN_FILE} ...")
code_md5, labels, filenames, srcs = [], [], [], []
key_counts = Counter()
with open(TRAIN_FILE, "r", encoding="utf-8") as f:
    for n, line in enumerate(f, 1):
        e = json.loads(line)
        key_counts.update(e.keys())
        code_md5.append(hashlib.md5(str(e.get("code", "")).encode("utf-8", "ignore")).hexdigest())
        labels.append(int(e.get("label", 0)) if e.get("label") is not None else 0)
        filenames.append(str(e.get("filename", "")))
        srcs.append(infer_source_asis(e))
        del e
        if n % 25000 == 0:
            print(f"  {n:,} ...")
N = len(code_md5)
print(f"{N:,} entries\n")

# ── A. Key inventory ─────────────────────────────────────────────────────────
print("=" * 70)
print("A. KEY INVENTORY")
print("=" * 70)
for k, c in key_counts.most_common():
    print(f"  {k:<20} present in {c:>7,} / {N:,}  ({c/N:.1%})")

probe = ("source", "dataset", "origin", "project", "corpus")
print(f"\n  Keys infer_source() probes: {probe}")
present = [k for k in probe if key_counts.get(k, 0) > 0]
print(f"  -> present: {present if present else 'NONE — every entry resolves to \"unknown\"'}")
if not present:
    print("  -> CONFIRMED: the notebook split is NOT stratified; it is a plain shuffle.")

# ── B. Does filename encode the source? ──────────────────────────────────────
print("\n" + "=" * 70)
print("B. FILENAME PREFIX -> SOURCE")
print("=" * 70)
has_fn = sum(1 for fn in filenames if fn)
print(f"  entries with a filename: {has_fn:,} / {N:,} ({has_fn/N:.1%})")
prefixes = Counter(fn.split("_")[0] for fn in filenames)
print(f"  distinct first-underscore prefixes: {len(prefixes):,}")
for p, c in prefixes.most_common(12):
    print(f"    {p:<28} {c:>7,}  ({c/N:.1%})")
if len(prefixes) <= 12:
    print("  -> prefix cleanly partitions the corpus; safe to stratify on it.")
else:
    print("  -> many prefixes; use test-4's SOURCES-keyed matching, not raw prefix.")

# ── Rebuild the notebooks' split (degenerate single-group, as shipped) ───────
def allocate_counts(total_needed, groups, fraction):
    raw = {g: len(v) * fraction for g, v in groups.items()}
    base = {g: int(math.floor(v)) for g, v in raw.items()}
    rem = total_needed - sum(base.values())
    order = sorted(groups, key=lambda g: (raw[g] - base[g], len(groups[g])), reverse=True)
    for g in order[:rem]:
        base[g] += 1
    return base

def split(group_keys, test_ratio=TEST_RATIO, val_ratio=VAL_RATIO, seed=SEED):
    rng = random.Random(seed)
    groups = defaultdict(list)
    for i, g in enumerate(group_keys):
        groups[g].append(i)
    for v in groups.values():
        rng.shuffle(v)
    target_test = int(round(len(group_keys) * test_ratio))
    target_val = int(round(len(group_keys) * val_ratio))
    alloc = allocate_counts(target_test, groups, test_ratio)
    test, trainval = [], {}
    for s, idx in groups.items():
        k = min(alloc[s], len(idx))
        test += idx[:k]
        trainval[s] = idx[k:]
    val_alloc = allocate_counts(target_val, trainval, val_ratio / (1.0 - test_ratio))
    val, train = [], []
    for s, idx in trainval.items():
        k = min(val_alloc[s], len(idx))
        val += idx[:k]
        train += idx[k:]
    return sorted(train), sorted(val), sorted(test)

train_idx, val_idx, test_idx = split(srcs)
train_set, test_set = set(train_idx), set(test_idx)
print(f"\n  split rebuilt: train={len(train_idx):,} val={len(val_idx):,} test={len(test_idx):,}")

# ── C. Exact-duplicate code bodies ───────────────────────────────────────────
print("\n" + "=" * 70)
print("C. EXACT-DUPLICATE CODE BODIES  (md5 of the raw string)")
print("=" * 70)
by_hash = defaultdict(list)
for i, h in enumerate(code_md5):
    by_hash[h].append(i)

dup_groups = {h: v for h, v in by_hash.items() if len(v) > 1}
dup_entries = sum(len(v) for v in dup_groups.values())
print(f"  distinct code bodies : {len(by_hash):,} / {N:,}")
print(f"  duplicated groups    : {len(dup_groups):,}")
print(f"  entries in a dup grp : {dup_entries:,}  ({dup_entries/N:.1%})")

leaked = [v for v in dup_groups.values()
          if any(i in train_set for i in v) and any(i in test_set for i in v)]
leaked_test = len({i for v in leaked for i in v} & test_set)
print(f"\n  dup groups straddling train/test : {len(leaked):,}")
print(f"  TEST entries whose code also appears in TRAIN : "
      f"{leaked_test:,} / {len(test_idx):,}  ({leaked_test/len(test_idx):.2%})")

# label-flipped duplicates: identical code, contradictory labels
conflict = sum(1 for v in by_hash.values()
               if len({labels[i] for i in v}) > 1)
print(f"  identical code with CONTRADICTORY labels : {conflict:,} groups")

# ── D. Filename-level straddling ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("D. FILENAME GROUPS STRADDLING TRAIN/TEST")
print("=" * 70)
by_fn = defaultdict(list)
for i, fn in enumerate(filenames):
    if fn:
        by_fn[fn].append(i)
multi = {k: v for k, v in by_fn.items() if len(v) > 1}
print(f"  distinct filenames          : {len(by_fn):,}")
print(f"  filenames with >1 entry     : {len(multi):,}")
if multi:
    sz = sorted((len(v) for v in multi.values()), reverse=True)
    print(f"  largest group               : {sz[0]:,} entries")
    print(f"  median group (of multi)     : {sz[len(sz)//2]:,}")

straddle = [v for v in multi.values()
            if any(i in train_set for i in v) and any(i in test_set for i in v)]
straddle_test = len({i for v in straddle for i in v} & test_set)
print(f"\n  filename groups straddling  : {len(straddle):,}")
print(f"  TEST entries sharing a filename with a TRAIN entry : "
      f"{straddle_test:,} / {len(test_idx):,}  ({straddle_test/len(test_idx):.2%})")

# ── Verdict ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)
exact = leaked_test / len(test_idx)
group = straddle_test / len(test_idx)
if exact >= 0.01:
    print(f"  [!] {exact:.2%} of the test set is verbatim-duplicated in train.")
    print("      Dedupe by code md5 BEFORE splitting, then retrain. Reported")
    print("      accuracy currently includes a memorisation component.")
else:
    print(f"  [ok] Exact duplication across the split is negligible ({exact:.2%}).")
if group >= 0.20:
    print(f"  [!] {group:.2%} of test entries share a filename with a train entry.")
    print("      Switch to GROUPED splitting (whole filenames to one side) and")
    print("      retrain; per-function random splitting leaks intra-file context.")
else:
    print(f"  [ok] Filename straddling is limited ({group:.2%}).")
if conflict:
    print(f"  [!] {conflict:,} code bodies carry contradictory labels — an accuracy ceiling.")

with open("results/test0_leakage_audit.txt", "w", encoding="utf-8") as fh:
    fh.write("Test 0 - Dataset Leakage Audit\n")
    fh.write("=" * 60 + "\n")
    fh.write(f"entries                          : {N:,}\n")
    fh.write(f"keys present of infer_source set : {present}\n")
    fh.write(f"distinct code bodies             : {len(by_hash):,}\n")
    fh.write(f"entries in duplicate groups      : {dup_entries:,} ({dup_entries/N:.2%})\n")
    fh.write(f"test entries duped into train    : {leaked_test:,} ({exact:.2%})\n")
    fh.write(f"contradictory-label dup groups   : {conflict:,}\n")
    fh.write(f"test entries sharing a filename  : {straddle_test:,} ({group:.2%})\n")
print("\nSaved -> results/test0_leakage_audit.txt")
