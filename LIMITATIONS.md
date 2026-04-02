# LIMITATIONS.md
## Comprehensive Limitations of the Study

This document catalogues every known limitation of this research — methodological,
architectural, and empirical. It is intended both as a honest internal record and as
the source material for Section 8 (Limitations) of the paper.

---

## Category 1 — Training and Evaluation Methodology

### L1.1 — Fixed training budget may undertrain DFG mechanism

**What**: All models were trained for exactly 3 epochs with no validation set and no
checkpoint selection. The final epoch checkpoint was used for all evaluations.

**Why this is a limitation**: The DFG attention mechanism in GraphCodeBERT requires the
model to learn simultaneously which graph edges carry useful signal and how to integrate
that signal with token representations. This is a more complex learning task than standard
text fine-tuning, and there is genuine reason to believe it may require more epochs to
converge. The original GraphCodeBERT paper uses validation-based early stopping. Our fixed
3-epoch budget may have systematically undertrained the DFG components, contributing to the
null ablation result. We cannot rule out that DFG would show a benefit under a longer or
validation-guided training regime.

**Why we accepted this trade-off**: Validation-based early stopping with a separate held-out
test set requires a three-way split. On 199,960 samples with a 90/10 test reservation, a
reasonable validation split would further reduce training data to ~81%. For fairness across
all six model configurations, a fixed budget eliminates differential optimism bias from
checkpoint selection. The alternative — variable training length per model — introduces
a different confound. We chose consistency over optimal individual training.

**Paper framing**: "Our fixed three-epoch training budget, adopted to eliminate differential
checkpoint selection bias across model configurations, may not provide sufficient training for
the DFG attention mechanism to reach full convergence. The original GraphCodeBERT evaluation
uses validation-guided early stopping; our experimental constraints preclude this approach.
We therefore cannot rule out that extended training would reveal a DFG benefit on this data."

---

### L1.2 — DFG built over parser-recovery wrappers

The dataset contains syntactically incomplete code fragments — decompiled bytecode excerpts that lack enclosing class or method context required for valid Java parsing. To enable Tree-sitter DFG extraction across all 199,960 samples, each fragment is wrapped in a minimal syntactic scaffold (`public class DummyClass { public void dummyMethod() { ... } }`). This wrapper is applied uniformly to all samples regardless of class label.

The DFG includes edges from the wrapper tokens alongside edges from the real code content. For long, rich functions, the wrapper edges are a small fraction of the total DFG. For short, obfuscated fragments — which are disproportionately the hard cases — the wrapper may constitute a larger fraction of the graph.

This is not a methodological flaw but an engineering necessity. The alternative — excluding all syntactically incomplete fragments — would discard a large and unrepresentable fraction of real-world decompiled code, biasing the corpus toward the easier, more complete samples. Excluding them would make the evaluation look better while making the system less representative of real APK scanning conditions. The wrapper was the correct tradeoff.

The residual question — whether DFG edges from wrapper tokens meaningfully interfere with vulnerability-relevant edges — cannot be answered without an ablation that processes the same samples without wrappers, which requires syntactically complete inputs that are not available for all samples. The wrapper-to-content edge ratio is higher for short fragments, which are also the samples most affected by identifier obfuscation. These two factors compound.

**Paper framing**: "A practical challenge in processing decompiled Android bytecode at scale is that JADX output frequently produces syntactically incomplete fragments — method bodies without enclosing class context, statements extracted mid-scope, and expressions lacking surrounding declarations. To enable uniform Tree-sitter DFG extraction across our full 199,960-sample corpus without biasing toward syntactically complete samples, we implement a minimal parser-recovery wrapper that provides valid syntactic context while preserving the original code content. This wrapper is applied uniformly across all classes, ensuring no differential treatment between safe and vulnerable samples."

---

### L1.3 — Original 92% result was inflated by circular evaluation

**What**: The initial reported accuracy of 92.02% came from a model trained on an unseeded
90/10 split with no gradient clipping, where the checkpoint was selected by maximising
validation accuracy on the *same* 10% partition later used as the test set.

**Why this matters**: This was a methodological flaw — checkpoint selection criterion and
reported performance were computed on the same data. The correct figure under honest
evaluation (held-out test set, fixed training, gradient clipping) is 88.71%. The 3.31
percentage point difference is entirely explained by the evaluation flaw.

**Paper framing**: "An initial evaluation of the system reported 92.02% accuracy. Subsequent
methodology review identified circular evaluation: the checkpoint was selected by maximising
performance on the same partition used for final reporting. Correcting this — by adopting a
fixed training budget, strict train/test separation, and gradient clipping — yields 88.71%
on a genuinely held-out partition, confirming the earlier figure was inflated by optimism bias."

---

### L1.4 — Statistical significance not yet computed

**What**: All comparisons between model configurations (Table 1, 2, 3) report point
differences without accompanying statistical significance tests.

**Why this is a limitation**: The differences between all transformer models are small
(within 1 percentage point of accuracy, within 141 FN out of 19,996 samples). Without
significance testing, it is not possible to formally claim these differences are noise rather
than signal. This is particularly important for the null DFG claim.

**Status**: McNemar's test to be run before paper submission (see PAPER_TODO Task 1).

---

## Category 2 — Data and Preprocessing

### L2.1 — Identifier semantics stripped by decompilation

**What**: JADX decompilation replaces all class, method, and field names with
machine-generated tokens when the original APK was compiled with ProGuard, R8, or other
obfuscators. In the most extreme cases, every identifier becomes `class_N`, `method_N`,
`field_N` for sequential N.

**Why this is a limitation**: The DFG attention mechanism was designed to track meaningful
data flows between named variables. When identifier names carry no semantic information,
the DFG edges connect tokens that the model cannot interpret in relation to vulnerability
patterns. This is the primary explanation for the null DFG result (Pattern P5a in Test 8
qualitative analysis), but it also limits the text-only models — they too lose the semantic
richness of meaningful variable names.

**Scope**: 5 of the 20 most confident false negatives (P5a) show complete machine-generated
obfuscation. An unknown proportion of the full 1,184 FN set share this characteristic. It
is the dominant single failure mode.

---

### L2.2 — Kotlin compiler generates synthetic non-semantic identifiers

**What**: Kotlin's lambda compilation and coroutine mechanism produce class names like
`-$$Lambda$ClassName$hashcode` and `ClassName$functionName$N` that are non-semantic by
design. These differ structurally from both clean Java identifiers and ProGuard-obfuscated
Java identifiers.

**Why this is a limitation**: The model was trained primarily on Java (LVDAndro) and C/C++
(Draper, Devign, Juliet). Kotlin-specific decompilation patterns — coroutine continuation
passing, lambda synthetic classes, Kotlin standard library wrappers — are underrepresented
in training. 3 of the top-20 FNs (P5b) show this pattern.

---

### L2.3 — Structural fragmentation produces impossible Java

**What**: JADX sometimes produces decompiled output that violates Java grammar: `package`
declarations inside method bodies, `import` statements after executable code, field
declarations interleaved with method invocations.

**Why this is a limitation**: The synthetic `DummyClass` wrapper cannot repair interior code
that is syntactically invalid. Tree-sitter parses these fragments with best-effort recovery,
producing ASTs and DFGs that do not correspond to any coherent program. The model learns
this invalid-Java surface pattern as safe because training data contains it in both classes,
but the vulnerability signal in such fragments is essentially unlearnable.

**Scope**: 4 of the top-20 FNs (P1) show structural fragmentation.

---

### L2.4 — Fractional sampling from source datasets

**What**: Each of the four source datasets was sampled (not used in full) to enforce 1:1
class balance across the unified corpus.

**Why this is a limitation**: Sampling introduces selection bias — the sampled subset may
not be representative of the full distribution within each source. Devign in particular
contributes only 25,000 samples out of its full ~27,000, and those samples were selected
without stratification by vulnerability type, function length, or language subset. It is
possible that the sampled Devign subset is easier or harder than the full dataset.

---

### L2.5 — DFG node budget may truncate vulnerability-relevant edges

**What**: The DFG is capped at 128 nodes per sample. For complex functions with many
variable definitions and uses, this truncates the graph, potentially discarding edges
that are relevant to the vulnerability pattern.

**Why this is a limitation**: Long, complex functions — which are more likely to appear
in Draper and Devign kernel code — are more likely to hit the 128-node cap. The
vulnerability-relevant edges may be in the portion of the DFG that was discarded. This
may contribute to the Draper and Devign performance gaps independently of the obfuscation
issue.

---

## Category 3 — Model Architecture and Training

### L3.1 — DFG node filtering in sliding window is imprecise

**What**: When a function exceeds 384 tokens, the pipeline splits it into overlapping
chunks. DFG nodes are filtered per chunk using substring matching:
`[node for node in dfg if node[0] in chunk_code]`. This filters by checking whether the
variable name appears as a substring of the chunk's source code string.

**Why this is a limitation**: For obfuscated code where variable names are single letters
(`a`, `b`, `i`, `n`) or short generic tokens, this produces false matches — a variable
named `i` matches any chunk containing the letter `i`. The chunk DFGs are therefore noisier
than intended. The correct approach would filter by character offset, checking whether the
node's position falls within the chunk's character range.

**Practical impact**: Given the null DFG result, this imprecision likely has minimal effect
on reported numbers. However it means the sliding window's DFG quality is lower than
achievable, potentially making the long-function case even harder for DFG to help with.

---

### L3.2 — Single-function analysis scope

**What**: All models classify individual functions in isolation. The classifier receives
one function's code and DFG at a time, with no access to calling context, class-level
state, or inter-function data flows.

**Why this is a limitation**: A substantial fraction of real-world vulnerabilities are
inter-procedural — they manifest as incorrect handling of values passed across function
boundaries. 3 of the top-20 FNs (P7) involve accessing sensitive state from parent classes
or passing untrusted data through chains of method calls. No single-function model can
detect these patterns regardless of architecture.

---

### L3.3 — Context window truncation

**What**: The maximum code sequence length is 384 tokens. Functions exceeding this are
handled by the sliding window, which takes the maximum probability across overlapping
chunks.

**Why this is a limitation**: The sliding window strategy cannot recover vulnerability
signals that span chunk boundaries. If the first 384 tokens of a function appear benign
and the vulnerability is encoded in a subsequent chunk, the model may assign low probability
to the early chunks and miss the vulnerability even if it correctly identifies the later
chunk. The Devign evaluation directly evidenced this: sequences up to 2,543 tokens were
observed, far beyond what the sliding window handles effectively.

---

## Category 4 — Evaluation and Deployment

### L4.1 — Real APK evaluation lacks ground truth

**What**: The scanner calibration run now covers 13 downloaded APK report JSONs
(23,005 functions total), reported as vulnerable function rates and probability
distributions. There is still no ground truth labelling of which specific functions in
these APKs are actually vulnerable.

**Why this is a limitation**: Without ground truth, it is not possible to compute precision
or recall on the real APK evaluation. The calibration result is stronger than before because
the probability distribution is now aggregated across 13 reports and is sharply concentrated
near 0.0, but the "near-zero false-positive hallucinations" claim remains an indirect
inference rather than a direct measurement. A rigorous evaluation would require manual review
or authoritative labelling of the flagged functions.

---

### L4.2 — InsecureShop flag rate lower than clean apps

**What**: InsecureShop (deliberately vulnerable) flags 4.8% of functions, while
AntennaPod (clean) flags 8.4%.

**Why this is a limitation**: This counterintuitive result is explained by training
distribution boundary — InsecureShop's textbook vulnerabilities differ at the bytecode
level from the CVE-labelled patterns in training. However it demonstrates that the system
cannot be used as a binary APK-level classifier. It is a function-level triage signal,
not an APK-level verdict. Claims about the scanner's ability to identify "vulnerable apps"
cannot be made from these results.

---

### L4.3 — Commercial obfuscation defeats targeted filtering

**What**: ProGuard and DexGuard collapse recognisable package namespaces to single-letter
paths (`a/b/c.java`), defeating the manifest-aware package filter that identifies developer
code.

**Why this is a limitation**: The most security-sensitive production apps — financial,
healthcare, enterprise — are precisely those most likely to use commercial obfuscation. The
pipeline requires whole-app brute-force scanning for these cases, dramatically increasing
compute cost and noise from third-party libraries.

---

### L4.4 — Static analysis scope

**What**: The system performs static analysis only. It has no access to runtime state,
dynamic values, external configuration, or user interaction flows.

**Why this is a limitation**: Vulnerabilities that depend on specific runtime conditions —
integer overflow from a particular input value, race condition triggered by timing, insecure
configuration loaded from a remote server — are not detectable by static analysis regardless
of model quality.

---

### L4.5 — Juliet 100% inflates aggregate metrics

**What**: Juliet Test Suite samples achieve 100% classification accuracy. These 2,533
samples (12.7% of the test set) contribute to the reported overall accuracy without
reflecting real-world capability.

**Why this is a limitation**: Juliet's synthetic, structured vulnerability patterns are
significantly easier to classify than real decompiled code. Aggregate accuracy figures
that include Juliet overstate the system's capability on realistic inputs. Per-source
results (Table 5) are the honest numbers.

---

## Category 5 — External Validity

### L5.1 — Devign domain gap limits C/C++ claims

**What**: Devign (67.58% accuracy) represents Linux kernel C code from QEMU and FFmpeg.

**Why this is a limitation**: The system should not be presented as a general C/C++
vulnerability detector. The Devign gap is explained by three factors: underrepresentation
of kernel idioms in training, token truncation on long kernel functions (up to 2,543
tokens observed), and predominantly inter-procedural vulnerability patterns. Any deployment
on C/C++ code from kernel or systems domains should expect substantially degraded performance.

---

### L5.2 — Dataset source imbalance in training

**What**: LVDAndro and Draper each contribute 75,000 samples, while Devign and Juliet
contribute 25,000 each. Despite class balance within each source, the sources themselves
are not equally represented.

**Why this is a limitation**: The model's learned representations are dominated by LVDAndro
(Android Java) and Draper (C/C++ CVEs). Devign and Juliet patterns are learned with less
intensity. This directly explains the Devign performance gap and potentially contributes to
the Draper-Devign performance differential despite both being C/C++.

---

### L5.3 — Comparison models not available for direct evaluation

**What**: LineVul, VulBERTa, and ReGVD were not available as reproducible fine-tunable
checkpoints and could not be evaluated on the same test split.

**Why this is a limitation**: Without direct comparison to these published systems, it is
not possible to situate the system's performance relative to the state of the art in
vulnerability detection. The cross-backbone comparison (CodeBERT, GCB, UniXcoder) provides
an architectural comparison but not a comparison to systems specifically designed and
optimised for vulnerability detection.

---

## Summary Priority Table

| ID | Limitation | Severity | Affects claim | Mitigated in paper? |
|---|---|---|---|---|
| L1.1 | Fixed training may undertrain DFG | High | Null DFG finding | Partially — acknowledged |
| L1.2 | DFG parser-recovery wrappers | Medium | Null DFG finding | Yes — engineering necessity |
| L1.4 | No statistical significance tests | High | All comparisons | No — pending Task 1 |
| L2.1 | Obfuscation strips DFG semantics | Medium | Core finding | Yes — P5a explanation |
| L3.2 | Single-function scope | Medium | FN patterns | Yes — P7 documented |
| L4.1 | Real APK lacks ground truth | Medium | Scanner claims | Partially — rate framing |
| L4.2 | InsecureShop result | Medium | Scanner claims | Yes — distribution explanation |
| L4.3 | Obfuscation defeats filtering | Medium | Deployment | Yes — Test D |
| L2.2 | Kotlin synthetic identifiers | Low | FN patterns | Yes — P5b documented |
| L2.3 | Structural fragmentation | Low | FN patterns | Yes — P1 documented |
| L3.1 | Sliding window DFG imprecision | Low | Long-function quality | Noted |
| L4.4 | Static analysis scope | Low | General | Noted |
| L4.5 | Juliet inflates metrics | Low | Aggregate accuracy | Yes — per-source table |
| L5.3 | No SOTA comparison | Low | Positioning | Yes — cross-backbone instead |
