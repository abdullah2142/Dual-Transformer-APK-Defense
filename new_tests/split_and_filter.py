"""
Canonical split + duplicate-filter block.

PASTE THIS into test-2, test-4, test-6 and test-7, replacing whatever
get_test_indices / get_stratified_indices / get_test_indices_by_source they
currently define. Then call:

    train_idx, val_idx, test_idx, report_sources = get_split_indices(args.train_file)

Kaggle: NO change to the dataset path and NO new upload. The hashes are
computed from the same JSONL the scripts already read.

Two things this fixes at once:

1. SPLIT — `infer_source` deliberately has NO filename fallback. Every entry
   resolves to "unknown", so the split degenerates to a single group. That is
   exactly what the training notebooks did, and matching them is the whole
   point. Adding a fallback here re-creates the 89.9% leak in tests 4/6/7.

2. DUPLICATES — test entries whose `code` is byte-identical to a train/val
   entry are dropped (1,455 of 19,996 -> 18,541). Training is unaffected;
   this only removes memorised samples from the *measurement*.

Verified against dataset_graphcodebert.jsonl on 2026-08-03:
    split  : train=163,967  val=15,997  test=19,996   (matches every notebook)
    filter : -1,455 (7.28%) -> 18,541 clean
    clean test by source: LVDAndro 7,482 | Draper 6,856 | Juliet 1,815 | Devign 2,388

Streams the file instead of holding all 199,960 records in RAM.
"""

import json, math, random, hashlib
from collections import defaultdict


def infer_source(entry):
    """Verbatim from the training notebooks. Do NOT add a filename fallback:
    the notebooks had none, and the graders must match the notebooks."""
    for key in ("source", "dataset", "origin", "project"):
        v = entry.get(key)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return "unknown"


def allocate_counts(total_needed, groups, fraction):
    raw = {g: len(v) * fraction for g, v in groups.items()}
    base = {g: int(math.floor(v)) for g, v in raw.items()}
    rem = total_needed - sum(base.values())
    order = sorted(groups, key=lambda g: (raw[g] - base[g], len(groups[g])), reverse=True)
    for g in order[:rem]:
        base[g] += 1
    return base


def source_for_reporting(filename):
    """Recovers the true source from the filename prefix (LVDAndro_279755_file).

    REPORTING ONLY — never used to build the split. Using this for grouping
    before the split is exactly the bug that put 89.9% of tests 4/6/7's test
    set inside the training data.
    """
    return str(filename).split("_")[0] or "unknown"


def get_split_indices(filepath, test_ratio=0.10, val_ratio=0.08, seed=42,
                      drop_duplicate_test=True, verbose=True):
    """Returns (train_indices, val_indices, test_indices, report_sources).

    Reproduces the training notebooks' partition exactly
    (163,967 / 15,997 / 19,996), then optionally removes test entries that are
    byte-identical to a train/val entry.

    `report_sources` is a per-index list of true source names, for breaking
    results down by source AFTER the split. Callers that don't need it can
    unpack the first three.
    """
    # ── single streaming pass: split key + code hash + reporting source ──────
    srcs, hashes, report_sources = [], [], []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line)
            srcs.append(infer_source(e))
            hashes.append(hashlib.md5(str(e.get("code", "")).encode("utf-8", "ignore")).hexdigest())
            report_sources.append(source_for_reporting(e.get("filename", "")))
            del e
    total = len(srcs)

    # ── stratified_three_way_split, verbatim ────────────────────────────────
    rng = random.Random(seed)
    source_to_indices = defaultdict(list)
    for idx, s in enumerate(srcs):
        source_to_indices[s].append(idx)
    for indices in source_to_indices.values():
        rng.shuffle(indices)

    target_test = int(round(total * test_ratio))
    target_val = int(round(total * val_ratio))

    test_alloc = allocate_counts(target_test, source_to_indices, test_ratio)
    trainval_groups, test_indices = {}, []
    for source, indices in source_to_indices.items():
        take = min(test_alloc[source], len(indices))
        test_indices.extend(indices[:take])
        trainval_groups[source] = indices[take:]

    adjusted_val_ratio = val_ratio / (1.0 - test_ratio)
    val_alloc = allocate_counts(target_val, trainval_groups, adjusted_val_ratio)

    val_indices, train_indices = [], []
    for source, indices in trainval_groups.items():
        take = min(val_alloc[source], len(indices))
        val_indices.extend(indices[:take])
        train_indices.extend(indices[take:])

    train_indices = sorted(train_indices)
    val_indices = sorted(val_indices)
    test_indices = sorted(test_indices)

    assert len(train_indices) == total - target_test - target_val
    assert len(val_indices) == target_val
    assert len(test_indices) == target_test
    assert set(train_indices).isdisjoint(val_indices)
    assert set(train_indices).isdisjoint(test_indices)
    assert set(val_indices).isdisjoint(test_indices)

    if verbose:
        print(f"Split: train={len(train_indices):,} val={len(val_indices):,} "
              f"test={len(test_indices):,}")

    # ── duplicate filter (evaluation only; training data is untouched) ───────
    if drop_duplicate_test:
        seen = {hashes[i] for i in train_indices}
        seen.update(hashes[i] for i in val_indices)
        before = len(test_indices)
        test_indices = [i for i in test_indices if hashes[i] not in seen]
        if verbose:
            dropped = before - len(test_indices)
            print(f"Duplicate filter: dropped {dropped:,} test entries "
                  f"({dropped/before:.2%}) that are byte-identical to a "
                  f"train/val sample -> {len(test_indices):,} clean test entries")

    return train_indices, val_indices, test_indices, report_sources


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else \
        "/kaggle/input/datasets/hasanmahmudabdullah/dfgdataset2/dataset_graphcodebert.jsonl"
    tr, vl, te, rs = get_split_indices(p)
    from collections import Counter
    print(f"\nfinal: train={len(tr):,} val={len(vl):,} test={len(te):,}")
    print("clean test by source:", dict(Counter(rs[i] for i in te)))
