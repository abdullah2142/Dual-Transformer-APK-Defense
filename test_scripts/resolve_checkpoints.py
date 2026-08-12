"""
Canonical checkpoint resolver.

PASTE THIS into any evaluation script that loads a trained checkpoint, then
replace the blank `weights = ""` fields with a call:

    args.gcb_text_weights = resolve('GCB text-only', 'saved_models/best_model_text_only.bin')

Why this exists
---------------
Every `weights` field in the evaluation scripts was a blank `# TODO`, so no
run's model provenance was recorded anywhere. That is what let the CodeBERT
split mismatch hide for two months (see PAPER.md 10.4). This resolver finds
the checkpoint under /kaggle/input, **prints the path it resolved**, and so
puts provenance into the run log automatically.

Why it matches on directory + filename, not filename alone
----------------------------------------------------------
THREE different checkpoints are named `best_model.bin`:

    saved_models/best_model.bin                 -> GraphCodeBERT + DFG
    saved_models_codebert_text/best_model.bin   -> CodeBERT text-only
    saved_models_codebert_dfg/best_model.bin    -> CodeBERT + DFG

A glob on `**/best_model.bin` would match all three and silently pick one, so
you would score the wrong model and never know. Callers therefore pass the
trailing `<dir>/<file>` pair, and the path component must match exactly:
`saved_models/x.bin` does NOT match `saved_models_unixcoder/x.bin`.

Fail-closed
-----------
Zero matches is an error. TWO OR MORE matches is also an error -- ambiguity
is never resolved by guessing. Pass an explicit path to override.

Kaggle: works with "+ Add Input -> Notebooks", which mounts each training
run's output under its own root, so the three best_model.bin files never
share a directory.
"""

import os
import glob as _glob

SEARCH_ROOTS = ('/kaggle/input', '/kaggle/working')


def resolve(label, *suffixes, override=None, roots=SEARCH_ROOTS, required=True):
    """Locate one checkpoint by its trailing '<dir>/<file>' path.

        resolve('CodeBERT text', 'saved_models_codebert_text/best_model.bin')

    Several suffixes may be given as fallbacks (first one that matches wins).
    Returns the resolved path, or '' when required=False and nothing matched.
    """
    if override:
        if not os.path.exists(override):
            raise FileNotFoundError(f'{label}: explicit path does not exist: {override}')
        print(f'  {label:24s} -> {override}  (explicit)')
        return override

    for suffix in suffixes:
        hits = []
        for root in roots:
            if os.path.isdir(root):
                hits.extend(_glob.glob(os.path.join(root, '**', suffix), recursive=True))
        hits = sorted(set(hits))

        if len(hits) == 1:
            size_mb = os.path.getsize(hits[0]) / 1e6
            print(f'  {label:24s} -> {hits[0]}  ({size_mb:.0f} MB)')
            if size_mb < 100:
                print(f'  {"":24s}    WARNING: {size_mb:.0f} MB is small for a checkpoint '
                      f'(expect ~499 MB). Wrong file?')
            return hits[0]

        if len(hits) > 1:
            raise RuntimeError(
                f'{label}: {len(hits)} files match "{suffix}" -- refusing to guess.\n  '
                + '\n  '.join(hits)
                + '\nAttach only one training run per model, or pass override=<path>.')

    if not required:
        print(f'  {label:24s} -> NOT FOUND (optional)')
        return ''

    raise FileNotFoundError(
        f'{label}: no file matching any of {list(suffixes)} under {list(roots)}.\n'
        f'On Kaggle use "+ Add Input -> Notebooks" and attach the training run '
        f'that produced it. To see what is actually mounted:\n'
        f"    import glob; print(glob.glob('/kaggle/input/**/*.bin', recursive=True))")


# ── the six checkpoints, by the directory each training notebook writes ──────
CHECKPOINTS = {
    'gcb_dfg':        ('GCB + DFG',        'saved_models/best_model.bin'),
    'gcb_text':       ('GCB text-only',    'saved_models/best_model_text_only.bin'),
    'codebert_dfg':   ('CodeBERT + DFG',   'saved_models_codebert_dfg/best_model.bin'),
    'codebert_text':  ('CodeBERT text',    'saved_models_codebert_text/best_model.bin'),
    'unixcoder_dfg':  ('UniXcoder + DFG',  'saved_models_unixcoder_dfg/model_unixcoder_dfg_best.bin'),
    'unixcoder_text': ('UniXcoder text',   'saved_models_unixcoder/best_model_text_only.bin'),
}


def resolve_all(*keys, **overrides):
    """Resolve several at once: resolve_all('gcb_dfg', 'gcb_text') -> dict."""
    print('Resolving checkpoints:')
    out = {}
    for k in keys:
        label, suffix = CHECKPOINTS[k]
        out[k] = resolve(label, suffix, override=overrides.get(k))
    return out
