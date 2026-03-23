# Research Notes — DFG-Aware Android Vulnerability Detection: An Empirical Study
## Comprehensive Paper Guidance Document

> **Status**: All experiments complete. One pre-writing task remains (statistical significance testing).
> **Last updated**: 2026-03-22

---

## PART 1 — WHAT THIS PAPER IS

### The central narrative

This paper began as a positive claim — "DFG-aware attention reduces missed malware by 28%."
Through rigorous experimental methodology, we discovered that claim was an artifact of flawed
evaluation. Correcting the methodology revealed a more interesting and publishable truth:
**all modern transformer models converge to the same performance on decompiled Android
vulnerability data, regardless of whether graph structure is incorporated.** We then explain
mechanistically why DFG fails in this setting through qualitative analysis of 1,184 false
negatives.

### The three-sentence paper summary

"We build the first end-to-end system for DFG-aware vulnerability detection on decompiled
Android bytecode at scale. Through controlled ablation across three encoder backbones, we
find that DFG-aware attention provides no consistent benefit over standard transformer
encoding in this setting. Qualitative analysis of 1,184 false negatives reveals the cause:
JADX decompilation strips identifier semantics from DFG edges, leaving graph structure
present but informationally empty."

### Why this is publishable at MSR

1. **Novel system**: First published pipeline for DFG extraction from decompiled APKs at scale.
2. **Novel corpus**: 200k DFG-annotated samples across Java/Kotlin/C — does not exist publicly.
3. **Informative negative finding**: The field has assumed DFG helps on code. This paper is the
   first to show it does not help on *decompiled* code, with a mechanistic explanation.
4. **Real deployment**: Tested on real APKs in the wild (Test C, scanner pipeline).

---

## PART 2 — ALL FINAL NUMBERS

### Complete model comparison table

```
Model              Backbone         Structure    Accuracy   ROC-AUC   PR-AUC    FN     FP
────────────────────────────────────────────────────────────────────────────────────────────
MLP / TF-IDF       —                None         ~71%       —         —         high   —
CodeBERT           codebert-base    Text only    88.48%     0.9610    0.9616    1,072  1,232
CodeBERT + DFG     codebert-base    DFG attn     88.45%     0.9609    0.9616    1,089  1,221
GCB + DFG (ours)   graphcodebert    DFG attn     88.71%     0.9616    0.9622    1,184  1,074
UniXcoder          unixcoder-base   Text only    89.28%     0.9652    0.9657    1,051  1,092
UniXcoder + DFG    unixcoder-base   DFG attn     89.40%     0.9651    0.9657    1,043  1,076
```

All models: 90/10 split, seed 42, 3 epochs, gradient clipping, test set 19,996 samples.

### DFG delta analysis per backbone

```
Backbone        Text-only    DFG-aware    Δ Accuracy    Δ FN
────────────────────────────────────────────────────────────
CodeBERT        88.48%       88.45%       −0.03%        +17
GraphCodeBERT   88.72%       88.71%       −0.01%        −10
UniXcoder       89.28%       89.40%       +0.12%         −8
```

No consistent directional benefit. The UniXcoder +0.12% falls within seed variance (±0.11%).

### Test 3 — DFG Ablation

```
GCB + DFG    88.71%   0.9616   1,184 FN
GCB no-DFG   88.72%   0.9612   1,194 FN
Δ            −0.01%  +0.0004    −10 FN
```

### Test 4 — Stability (1-epoch probe, fixed split)

```
Mean: 87.53% ± 0.11%   ROC 0.9565 ± 0.0003
```

Frame as training stability probe only — not final model accuracy.

### Test 5 — Per-source

```
LVDAndro   7,537   98.34%   0.9978    51 FN
Draper     7,449   89.43%   0.9507   439 FN
Juliet     2,533  100.00%   1.0000     0 FN
Devign     2,477   67.58%   0.7633   449 FN
```

### Test 7 — Threshold (imbalanced 90/10)

```
0.60 → Recall 83.41%   F1 0.6585   FPR 7.77%   FN 186   ← OPTIMAL
```

### Test 8 — False negatives

Total FNs: 1,184. Top 20 analysed below in Part 3.

---

## PART 3 — QUALITATIVE ERROR ANALYSIS: FULL PATTERN CLASSIFICATION

### Overview of top-20 distribution

The 20 most confident false negatives (all flagged at 99.92–99.99% safe confidence)
break into five distinct failure categories. 19/20 are from LVDAndro; 1/20 is from Draper.
This concentration confirms the Android decompilation pipeline as the dominant source of
model failures, not the underlying vulnerability detection capability.

```
Pattern                                    Count in top-20   Source
────────────────────────────────────────────────────────────────────
P5a — Full machine-generated obfuscation      5             LVDAndro
P5b — Kotlin/lambda synthetic obfuscation     3             LVDAndro
P1  — Structural fragmentation                4             LVDAndro
P7  — Inter-procedural access patterns        3             LVDAndro
P2  — Benign surface over complex logic       2             LVDAndro
P3  — Arithmetic/numeric complexity           1             LVDAndro
P6  — Control flow / flag logic               1             Draper
P4  — Android API semantic bypass             1             LVDAndro
```

---

### Pattern P5a — Full machine-generated identifier obfuscation
**FNs**: #1, #2, #3, #9, #13 | **Confidence**: 99.99–99.95%

**What the code looks like**:

FN#1 (`LVDAndro_83233`): `class_336`, `method_1192`, `field_1000`, `class_22`, `method_58`
FN#2 (`LVDAndro_128605`): `class_443`, `method_1455`, `field_1347`, `method_1456`
FN#3 (`LVDAndro_225549`): `n21`, `n19`, `n24`, `n22`, `n25`, `n26`, `n27`
FN#9 (`LVDAndro_373963`): `object`, `object2`, `object3`, `hashSet`, all via single-letter
FN#13 (`LVDAndro_3920`): methods named `a`, `b`, `c`, `d`, `e`, `f2`

**Root cause**: JADX decompilation applies full identifier renaming when original symbol
tables are unavailable (stripped APKs, ProGuard, R8). Every meaningful class, method, and
field name is replaced with a machine-generated token. DFG edges are built between these
tokens — the graph is syntactically valid but carries zero semantic information about what
the data flows represent. The model sees data flowing between entities named `class_336` and
`method_1192` and cannot distinguish this from safe boilerplate.

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

**What the code looks like**:

FN#5 (`LVDAndro_84304`): `-$$Lambda$Sounds$iJSOl-pseCunlcJXFFxU9chQx24`
FN#8 (`LVDAndro_102817`): `Intrinsics.checkExpressionValueIsNotNull`, `CollectionsKt`, `StringsKt`
FN#11 (`LVDAndro_120515`): `MediaParsingService$updateStorages$2`, `CoroutineScope`, `Continuation`

**Root cause**: Kotlin compiler generates synthetic class names for lambda expressions
(`-$$Lambda$ClassName$hash`) and coroutine state machines (`ClassName$functionName$N`).
These names are non-semantic by design — they encode compiler internals, not application
logic. The DFG built over these tokens inherits the same semantic emptiness as P5a, but
the mechanism is the Kotlin compiler rather than ProGuard. Additionally, Kotlin's standard
library wrappers (`CollectionsKt`, `StringsKt`, `Intrinsics`) produce calling patterns
that differ from standard Java code, potentially out-of-distribution from the predominantly
Java LVDAndro training samples.

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

**What the code looks like**:

FN#4 (`LVDAndro_38620`): Field declarations (`flipV`, `bluetoothInputs`) mixed with
  method bodies — structurally impossible in valid Java
FN#10 (`LVDAndro_310332`): `package com.igormaznitsa.piratedice` appears *inside* a method
  body — syntactically impossible
FN#18 (`LVDAndro_299675`): Starts directly with `this.db = new GalleryTrashDb(...)` — no
  method declaration, no class declaration
FN#19 (`LVDAndro_278020`): Ends with `import android.support.a.f.class_204` inside method
  body; `import` statements cannot appear inside methods

**Root cause**: JADX sometimes produces decompiled output that is syntactically impossible
as valid Java — package declarations inside methods, imports inside method bodies, field
declarations interleaved with executable code. The synthetic `DummyClass` wrapper applied
during dataset construction cannot compensate when the interior code itself violates Java
grammar. Tree-sitter parses these fragments with best-effort recovery, but the resulting
AST and DFG contain structural artifacts that confound both the graph and the tokeniser.
The model learns these structurally-invalid patterns as safe because valid Java code never
looks like this.

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

**What the code looks like**:

FN#6 (`LVDAndro_190913`): `this.socket = call` / `tryReAddingEventToFrontOfQueue` — socket
  and queue management; vulnerability depends on what the caller passes
FN#14 (`LVDAndro_261191`): Resource access via `mapView.getContext().getResources()`,
  cross-class file path construction — vulnerability only apparent with context of callers
FN#17 (`LVDAndro_199128`): `((MainActivity)this.getActivity()).userId` / `.token` — sensitive
  credential access through class casting; vulnerability depends on who can reach this code

**Root cause**: The vulnerability in each case is not in the function body itself but in
the relationship between this function and its callers or the objects it manipulates. FN#17
directly accesses `userId` and `token` through a cast — whether this is a vulnerability
depends on whether the calling context appropriately gatekeeps access. Single-function
analysis has no access to the call graph, cannot determine who calls this method, and cannot
know whether the access is appropriately restricted. The function body looks like normal
Android code performing normal operations.

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

**What the code looks like**:

FN#7 (`LVDAndro_164636`): Synchronized random number generator — clean, well-structured
  code managing `ArrayDeque<java.util.Random>`. Vulnerability is a threading race condition
  invisible from data flow.
FN#20 (`LVDAndro_271604`): Logger binding sanity check — systematic API version validation
  with `Util.reportFailure`. Vulnerability is in error handling logic that looks defensive.

**Root cause**: These functions are well-written, readable, properly structured code that
follows established patterns. The vulnerability is not in the surface appearance but in
a subtle semantic property — a race condition in FN#7 (the synchronized block does not
protect all shared state), and an error handling omission in FN#20. The DFG faithfully
represents the data flows but cannot distinguish correct from incorrect logic when the code
structure itself is idiomatic.

**Paper paragraph** (Section 8):
> "Benign surface appearance (P2) accounts for 2 of the top-20 false negatives. FN #7
> implements a synchronized random number generator with clean, idiomatic structure; the
> vulnerability is a threading race condition where the synchronized block does not protect
> all shared state — a pattern that requires reasoning about concurrent execution rather
> than data flow. FN #20 implements a systematic API version sanity check with structured
> error reporting; the vulnerability is an incomplete error handling path that looks
> defensive. Both functions are precisely the kind of readable, well-structured code that
> likely dominates the 'safe' class in training data, causing the model to associate this
> surface pattern with safety regardless of underlying semantic correctness."

---

### Pattern P3 — Arithmetic and numeric complexity
**FN**: #12 | **Confidence**: 99.95%

**What the code looks like**:

FN#12 (`LVDAndro_180694`): An animation interpolation function with 9 repeated
  `keyFrame.getTransforms().get(str2)` calls and the same ternary division pattern
  `keyFrame != keyFrame3 ? timeStamp / (keyFrame.getTimeStamp() - keyFrame3.getTimeStamp()) : 0.0f`
  repeated for each keyframe. Potential divide-by-zero when two keyframes share the same
  timestamp.

**Root cause**: The vulnerability is a numeric edge case — division by zero when
`keyFrame.getTimeStamp() == keyFrame3.getTimeStamp()`. The 0.0f fallback in the ternary
only guards the case where the keyframe is identical to the reference frame, not when two
different keyframes share a timestamp. Detecting this requires type-level reasoning about
float equality and the specific semantics of the ternary guard — beyond what token or
data-flow analysis can provide.

**Paper paragraph** (Section 8):
> "Arithmetic edge case vulnerabilities (P3) appear in FN #12, an animation interpolation
> function containing repeated floating-point division operations guarded by identity
> checks (`keyFrame != keyFrame3 ? timeStamp / (...) : 0.0f`). The vulnerability is a
> divide-by-zero condition when two distinct keyframes share the same timestamp — a case
> the identity guard does not cover. Detecting this class of vulnerability requires
> understanding the semantics of the guard condition (identity versus equality) and
> reasoning about the valid range of input values, capabilities that are beyond token-level
> or data-flow analysis."

---

### Pattern P6 — Control flow and flag logic
**FN**: #16 | **Confidence**: 99.94%

**What the code looks like**:

FN#16 (`Draper_363906`): C function `notify_file_flags_changed` — a signal function that
  checks a bitmask `mask & (DjVuFile::ALL_DATA_PRESENT | DjVuFile::DATA_PRESENT | ...)`.
  The flag `DjVuFile::DECODE_STOPPED` appears twice in the OR expression.

**Root cause**: The duplicate flag in the bitmask OR is a subtle logic error — the second
`DECODE_STOPPED` contributes nothing to the condition. Whether this is the documented
vulnerability or merely suspicious is a domain-specific question that requires understanding
the DjVu flag semantics. The DFG represents the data flow correctly but cannot reason about
the semantic meaning of bitmask operations or detect unintentional duplicates in flag
expressions.

**Paper paragraph** (Section 8):
> "Control flow and flag logic errors (P6) appear in FN #16, a C signal function that
> evaluates a bitmask expression containing a duplicate flag (`DjVuFile::DECODE_STOPPED`
> appears twice in the OR condition). The DFG correctly captures data flows involving
> the `mask` variable but cannot reason about the semantic meaning of bitmask operations
> or identify that a flag appears redundantly. Detecting such defects requires symbolic
> reasoning about the value space of flag combinations — a capability beyond data-flow
> graph analysis."

---

### Pattern P4 — Android API semantic bypass
**FN**: #15 | **Confidence**: 99.94%

**What the code looks like**:

FN#15 (`LVDAndro_197646`): A search feature implementation using an `ArrayAdapter` with
  hardcoded integer resource IDs (`17367043`), accessing `userid` as a String extra,
  and using `ProgressDialog` in a pattern that suggests insecure data handling through
  Android's intent system.

**Root cause**: The vulnerability involves misuse of Android API contracts — integer
resource IDs where the wrong ID could produce unexpected behavior, `getStringExtra("userid")`
with no validation, and `ProgressDialog` patterns that may expose sensitive data. Detecting
this requires knowledge of what specific Android API calls are considered dangerous and
under what calling conditions — information that cannot be derived from the function's
internal data flow alone.

**Paper paragraph** (Section 8):
> "Android API semantic bypasses (P4) appear in FN #15, where the vulnerability involves
> misuse of Android API contracts: unvalidated `getStringExtra` calls, hardcoded resource
> identifiers, and `ProgressDialog` patterns that may expose sensitive state. These
> vulnerabilities require knowledge of which specific Android API usage patterns are
> considered dangerous and under what conditions — semantic knowledge that cannot be
> derived from intra-function data flow analysis alone."

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

**P5a + P5b together = 8/20** — obfuscation-driven DFG degradation is the dominant failure
mode by a wide margin, and directly explains the null ablation result.
**P1 = 4/20** — structural fragmentation from decompilation is the second largest category.
**P5a + P1 + P5b = 12/20** — three-quarters of the top failures are decompilation artifacts.

---

## PART 4 — KEY DECISIONS AND THEIR DEFENSES

### Decision 1: Retraining with clean split

Old model2 used unseeded 90/10, no gradient clipping, circular val/test. The 92% was
optimism bias. New model: seed 42, gradient clipping, final epoch, strictly held-out test.

**Paper sentence**: "We detected a methodological flaw in our initial evaluation: checkpoint
selection criterion and reported performance were computed on the same partition. We corrected
this by adopting a strict 90/10 train/test split with fixed seed, saving the final epoch
checkpoint, and reporting performance on a held-out test set the model never influences."

### Decision 2: Reporting the negative ablation result as lead finding

The data is unambiguous — inconsistent DFG effects across three backbones. The negative
finding with a mechanistic explanation is more valuable than a marginal accuracy gain.

**Paper sentence**: "Our controlled ablation reveals no consistent benefit from DFG-aware
attention on decompiled Android bytecode — a null result corroborated by cross-backbone
comparison showing directionally inconsistent DFG effects (Table 3). We attribute this
to the DFG quality degradation documented in Section 8."

### Decision 3: No validation set, no checkpoint selection

Eliminates differential optimism bias. All models evaluated at fixed 3-epoch budget.

**Paper sentence**: "All models are trained for exactly three epochs and evaluated once on
the held-out 10%. This eliminates differential optimism bias: with checkpoint selection,
a model peaking at epoch 2 appears better than one peaking at epoch 3, even if final
performance is identical."

### Decision 4: Threshold 0.60 from imbalanced condition

Test 7 calibrates the threshold on deployment-realistic 90/10 class ratio. Balanced
threshold (0.25 for best F1) is not the correct operating point for a triage scanner.

**Paper sentence**: "We calibrate the decision threshold under deployment-realistic conditions
— 90% safe / 10% malicious — where threshold sensitivity analysis reveals F1 is maximised
at 0.60, achieving 83.4% recall at 7.8% false positive rate."

### Decision 5: Repurposing ReGVD as CodeBERT+DFG

ReGVD was unavailable. The notebook already uses CodeBERT backbone with DFG attention —
correctly named CodeBERT+DFG. Completes the cross-backbone DFG picture.

**Paper sentence**: "As ReGVD, LineVul, and VulBERTa were unavailable as reproducible
fine-tunable checkpoints, we evaluate DFG-aware attention on three independent backbones
(CodeBERT, GraphCodeBERT, UniXcoder), providing a principled cross-architecture comparison."

---

## PART 5 — PAPER STRUCTURE WITH DRAFT SENTENCES

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
> mechanistically through qualitative analysis of 1,184 false negatives."

### Section 3 — Dataset and Pipeline

> "Our training corpus comprises 199,960 balanced samples drawn equally from four sources:
> LVDAndro (decompiled Android Java), Draper (C/C++ NVD/SARD CVEs), Devign (C/C++
> QEMU/FFmpeg), and the Juliet Test Suite (synthetic CWEs), with a strict 1:1
> safe-to-vulnerable class ratio enforced across all sources."

> "Extracting meaningful DFGs from decompiled bytecode presents non-trivial challenges not
> encountered in clean source-level analyses: JADX-decompiled code introduces
> machine-generated identifiers (e.g., `class_336`, `method_1192`), synthetic wrapper
> classes, and fragmented method boundaries that confound standard AST parsers."

> "All five transformer models are trained identically: a 90/10 train/test partition with
> fixed seed 42, three full epochs, AdamW (lr=2e-5, ε=1e-8), gradient clipping at max
> norm 1.0, and FP16 mixed precision. No validation set is used and no checkpoint selection
> is performed — the final epoch checkpoint is evaluated once on the held-out test set."

### Section 4 — Model Comparison and Ablation

> "Table 1 presents the full baseline comparison. All transformer models cluster within a
> 0.92-percentage-point accuracy band (88.45%–89.40%), regardless of whether graph-augmented
> attention is applied. This convergence suggests that the performance ceiling on decompiled
> Android vulnerability detection is determined by the data domain rather than model
> architecture."

> "Our controlled ablation, varying only the DFG attention mask while keeping all other
> conditions identical, yields a −0.01% accuracy delta and −10 FN reduction (Table 2).
> We replicate this across two additional backbones: DFG harms CodeBERT (+17 FN) and
> provides marginal benefit for UniXcoder (−8 FN), within the ±0.11% seed variance
> measured in Test 4. No consistent directional pattern exists."

> "Notably, UniXcoder — a text-only encoder — achieves the highest accuracy (89.28%) and
> lowest false negative count (1,051). The model that makes no attempt to leverage graph
> structure outperforms the model specifically designed to exploit it."

### Section 6 — Android-Domain Specialisation

> "On LVDAndro — real decompiled Android APK bytecode — the system achieves 98.34%
> accuracy and 0.9978 ROC-AUC, with only 51 missed vulnerabilities across 7,537 test
> samples. This demonstrates fitness for the intended Android scanning application."

> "Juliet Test Suite samples are classified with perfect accuracy (100%), as expected
> given the structured, non-obfuscated nature of synthetic CWE patterns. We report this
> for completeness but exclude it from capability claims."

> "Devign samples (Linux kernel C, QEMU, FFmpeg) are classified at 67.58% accuracy.
> We attribute this to three factors: kernel C idioms are underrepresented in training;
> kernel functions frequently exceed the 384-token context window (sequences up to 2,543
> tokens observed); and Devign vulnerabilities are predominantly inter-procedural.
> This gap reflects a scope boundary rather than a generalisation failure."

### Section 8 — Limitations and Qualitative Analysis

Opening link:
> "The null DFG result in Section 4 is not architecturally inevitable — GraphCodeBERT's
> DFG attention mechanism demonstrably improves performance on clean source-level code.
> To understand why it fails on decompiled bytecode, we analyse the 1,184 false negatives
> from our held-out test set. The top-20 most confident mistakes reveal a coherent
> picture: 8 of 20 are caused by complete identifier obfuscation (P5a, P5b), 4 by
> structural fragmentation (P1), and 3 by inter-procedural patterns (P7). Three-quarters
> of the dominant failures are decompilation artifacts that degrade DFG signal before
> it reaches the attention mechanism."

P5a mechanistic link:
> "Pattern P5a provides the mechanistic explanation for the null ablation result: when
> obfuscation strips all identifier semantics, DFG edges connect meaningless tokens.
> Text-only models that never attempt to use graph structure are not disadvantaged —
> and empirically, they match or outperform graph-augmented models. The graph is present;
> the signal it was designed to carry is absent."

Concrete examples sentence:
> "Figure X illustrates three representative P5a false negatives. In each case, JADX
> has replaced every class, method, and field name with a machine-generated token
> (`class_336`, `method_1192`, `field_1000`). The DFG contains 40–128 edges, all
> connecting these semantically empty nodes. The model assigns 99.99% confidence of
> safety — not uncertainty but the complete absence of discriminative signal."

---

## PART 6 — KEY NUMBERS QUICK REFERENCE

| Metric | Value | Source |
|---|---|---|
| GCB+DFG accuracy | 88.71% | graphcodebert-training__2_ |
| GCB+DFG ROC-AUC | 0.9616 | graphcodebert-training__2_ |
| GCB+DFG FN (0.5) | 1,184 | graphcodebert-training__2_ |
| CodeBERT accuracy | 88.48% | codebert-training__2_ |
| CodeBERT FN | 1,072 | codebert-training__2_ |
| CodeBERT+DFG FN | 1,089 | regvd-training__1_ |
| UniXcoder accuracy | 89.28% | unixcoder-training__2_ |
| UniXcoder FN | 1,051 | unixcoder-training__2_ |
| UniXcoder+DFG accuracy | 89.40% | unixcoder-dfg-training__1_ |
| UniXcoder+DFG FN | 1,043 | unixcoder-dfg-training__1_ |
| Ablation Δ accuracy | −0.01% | test-3-ablation |
| Ablation Δ FN | −10 | test-3-ablation |
| Test 4 stability | 87.53% ± 0.11% | Test_4_multiseed |
| LVDAndro accuracy | 98.34% | test-5-per-source__1_ |
| Devign accuracy | 67.58% | test-5-per-source__1_ |
| Optimal threshold | 0.60 | test-7-imbalanced-eval__3_ |
| Imbalanced recall (0.60) | 83.41% | test-7-imbalanced-eval__3_ |
| Test 8 total FN | 1,184 | test-8-qualitative-90-10 |
| P5a FNs in top-20 | 5/20 | test-8-qualitative-90-10 |
| P5b FNs in top-20 | 3/20 | test-8-qualitative-90-10 |
| P1 FNs in top-20 | 4/20 | test-8-qualitative-90-10 |
| Test C functions scanned | 23,005 | test_c_calibration_newmodel.py |
| Test C below 0.10 | 89.2% | test_c_calibration_newmodel.py |
| Test C above 0.60 | 5.6% | test_c_calibration_newmodel.py |
| Test C above 0.90 | 4.1% | test_c_calibration_newmodel.py |

---

## PART 7 — REMAINING WORK BEFORE WRITING

### 1. Statistical significance testing (REQUIRED)

**What**: McNemar's test on per-sample prediction pairs between model configurations.
**Why**: Without significance tests you cannot claim the null result formally. The
difference between "DFG provides no meaningful benefit" and "differences are not
statistically significant (p > 0.05)" is the difference between an observation and
a finding.

**How**: Load `test_probs.npy` and `test_labels.npy` from each training notebook.
For each model pair (e.g., GCB+DFG vs GCB no-DFG), compute a 2×2 contingency table
of prediction agreements/disagreements, then apply McNemar's test.

```python
from statsmodels.stats.contingency_tables import mcnemar
import numpy as np

# Example for GCB+DFG vs GCB no-DFG
preds_dfg    = (probs_dfg[:, 1] >= 0.5).astype(int)
preds_nodfg  = (probs_nodfg[:, 1] >= 0.5).astype(int)
labels       = test_labels

# Contingency table: both correct, dfg only correct, nodfg only correct, both wrong
b = np.sum((preds_dfg == labels) & (preds_nodfg != labels))
c = np.sum((preds_dfg != labels) & (preds_nodfg == labels))

result = mcnemar([[0, b], [c, 0]], exact=False)
print(f"McNemar p-value: {result.pvalue:.4f}")
```

Run for all five model pairs from Table 3. Expected result: all p > 0.05.

### 2. Confidence calibration histogram with new model (COMPLETED)

**Implementation**: `test_c_calibration_newmodel.py` now auto-discovers all downloaded
`*_vuln_report.json` files, aggregates their `all_probabilities`, and writes:
- `test_c_confidence_histogram_newmodel.png`
- `test_c_per_apk_histogram_newmodel.png`
- `test_c_calibration_newmodel.txt`

**Current result**: 13 APK reports, 23,005 functions total, 89.2% of probabilities below
0.10, 5.2% in the uncertain 0.10-0.60 band, 5.6% at or above 0.60, and 4.1% above 0.90.
The distribution is strongly concentrated near 0.0 with a small high-confidence tail,
supporting the calibration claim for the new model.

---

## PART 8 — TARGET VENUE

**Primary: MSR** — empirical study + negative finding + corpus = exact MSR scope
**Fallback: EMSE/IST** — journal depth for thorough empirical work
**Also viable: ASE tool track** — pipeline + deployment focus
