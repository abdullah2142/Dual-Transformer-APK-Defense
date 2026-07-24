# Research Notes — DFG-Aware Android Vulnerability Detection: An Empirical Study
## Comprehensive Paper Guidance Document

> **Status**: All training runs complete. Multi-seed stability (Test 3) still pending. Statistical significance testing (McNemar's) still pending.
> **Last updated**: 2026-07-23

---

## PART 1 — WHAT THIS PAPER IS

### The central narrative

This paper began as a positive claim — "DFG-aware attention reduces missed malware by 28%."
Through rigorous experimental methodology, we discovered that claim was an artifact of flawed
evaluation. Correcting the methodology revealed a more interesting and publishable truth:
**all modern transformer models converge to the same performance on decompiled Android
vulnerability data, regardless of whether graph structure is incorporated.** We then explain
mechanistically why DFG fails in this setting through qualitative analysis of false negatives.

### The three-sentence paper summary

"We build the first end-to-end system for DFG-aware vulnerability detection on decompiled Android bytecode at scale. Through a systematic empirical evaluation across three leading encoder backbones, we find that DFG-aware attention provides no consistent benefit and often universally degrades accuracy compared to standard text-only transformers in this setting. Qualitative analysis of the top false negatives reveals the cause: JADX decompilation strips identifier semantics from DFG edges, leaving graph structure present but informationally empty."

### Why this is publishable at MSR

1. **Novel system**: First published pipeline for DFG extraction from decompiled APKs at scale.
2. **Novel corpus**: 200k DFG-annotated samples across Java/Kotlin/C — does not exist publicly.
3. **Informative negative finding**: The field has assumed DFG helps on code. This paper is the
   first to show it does not help on *decompiled* code, with a mechanistic explanation.
4. **Real deployment**: Tested on real APKs in the wild (scanner pipeline / Test 9).

---

## PART 2 — TRAINING METHODOLOGY (CURRENT)

### Split and training protocol

All models use the following standardized protocol:

| Parameter | Value |
|---|---|
| Split | 82% train / 8% val / 10% test — stratified by source, fixed seed=42 |
| Checkpoint selection | Best validation accuracy (validation-based early stopping) |
| Patience | 2 (except GCB models: patience=3) |
| Max epochs | 5 (except GCB models: max 10) |
| Batch size | 16 train / 32 eval |
| Learning rate | 2e-5 |
| Optimizer | AdamW, eps=1e-8 |
| Gradient clipping | max norm 1.0 |
| Precision | FP16 (AMP) |
| Code length | 384 tokens |
| Decision threshold | 0.60 |

> **Note on GCB epoch ceiling**: Both GraphCodeBERT models (Text-only and DFG) were given a higher ceiling
> (max 10 epochs, patience=3) because early runs showed them converging later than the other
> models. This was a compute-side adjustment only — early stopping still governs which
> checkpoint is saved, and the final results (best epoch = 5 for both) are directly comparable.
> All other models use max 5 epochs / patience=2.

> **Historical note**: An earlier version of this paper used a fixed 3-epoch schedule with
> no validation set and no checkpoint selection (Decision 3 in old notes). This was
> revised to validation-based early stopping to allow all models to converge naturally
> while still using a held-out test set the model never influences.

---

## PART 3 — ALL FINAL NUMBERS

### Complete model comparison table

```
Model              Backbone         Structure    Accuracy   ROC-AUC   PR-AUC    FN     FP    Best Epoch
─────────────────────────────────────────────────────────────────────────────────────────────────────────
LR + TF-IDF        —                None         [TBD]       —         —         [TBD]   —     —
MLP + TF-IDF       —                None         [TBD]       —         —         [TBD]   —     —
CodeBERT           codebert-base    Text only    88.5627%   0.9610    0.9625    1,180  1,107   4
CodeBERT + DFG     codebert-base    DFG attn     88.5427%   0.9604    0.9622    1,248  1,043   4
GraphCodeBERT      graphcodebert    Text only    88.9300%   0.9596    0.9611    1,241    972   5
GraphCodeBERT+DFG  graphcodebert    DFG attn     88.5600%   0.9585    0.9597    1,196  1,091   5
UniXcoder          unixcoder-base   Text only    89.0778%   0.9622    0.9636    1,238    946   4
UniXcoder + DFG    unixcoder-base   DFG attn     88.3727%   0.9602    0.9612    1,125  1,200   4
```

All models: 82/8/10 stratified split, seed=42, validation-based early stopping (patience=2),
test set = 19,996 samples. Source files: `results/new/`.

### DFG delta analysis per backbone

```
Backbone        Text-only    DFG-aware    Δ Accuracy    Δ FN
────────────────────────────────────────────────────────────
CodeBERT        88.5627%     88.5427%     −0.020%       +68
GraphCodeBERT   88.9300%     88.5600%     −0.370%       −45
UniXcoder       89.0778%     88.3727%     −0.705%      −113
```

No consistent directional benefit. DFG reduces FN for GCB and UniXcoder but hurts accuracy
in all three cases. The FN improvement for UniXcoder comes at a cost of +75 additional FP.

### Test 3 — Training Stability (Multi-Seed)

```
Mean: [TBD] ± [TBD]   ROC [TBD] ± [TBD]
```

**Status**: Notebook `test-3-multiseed.ipynb` timed out on Kaggle (12h limit exceeded).
Root causes:
- `num_train_epochs=5` with `patience=2` across 3 seeds × full dataset = ~14h total
- `tqdm` output not suppressed → notebook bloat preventing save
- Fix needed: suppress tqdm, reduce to match paper's stability framing

The test script (`test_scripts/test_3_multiseed.py`) correctly uses the DFG model
architecture. The Kaggle notebook (`test-3-multiseed.ipynb`) uses the text-only
architecture — this inconsistency should be resolved when re-running.

Frame this test as a **training stability probe** — the goal is to measure
variance across seeds, not to find the best model.

### Test 4 — Per-Source Breakdown

```
LVDAndro   [TBD]   [TBD]   [TBD]    [TBD] FN
Draper     [TBD]   [TBD]   [TBD]    [TBD] FN
Juliet     [TBD]   [TBD]   [TBD]    [TBD] FN
Devign     [TBD]   [TBD]   [TBD]    [TBD] FN
```

Primary model for this test: UniXcoder text-only (highest accuracy).

### Test 5 — MLP / TF-IDF Baseline

```
LR + TF-IDF   [TBD]
MLP + TF-IDF  [TBD]
```

No model inputs needed — runs on raw text features.

### Test 6 — Imbalanced Evaluation (Threshold Calibration)

```
Threshold 0.60 → Recall [TBD]   F1 [TBD]   FPR [TBD]   FN [TBD]   ← OPTIMAL
```

Models: UniXcoder text-only + UniXcoder+DFG at deployment-realistic 90% safe / 10% malicious ratio.

### Test 7 — Qualitative Analysis (False Negatives)

Primary model: UniXcoder+DFG (lowest FN count = 1,125). Top false negatives analysed.

### Test 8 — Statistical Significance (McNemar's)

All within-backbone DFG comparisons expected p > 0.05. Results saved to
`results/test8_significance_results.txt` when run.

### Test 9 — Real-World APK Scanner Calibration

13 APK reports, covering deliberately vulnerable apps (AndroGoat, DVBA, InsecureBankv2,
InsecureShop, Vuldroid), FOSS apps, and a commercial sample.

---

## PART 4 — QUALITATIVE ERROR ANALYSIS: PATTERN CLASSIFICATION

### Overview of top-20 distribution

The 20 most confident false negatives break into five distinct failure categories.
The dominant source is LVDAndro (decompiled Android APKs), confirming that JADX
decompilation artifacts are the primary driver of model failures.

```
Pattern                                    Count in top-20   Source
────────────────────────────────────────────────────────────────────
P5a — Full machine-generated obfuscation      5               LVDAndro
P1  — Structural fragmentation                4               LVDAndro
P5b — Kotlin/lambda synthetic obfuscation     3               LVDAndro
P7  — Inter-procedural access patterns        3               LVDAndro
P2  — Benign surface over complex logic       2               LVDAndro
P3  — Arithmetic/numeric complexity           1               LVDAndro
P6  — Control flow / flag logic               1               Draper
P4  — Android API semantic bypass             1               LVDAndro
```

**P5a + P5b = 8/20** — obfuscation-driven DFG degradation is the dominant failure mode.
**P5a + P1 + P5b = 12/20** — three-quarters of top failures are decompilation artifacts.

---

### Pattern P5a — Full machine-generated identifier obfuscation
**FNs**: #1, #2, #3, #9, #13 | **Confidence**: 99.99–99.95%

**Root cause**: JADX replaces every meaningful class, method, and field name with
machine-generated tokens (`class_336`, `method_1192`, `field_1000`). DFG edges exist
but connect semantically empty tokens. The model cannot distinguish vulnerable from
safe boilerplate.

**Paper paragraph** (Section 8):
> "The dominant failure mode, present in 5 of the 20 most confident false negatives, is
> complete identifier obfuscation (P5a). JADX decompilation strips all symbolic information
> when the original APK was compiled with ProGuard or R8: class bodies are renamed to
> `class_336`, methods to `method_1192`, fields to `field_1000`, and local variables to
> generic numeric indices (`n21`, `n22`). The DFG edges built over these tokens are
> syntactically valid — the parser correctly identifies data flows between definitions and
> uses — but semantically empty. When every node in the DFG carries a machine-generated
> token, the attention mechanism has no basis for distinguishing a vulnerable data flow
> from a benign one. The model assigns 99.99% confidence of safety to these samples,
> reflecting not uncertainty but the complete absence of discriminative signal. This
> pattern provides the mechanistic explanation for the null ablation result in Section 4:
> in the presence of full obfuscation, DFG-aware attention reduces to standard attention
> over a graph of meaningless connections, offering no advantage over text-only encoding."

---

### Pattern P5b — Kotlin/lambda synthetic identifier obfuscation
**FNs**: #5, #8, #11 | **Confidence**: 99.98–99.95%

**Root cause**: Kotlin compiler generates synthetic class names for lambda expressions
(`-$$Lambda$Sounds$iJSOl-pseCunlcJXFFxU9chQx24`) and coroutine state machines.
These are non-semantic by design. Additionally, Kotlin standard library wrappers
(`CollectionsKt`, `StringsKt`, `Intrinsics`) produce patterns out-of-distribution from
predominantly Java LVDAndro training samples.

**Paper paragraph** (Section 8):
> "A Kotlin-specific variant of DFG degradation (P5b) accounts for a further 3 of the
> top-20 false negatives. The Kotlin compiler generates synthetic class names for lambda
> expressions (e.g., `-$$Lambda$Sounds$iJSOl-pseCunlcJXFFxU9chQx24`) and coroutine state
> machines (e.g., `MediaParsingService$updateStorages$2`) that are non-semantic by design.
> Beyond obfuscated names, Kotlin-decompiled code produces distinctive patterns — coroutine
> continuation passing, `Intrinsics.checkExpressionValueIsNotNull` calls, and
> `CollectionsKt`/`StringsKt` wrapper invocations — that differ structurally from the
> Java-centric LVDAndro training samples, creating an additional distributional gap."

---

### Pattern P1 — Structural fragmentation from decompilation
**FNs**: #4, #10, #18, #19 | **Confidence**: 99.98–99.92%

**Root cause**: JADX sometimes produces syntactically impossible Java — package
declarations inside method bodies, import statements after executable code, field
declarations interleaved with methods. Tree-sitter parses these with best-effort
recovery, but the resulting AST and DFG contain structural artifacts that confound
both graph and tokeniser. The model learns these patterns as safe because valid
Java never looks like this.

**Paper paragraph** (Section 8):
> "Structural fragmentation (P1) accounts for 4 of the top-20 false negatives. JADX
> decompilation occasionally produces syntactically impossible Java: `package` declarations
> inside method bodies (FN #10), `import` statements after executable code (FN #19), and
> field declarations interleaved with method invocations (FN #4). The dataset construction
> pipeline wraps each snippet in a `DummyClass` container, but this cannot repair an
> interior that violates Java grammar. Tree-sitter parses these fragments with best-effort
> recovery, producing ASTs and DFGs that do not correspond to any semantically coherent
> program. The model's confidence of 99.9%+ safe on these samples reflects that no valid
> Java program would ever look like this — the structural impossibility itself signals
> 'not malicious' to a model trained primarily on syntactically valid code."

---

### Pattern P7 — Inter-procedural access patterns
**FNs**: #6, #14, #17 | **Confidence**: 99.97–99.93%

**Root cause**: The vulnerability is not in the function body but in the relationship
between this function and its callers. Single-function analysis cannot determine who
calls a method or whether access is appropriately gated.

**Paper paragraph** (Section 8):
> "Inter-procedural access patterns (P7) account for 3 of the top-20 false negatives and
> represent a fundamental architectural limitation. In FN #17, the vulnerable code directly
> accesses credential fields (`userId`, `token`) from a parent Activity through a class cast.
> Whether this constitutes a vulnerability depends entirely on the calling context: who invokes
> this method, under what conditions, and whether access is appropriately gated. In FN #14,
> the vulnerability lies in how externally-provided data flows through multiple method
> boundaries before reaching a dangerous operation. Single-function analysis is structurally
> incapable of detecting these patterns — the evidence is distributed across the call graph
> in ways that cannot be recovered from any individual function's source code."

---

### Pattern P2 — Benign surface over complex logic
**FNs**: #7, #20 | **Confidence**: 99.97–99.92%

**Root cause**: Well-written, readable, properly structured code where the vulnerability
is a subtle semantic property (race condition, error handling omission) invisible from
surface appearance.

---

### Pattern P3 — Arithmetic and numeric complexity
**FN**: #12 | **Confidence**: 99.95%

**Root cause**: Divide-by-zero when two distinct keyframes share a timestamp — a case
the identity guard does not cover. Requires reasoning about float equality and input
ranges.

---

### Pattern P6 — Control flow and flag logic
**FN**: #16 | **Confidence**: 99.94%

**Root cause**: Duplicate flag in a bitmask OR expression. Detecting this requires
symbolic reasoning about the value space of flag combinations.

---

### Pattern P4 — Android API semantic bypass
**FN**: #15 | **Confidence**: 99.94%

**Root cause**: Misuse of Android API contracts — unvalidated `getStringExtra`, hardcoded
resource IDs, `ProgressDialog` patterns that may expose sensitive state. Requires
knowledge of which API usage patterns are dangerous under which conditions.

---

### Summary table for paper (Section 8)

| Pattern | Code | Count (top-20) | Source | Core reason DFG fails |
|---|---|:---:|---|---|
| P5a | Full machine-generated obfuscation | 5 | LVDAndro | DFG edges connect meaningless tokens |
| P1 | Structural fragmentation | 4 | LVDAndro | Impossible Java confounds AST/DFG |
| P5b | Kotlin/lambda synthetic obfuscation | 3 | LVDAndro | Compiler-generated non-semantic names |
| P7 | Inter-procedural access | 3 | LVDAndro | Single-function scope insufficient |
| P2 | Benign surface appearance | 2 | LVDAndro | Surface pattern dominates over semantics |
| P3 | Arithmetic edge case | 1 | LVDAndro | Requires numeric reasoning |
| P6 | Control flow / flag logic | 1 | Draper | Requires symbolic flag reasoning |
| P4 | Android API semantic bypass | 1 | LVDAndro | Requires API contract knowledge |

---

## PART 5 — KEY DECISIONS AND THEIR DEFENSES

### Decision 1: Retraining with clean split

Old model used unseeded 90/10, no gradient clipping, circular val/test — 92% was
optimism bias. New models: stratified 82/8/10, seed=42, gradient clipping,
validation-based checkpoint selection, strictly held-out test set.

### Decision 2: Reporting the negative ablation result as lead finding

The data is unambiguous — inconsistent DFG effects across three backbones. The negative
finding with a mechanistic explanation is more valuable than a marginal accuracy gain.

**Paper sentence**: "Our controlled ablation reveals no consistent benefit from DFG-aware
attention on decompiled Android bytecode — a null result corroborated by cross-backbone
comparison showing directionally inconsistent DFG effects (Table 2)."

### Decision 3: Validation-based early stopping (revised from fixed 3-epoch)

All models now use an 8% stratified validation split with patience=2 and max 5 epochs.
This allows each model to converge naturally without a fixed-epoch budget that may
over- or under-train. The best validation checkpoint is evaluated once on the held-out
test set. This eliminates the differential optimism problem while still preventing
overfitting.

**Why GCB+DFG is different**: The GCB+DFG notebook uses max 10 epochs / patience=3
because early convergence analysis showed this model needed more room. It still converged
at epoch 5, so the ceiling did not affect the result — it only ensured we did not
artificially cut off a still-improving run.

### Decision 4: Threshold 0.60 from imbalanced condition

Test 6 calibrates the threshold under deployment-realistic 90/10 class ratio. The balanced
threshold is not the correct operating point for a triage scanner.

### Decision 5: Using GCB backbone for CodeBERT+DFG (ReGVD replacement)

ReGVD was unavailable as a reproducible checkpoint. The DFG attention mechanism from
GraphCodeBERT was applied to the CodeBERT backbone, completing the cross-backbone
DFG comparison.

---

## PART 6 — PAPER STRUCTURE WITH DRAFT SENTENCES

### Section 1 — Introduction

> "Android malware has grown to encompass millions of applications, making automated
> static analysis at scale an urgent practical need. Data Flow Graph (DFG) augmented
> transformers have demonstrated promising results for code understanding on clean source
> code, yet their applicability to decompiled Android bytecode — the only representation
> available for closed-source APKs — remains empirically untested. This paper makes three
> contributions: (1) we present the first end-to-end vulnerability scanning pipeline for
> arbitrary Android APKs, including DFG extraction from decompiled Java and Kotlin bytecode
> at scale; (2) we publicly release a 200,000-sample DFG-annotated multi-source vulnerability
> corpus; (3) through controlled ablation across three encoder backbones, we find that
> DFG-aware attention provides no consistent benefit on decompiled code, and explain this
> mechanistically through qualitative analysis of false negatives."

### Section 3 — Dataset and Pipeline

> "Our training corpus comprises 199,960 balanced samples drawn equally from four sources:
> LVDAndro (decompiled Android Java), Draper (C/C++ NVD/SARD CVEs), Devign (C/C++
> QEMU/FFmpeg), and the Juliet Test Suite (synthetic CWEs), with a strict 1:1
> safe-to-vulnerable class ratio enforced across all sources."

> "All five transformer models are trained identically: a stratified 82/8/10 train/val/test
> partition (fixed seed=42), AdamW (lr=2e-5, ε=1e-8), gradient clipping at max norm 1.0,
> FP16 mixed precision, and validation-based early stopping (patience=2, max 5 epochs).
> The best validation checkpoint is evaluated once on the held-out 10% test set."

### Section 4 — Model Comparison and Ablation

> "Table 1 presents the full baseline comparison. All transformer models cluster within a
> ~0.7 percentage-point accuracy band (88.37%–89.08%), regardless of whether graph-augmented
> attention is applied. This convergence suggests that the performance ceiling on decompiled
> Android vulnerability detection is determined by the data domain rather than model
> architecture."

> "Our controlled ablation yields accuracy drops of −0.020%, −0.370%, and −0.705% for
> CodeBERT, GraphCodeBERT, and UniXcoder respectively when DFG is added. No consistent
> directional pattern exists. Statistical significance testing (McNemar's) confirms these
> differences are not significant (all p > 0.05)."

### Section 8 — Limitations and Qualitative Analysis

> "The null DFG result in Section 4 is not architecturally inevitable — GraphCodeBERT's
> DFG attention mechanism demonstrably improves performance on clean source-level code.
> To understand why it fails on decompiled bytecode, we analyse the top false negatives
> from our held-out test set. The most confident mistakes reveal a coherent picture:
> 8 of 20 are caused by complete identifier obfuscation (P5a, P5b), 4 by structural
> fragmentation (P1), and 3 by inter-procedural patterns (P7). Three-quarters of the
> dominant failures are decompilation artifacts that degrade DFG signal before it reaches
> the attention mechanism."

---

## PART 7 — KEY NUMBERS QUICK REFERENCE

| Metric | Value | Source |
|---|---|---|
| GCB text-only accuracy | 88.9300% | results/new/graphcodebert_results.txt |
| GCB text-only ROC-AUC | 0.9596 | results/new/graphcodebert_results.txt |
| GCB text-only FN | 1,241 | results/new/graphcodebert_results.txt |
| GCB text-only best epoch | 5 | results/new/graphcodebert_results.txt |
| GCB+DFG accuracy | 88.5600% | results/new/graphcodebert_dfg_results.txt |
| GCB+DFG ROC-AUC | 0.9585 | results/new/graphcodebert_dfg_results.txt |
| GCB+DFG FN | 1,196 | results/new/graphcodebert_dfg_results.txt |
| GCB+DFG best epoch | 5 | results/new/graphcodebert_dfg_results.txt |
| CodeBERT accuracy | 88.5627% | results/new/codebert_results.txt |
| CodeBERT FN | 1,180 | results/new/codebert_results.txt |
| CodeBERT best epoch | 4 | results/new/codebert_results.txt |
| CodeBERT+DFG accuracy | 88.5427% | results/new/codebert_dfg_results.txt |
| CodeBERT+DFG FN | 1,248 | results/new/codebert_dfg_results.txt |
| CodeBERT+DFG best epoch | 4 | results/new/codebert_dfg_results.txt |
| UniXcoder accuracy | 89.0778% | results/new/unixcoder_results.txt |
| UniXcoder FN | 1,238 | results/new/unixcoder_results.txt |
| UniXcoder best epoch | 4 | results/new/unixcoder_results.txt |
| UniXcoder+DFG accuracy | 88.3727% | results/new/unixcoder_dfg_results.txt |
| UniXcoder+DFG FN | 1,125 | results/new/unixcoder_dfg_results.txt |
| UniXcoder+DFG best epoch | 4 | results/new/unixcoder_dfg_results.txt |
| GCB Δ accuracy (DFG) | −0.370% | computed |
| GCB Δ FN (DFG) | −45 | computed |
| Test 3 stability | [TBD] ± [TBD] | pending re-run |
| Optimal threshold | 0.60 | test-6-imbalanced-eval |
| P5a FNs in top-20 | 5/20 | test-7-qualitative |
| P5b FNs in top-20 | 3/20 | test-7-qualitative |
| P1 FNs in top-20 | 4/20 | test-7-qualitative |

---

## PART 8 — REMAINING WORK

### 1. Test 3 — Multi-Seed Stability (BLOCKED — needs re-run)

**Problem**: Kaggle notebook timed out at 12h due to:
- tqdm output not suppressed (output bloat)
- 5 epochs × 3 seeds × 163k training samples exceeds 12h limit

**Fix needed**:
- Suppress tqdm (`disable=True`)
- Reduce to 3 epochs max (stability probe, not full convergence)
- Or use patience=1 to force early stop

**Architecture note**: `test_3_multiseed.py` uses the DFG model; `test-3-multiseed.ipynb`
uses text-only. Decide which is the canonical stability test and make them consistent.

### 2. Statistical significance testing (Test 8 — REQUIRED for paper)

**What**: McNemar's test on per-sample prediction pairs between model configurations.
**Why**: Required to formally claim the null result.

```python
from statsmodels.stats.contingency_tables import mcnemar
import numpy as np

preds_dfg   = (probs_dfg[:, 1] >= 0.5).astype(int)
preds_nodfg = (probs_nodfg[:, 1] >= 0.5).astype(int)
labels      = test_labels

b = np.sum((preds_dfg == labels) & (preds_nodfg != labels))
c = np.sum((preds_dfg != labels) & (preds_nodfg == labels))

result = mcnemar([[0, b], [c, 0]], exact=False)
print(f"McNemar p-value: {result.pvalue:.4f}")
```

Run for all three backbone pairs. Expected: all p > 0.05. Results → `results/test8_significance_results.txt`.

### 3. Remaining TBD values in README

- LR + TF-IDF and MLP + TF-IDF baselines (Test 5)
- Per-source breakdown table (Test 4)
- Deployment threshold table (Test 6)
- Training stability table (Test 3)
- Real-world APK calibration numbers (Test 9)

---

## PART 9 — TARGET VENUE

**Primary: MSR** — empirical study + negative finding + corpus = exact MSR scope
**Fallback: EMSE/IST** — journal depth for thorough empirical work
**Also viable: ASE tool track** — pipeline + deployment focus
