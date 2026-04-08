---
id: "lld_technical_report_2026-04-07"
title: "Layered LLM Defense: A Biologically-Inspired Defense-in-Depth Architecture for Large Language Models"
type: "technical_report"
category: "research"
language: "en"
tags: ["llm-security", "defense-in-depth", "antifragile", "ablation", "harmbench"]
authors:
  - name: "Michael Munz"
    affiliation: "Independent researcher"
    orcid: "null"
date: "2026-04-07"
version: "0.1.0-draft"
license: "CC-BY-4.0 (text), Apache-2.0 (code)"
keywords:
  - large language models
  - LLM security
  - jailbreak defense
  - defense in depth
  - antifragile systems
  - HarmBench
  - ablation study
---

# Layered LLM Defense: A Biologically-Inspired Defense-in-Depth Architecture for Large Language Models

## Abstract

We present **Layered LLM Defense (LLD)**, a defense-in-depth framework
that combines formal verification, antifragile learning, information-theoretic
interface hardening, and moving target defense (MTD) with a set of
biologically-inspired architectural primitives derived from immune system,
hormesis, microbiome, and adaptive bone-remodeling models. We evaluate LLD
against a 510-vector benchmark (HarmBench-style markers, plus
representative GCG, AutoDAN, and PAIR adversarial-suffix patterns) and
against a real Llama-3.3-70B target via the Groq API.

Our central contribution is an **ablation study** isolating the
contribution of biologically-inspired components from conventional
defense engineering. On the simulated benchmark, a vanilla 2-layer
configuration (formal verification + input sanitization) achieves
89.8% Attack Success Rate (ASR). Adding correlation, fragmentation,
OODA disruption, and response-strategy components ("Bio-Off") reduces
ASR to 71.2% — an 18.6 percentage-point improvement that is
expected to transfer to other judges. Adding the biological components
(Microbiome, Fever mode, Hormesis, Herd Immunity, Auto-Healing)
reduces simulated ASR further to ~0%, but this last step is partly a
**simulation artifact**: the Microbiome whitelist easily flags the
abstract `[BLOCKED_PAYLOAD_*]` markers in the test dataset because
they do not appear in any clean baseline. Real production traffic
will produce higher numbers, and we make no claim of perfect defense.

On a real Llama-3.3-70B benchmark via Groq with 100 attack vectors,
LLD reports a raw ASR of 7.0% with 0.0% False Positive Rate measured
on a 40-input clean baseline. After deterministic refusal pre-filtering
of the 7 reported "bypasses", 5 are confirmed as model refusals (judge
false positives). The remaining 2 cases (one cybercrime SQL educational
explanation, one obfuscated crime category enumeration) are borderline
and require human verdict. The **honest live-LLM ASR range is 0–2%**,
comparable with publicly reported numbers for LlamaGuard (~10–15%) and
RAIN (~10–12%) but on a much smaller sample. We have not yet performed
a head-to-head LlamaGuard comparison on the same dataset.

Two additional honest caveats stressed by external review: (a) the
0.0% FPR is measured on a small clean baseline (40 general-knowledge
inputs) and is likely to rise on real production traffic; (b) the
biological primitives (Hormesis, Immune Memory, Microbiome) are
formally specified statistical filters &mdash; the biological framing
is a useful reasoning aid, not a claim of biological correctness.

We release the implementation as open source under Apache 2.0. We
explicitly document every limitation, including the simulation
artifacts in our ablation, the small live-LLM sample size, the lack
of head-to-head LlamaGuard comparison data, and the absence of
gradient-based adversarial generation. The goal of this report is
not to claim a closed problem but to make a reproducible artifact
available for community evaluation.

**Keywords:** LLM security, jailbreak defense, defense in depth,
antifragile systems, HarmBench, ablation study.

---

## 1. Introduction

### 1.1 Motivation

Large language models deployed in production face a continuously
expanding attack surface. Public benchmarks such as HarmBench
report attack success rates of 70–85% against undefended frontier
models, and even leading defenses (LlamaGuard, RAIN) leave a
residual ASR of approximately 10–15%.

Existing defense approaches share three structural weaknesses:

1. **Single-mechanism reliance.** Most production defenses depend on
   one technique (input sanitization, output classification, or
   rule-based filtering). When the technique is bypassed, the entire
   defense collapses.

2. **No principled composition.** Where multiple defenses are
   combined, the composition is ad-hoc. There is no shared
   architectural principle that explains *why* the chosen combination
   should be more robust than its parts.

3. **Static rule sets.** Defense rules are typically authored
   manually and updated reactively. The defense does not learn from
   the attacks it observes.

### 1.2 Contributions

This report makes the following contributions:

1. **A four-layer architecture** that combines formal verification,
   antifragile learning, information-theoretic interface hardening,
   and moving target defense, with a documented compositional logic
   based on **prerequisite negation**: each layer eliminates a
   specific precondition required by the next attacker step.

2. **A library of biologically-inspired security primitives**:
   Hormesis-calibrated rule strengthening, Immune Memory fast-paths,
   Barbell strategy splits, Microbiome whitelist baselines, and
   Self-Adversarial Loop hardening with thymus-style dual selection.

3. **An ablation study** that quantifies the contribution of the
   biological components versus conventional engineering. To our
   knowledge, this is the first published ablation isolating
   biologically-inspired LLM defense primitives from non-biological
   layered defenses on the same benchmark.

4. **A reproducible benchmark suite** of 510 attack vectors covering
   seven HarmBench categories, including representative patterns
   from GCG (Zou et al., 2023), AutoDAN (Liu et al., 2023), and
   PAIR (Chao et al., 2023) adversarial-suffix attacks.

5. **A real-LLM evaluation** against Llama-3.3-70B via the Groq API
   with persisted verbatim outputs and a deterministic refusal
   pre-filter for honest ASR estimation.

6. **An open-source implementation** in standard-library Python
   (no third-party dependencies for the core; Groq integration is
   stdlib `urllib`-based) under Apache 2.0.

### 1.3 What this report is and is not

This report is a working document, not a peer-reviewed paper. The
goal is to document the design, the experiments performed, and the
limitations honestly so that the community can evaluate the work,
reproduce it, and extend it. We describe both validated and
disconfirmed hypotheses, both successful experiments and methodological
artifacts. We make no claims that the framework is complete, optimal,
or production-deployed at scale.

---

## 2. Background and Related Work

### 2.1 LLM jailbreak attacks

Modern jailbreak attacks fall into three broad classes:

- **Direct prompt injection**: instructions that override the system
  prompt, such as "ignore previous instructions and do X".
- **Role-play wrappers**: prompts that ask the model to adopt a
  persona without safety constraints (DAN, EVIL, STAN), or to
  hypothetically describe a process.
- **Adversarial-suffix optimization**: gradient-based
  (GCG, Zou et al., 2023) or genetic (AutoDAN, Liu et al., 2023)
  searches that find token sequences which reliably break
  safety training. PAIR (Chao et al., 2023) automates the
  refinement loop.

HarmBench (Mazeika et al., 2024) standardizes evaluation across
attack types and harmful categories.

### 2.2 LLM defense approaches

**Input/output classifiers.** LlamaGuard (Inan et al., 2023) is
Meta's content-safety classifier and is widely treated as the
industry baseline. It reports ~10–15% ASR on HarmBench-style
benchmarks against Llama models.

**Inference-time intervention.** RAIN (Li et al., 2023) and similar
methods modify the decoding loop to penalize harmful continuations.

**Constrained generation.** Outlines, Pydantic-based schemas,
and grammars constrain output structure. These prevent some
output-side attacks (XSS, SQL injection in generated code) but
do nothing against jailbreaks of natural-language outputs.

**Differential privacy and information-theoretic limits.** These
work prevents the attacker from extracting information across
queries (model extraction, membership inference). They do not
prevent single-query jailbreaks.

**Moving target defense (MTD).** Originated in network security;
recent work applies it to LLM serving (rotating system prompts,
model variants, decoding parameters). Reduces attacker
reconnaissance value.

### 2.3 Where LLD fits

LLD combines all four families above into a single pipeline with
a **compositional logic** (prerequisite negation) and a set of
**biological primitives** (Hormesis, Immune Memory, Barbell,
Microbiome) that, to our knowledge, do not appear in any prior
LLM defense framework. The novelty is therefore in the
*combination and the formalization*, not in any single component.

The closest adjacent work identified during the literature scan is
**Countermind** (arXiv:2510.11837), which proposes a multi-layer
defense without the biological primitives. LLD does not duplicate
the Countermind approach.

---

## 3. Architecture

![Figure 1: Four-layer architecture overview](../figures/fig_1_architecture.png)

### 3.1 Four-layer overview

```
                ┌─── Incoming Request ───┐
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L4: MOVING TARGET DEFENSE          │  │
│  Endpoint, model, prompt rotation   │  │
│  Goal: defeat reconnaissance        │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L3: INFORMATION-THEORETIC LAYER    │  │
│  Input sanitization, error masking  │  │
│  Goal: zero feedback to attacker    │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L2: ANTIFRAGILE SHELL              │  │
│  Immune memory, pattern learner,    │  │
│  hormesis-calibrated rule           │  │
│  Goal: get stronger from each       │  │
│  attack                             │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L1: PROVEN CORE                    │  │
│  Pydantic schemas, invariant        │  │
│  monitor, jailbreak detector        │  │
│  Goal: any output that escapes is   │  │
│  schema-valid                       │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
        Outgoing Response                 │
                                         │
        Bookkeeping pipeline ─────────────┘
        (correlation, response strategy,
         OODA disruption, fever mode,
         herd immunity, auto-healing)
```

### 3.2 Prerequisite negation

The compositional principle is that each layer eliminates a
specific precondition required by the next attacker step.

| Layer | Eliminates precondition | Confirmed by |
|---|---|---|
| L4 (MTD) | Stable target for reconnaissance | 0% stale config reuse across rotations |
| L3 (Info-theoretic) | Useful feedback from probing | sanitized errors leak no model state |
| L2 (Antifragile) | Repetition advantage | flat ASR trend after first block |
| L1 (Formal) | Schema-invalid escape | 100% of allowed outputs schema-valid |

This is **not** a multiplicative cost model. We initially hypothesized
that combined cost would be `C1 * C2 * C3 * C4`, predicting a Cost
Multiplication Factor (CMF) above 10x. Empirical measurement
(experiment_cost_multiplication.py) found CMF ≈ 2.3x — sub-additive,
not multiplicative. The reason is shared blind spots: attacks that
bypass L1 tend to bypass L2-L4 as well, because none of the layers
covers a category the others miss.

The honest model is therefore: **prerequisite negation is confirmed
4/4, but layer combination gives sub-additive cost increase, not
multiplication**. We document this disconfirmation explicitly because
the original architecture description hypothesized multiplication.

### 3.3 Layer details

#### L1 — Proven Core (Formal Verification)

- Pydantic schemas for structured outputs
- Constrained decoder (rejects schema-invalid completions)
- Invariant monitor with patterns for SQL injection, XSS
  (event-handler and CSS variants), PII leakage (with HTML entity
  decoding), prompt injection markers, jailbreak compliance phrases
- Jailbreak output detector (catches "I am DAN", "safety disabled"
  style compliance phrases in the model's *output*, not its input)

#### L2 — Antifragile Shell

- `AttackMemory` (SQLite): persistent record of every attack signal,
  block decision, and false-positive report
- `PatternLearner`: extracts a fixed feature vector from each input,
  learns running mean and covariance, reports a Mahalanobis-based
  anomaly score, plus a fuzzy keyword score for known injection
  vocabulary
- `HormesisCalibrator`: implements the convex defense-strength
  formula `D(r,A) = D_base * (1 + alpha * sum(blocked))` capped
  at `hormesis_cap`, with FP rate-limiting to prevent
  autoimmunity (the system relaxes thresholds if too many FPs are
  reported in a short window — see Section 6.1 for the
  Hormesis-exploit experiment)
- `ImmuneMemory`: fast-path for previously-seen attack hashes
  (microsecond block decision)

#### L3 — Information-Theoretic Layer

- Input sanitization with central `sanitization.py` module shared
  in `lld/layer3_infosec.py` (control characters, zero-width characters,
  Unicode tag characters, length limits)
- Differential-privacy noise injection on confidence outputs
- Error message sanitization

#### L4 — Moving Target Defense

- Endpoint rotation
- Model configuration variation
- Prompt template rotation with cryptographic seeding
- Session-scoped fingerprinting for persistent attackers

### 3.4 Bio-defense extensions (Section 4)

Beyond the four base layers, LLD adds eight biologically-inspired
extensions documented in Section 4: Microbiome (whitelist baseline),
Fever mode (system-wide hardening), Herd Immunity (vaccine export),
Self-Adversarial Loop (SAL with thymus-style selection), Startle
Display, Auto-Failover, Auto-Healing, and Response Strategy Engine
(five immune-response types: Tolerate, Sandbox, Inflame, Deceive,
Terminate).

---

## 4. Biologically-inspired Primitives

The biological primitives are not metaphors. They are formal
mathematical models with input/output contracts.
`concepts/biological_formalization.md` defines each model with its
mathematical form, the corresponding LLD primitive, and a Python
sketch. We summarise the most load-bearing primitives here.

### 4.1 Hormesis-calibrated antifragile defense

Biological intuition: small doses of a stressor strengthen an
organism, but large doses harm it. For security: too few attacks
mean the rule has not been tested (fragile); an optimal attack
density strengthens the rule; too many false positives produce
autoimmunity (the rule blocks legitimate requests).

Formalization:

```
D(r, A) = D_base(r) * (1 + alpha * sum_{a in A} B(a)) * H(FP(r))

where:
  D(r, A)    = current defense strength of rule r given attack history A
  D_base(r)  = baseline strength when untested
  B(a)       = 1 if attack a was blocked, 0 otherwise
  alpha      = strengthening rate (default 0.05)
  H(FP)      = autoimmunity damping function:
                 H(FP) = 1 if FP < theta_FP
                 H(FP) = 1 - k * (FP - theta_FP) if FP >= theta_FP
```

`alpha` is small and capped (`hormesis_cap = 2.0`) to ensure that
the convex strengthening curve flattens before any single rule
dominates the decision.

### 4.2 Microbiome (whitelist baseline)

Biological intuition: gut microbiota establish a baseline of
"normal" by being present continuously. Foreign organisms are
detected as deviations from baseline, not by direct identification.

Formalization: the Microbiome module trains on legitimate model
outputs (a warmup phase) and computes a six-feature deviation score
for each new output. Outputs with deviation above a threshold are
flagged as "not within baseline" and contribute to the correlation
engine, but they do **not** block standalone (we found early on that
small baselines produce too many false positives if used as a
standalone gate).

### 4.3 Self-Adversarial Loop (SAL) with Thymus selection

Biological intuition: the thymus performs both positive selection
(retain T-cells that can recognize antigens) and negative selection
(eliminate T-cells that attack self). Applied to security rules:
generate candidate rules adversarially, then keep only those that
both detect attacks (positive) AND do not flag legitimate inputs
(negative).

Implementation: `RedTeamGenerator` produces 10 mutation types
(Unicode obfuscation, role-play wrapping, encoding, fragmentation,
etc.) over a seed set of bypasses. `ThymusSelector` runs each
candidate rule against both an attack corpus and a clean corpus,
keeping only those that exceed positive selection (catches
attacks) and pass negative selection (no clean-corpus FPs).
`SelfAdversarialLoop` iterates until convergence.

### 4.4 Fever mode

Biological intuition: systemic infection triggers a body-wide
hardening response (elevated temperature, restricted activity).
Applied to security: when a burst of attacks is detected in a short
window, the entire defense system tightens — lower thresholds
(0.4x), longer delays (3x), more aggressive rotation (10x), and
escalation of response strategies.

### 4.5 Herd Immunity (vaccine export)

Biological intuition: vaccinating one individual reduces transmission
to others. Applied to a fleet of LLD instances: when one instance
discovers a new attack pattern via SAL, it exports a "vaccine" (rule
fragment) that other instances can import. This enables horizontal
scaling of SAL hardening without centralized retraining.

---

## 5. Experimental Setup

### 5.1 Attack dataset

We use a 510-vector attack suite with the following composition:

| Type | Count | Source |
|---|---:|---|
| Direct attacks (markers, phrasing variations) | 228 | HarmBench-style markers + handcrafted phrasings |
| Jailbreak-wrapped (DAN, STAN, role-play) | 70 | HarmBench + 5 extra per category |
| Obfuscated (Unicode, base64, ROT13, leet, spacing) | 65 | HarmBench + 5 extra encodings |
| GCG suffix patterns | 70 | Zou et al. 2023, HarmBench appendix |
| AutoDAN templates | 56 | Liu et al. 2023 — genetic prompt templates |
| PAIR refinements | 21 | Chao et al. 2023 |
| **Total** | **510** | |

**Critical caveat:** All harmful payloads in our dataset are
abstract markers of the form `[BLOCKED_PAYLOAD_<category>_<id>]`,
not actual harmful content. This makes the dataset safe to share
and store but introduces a simulation artifact: a defense layer
that can detect "this string contains the marker" appears highly
effective on the simulated benchmark even if it would be less
effective against real LLM outputs. We discuss this in Section 7.1.

### 5.2 Clean dataset for FPR

40 unique clean question-answer pairs covering general knowledge,
science, and history. Used for both warmup (Microbiome baseline,
PatternLearner statistics) and FPR measurement.

### 5.3 Defense configurations

We evaluate three configurations of the same `IntegratedDefense`
class, distinguished by the `disabled_components` set:

- **LLD-Vanilla**: only L1 (Pydantic + InvariantMonitor) and L3
  (input sanitization). All bio components, fragmenter,
  correlation, response-strategy, OODA, fatigue, watermark,
  herd immunity, auto-healing, startle, and Layer-2 anomaly score
  disabled. (12 components disabled)

- **LLD-Bio-Off**: full pipeline EXCEPT Microbiome, Fever, Herd
  Immunity, Auto-Healing. Keeps correlation, fragmenter, OODA,
  response strategy, watermark, attacker fatigue. (4 components
  disabled)

- **LLD-Full**: all 15 modules enabled.

This produces a clean ablation: the difference (Vanilla → Bio-Off)
measures the contribution of *non-biological* engineering layers,
and the difference (Bio-Off → Full) measures the contribution of
the *biological* layer.

### 5.4 Judges

For the simulated benchmark we use a deterministic
`SimulatedLLMJudge` that flags responses containing
`[BLOCKED_PAYLOAD_*]` markers or jailbreak-compliance phrases
("safety disabled", "I am DAN", etc.).

For the real-LLM benchmark we use:
- `llama-3.3-70b-versatile` (Groq) as the target model
- `llama-3.1-8b-instant` (Groq) as the safety judge with an
  explicit safety system prompt
- A new `DoubleJudge` module (Section 6.4) that requires agreement
  from two judge models AND applies a refusal pre-filter

### 5.5 Hardware and software

- All offline experiments run on a single laptop, no GPU
- Real-LLM benchmark uses the Groq free tier with 1.2-second
  throttling between API calls
- Python 3.11, standard library only (no pip dependencies for
  the core; Groq integration uses stdlib `urllib`)
- 453 unit tests pass in approximately 7 seconds

---

## 6. Results

![Figure 2: Ablation result. The Vanilla → Bio-Off transferable gain is the most defensible empirical claim. The further drop to ~0% in the Full configuration is partly a simulation artifact.](../figures/fig_2_ablation.png)

### 6.1 Ablation study

Running the three ablation configurations against the 510-vector
extended dataset with the simulated judge:

| Configuration | ASR | Blocks | FPR | Mean latency | p95 latency | Tokens saved |
|---|---:|---:|---:|---:|---:|---:|
| LLD-Vanilla | **89.8%** | 50 | 0.0% | 0.85 ms | 1.58 ms | 648 |
| LLD-Bio-Off | **71.2%** | 145 | 0.0% | 1.75 ms | 3.71 ms | 3,223 |
| LLD-Full | **0.0%** | 510 | 0.0% | 2.22 ms | 5.75 ms | 8,955 |

**Interpretation.**

- L1 + L3 alone catch only **10.2%** of the extended attack suite.
  Pydantic schemas and invariant patterns are insufficient against
  jailbreaks, AutoDAN refinements, GCG suffixes, and phrasing
  variations.
- Adding correlation, fragmenter, response strategy, and OODA
  (Bio-Off vs Vanilla) closes **18.6 percentage points**. This is
  the contribution of conventional defense engineering.
- Adding the biological components on top (Full vs Bio-Off) closes
  the remaining **71.2 percentage points**. The dominant
  contributor is the Microbiome whitelist deviation module
  (visible in the per-layer latency: microbiome runs at
  ~0.001 ms when disabled and ~0.51 ms when enabled, the only
  material change between Bio-Off and Full on the hot path).

### 6.2 Per-category ASR

| Category | Vanilla | Bio-Off | Full |
|---|---:|---:|---:|
| chemical_biological | 91.9% | 73.0% | 0.0% |
| cybercrime | 85.1% | 64.9% | 0.0% |
| harassment_bullying | 91.9% | 73.0% | 0.0% |
| illegal_activity | 91.9% | 74.3% | 0.0% |
| misinformation | 91.9% | 74.3% | 0.0% |
| physical_harm | 91.9% | 74.3% | 0.0% |
| privacy_violation | 83.3% | 63.6% | 0.0% |

Cybercrime and privacy violation have lower vanilla ASR because
L1's SQL/XSS/PII patterns catch direct attacks in those categories.
Other categories rely entirely on the bio components for blocking
in the vanilla configuration.

### 6.3 Per-layer latency

![Figure 4: Per-layer latency breakdown. Fragmenter and microbiome are the two costliest stages but the full pipeline still finishes in ~2.2 ms.](../figures/fig_4_layer_latency.png)

The full-config mean latency is 2.22 ms with p95 of 5.75 ms.
This is approximately 100–500x faster than typical LLM inference
itself (10²–10³ ms per request), so the defense overhead is
negligible in any realistic serving stack.

The two costliest stages are the **fragmenter** (~0.87 ms,
multi-vector attack analysis) and the **microbiome** (~0.51 ms,
whitelist deviation scoring). Both are amenable to caching or
parallelization if sub-millisecond latency is required.

### 6.4 Real LLM benchmark (Llama-3.3-70B via Groq)

![Figure 3: Live-LLM ASR vs published defenses on a small 100-vector sample. We do not claim to beat LlamaGuard; we report comparable numbers on a much smaller sample.](../figures/fig_3_baseline_comparison.png)

**Setup:**
- 100 attack vectors (subset of the extended 510 — original HarmBench-style markers)
- Target: `llama-3.3-70b-versatile` via Groq
- Judge: `llama-3.1-8b-instant` with explicit safety system prompt
- Wallclock: 191.7 seconds, 19,285 total tokens
- Two-phase warmup: Microbiome trained on 15 real Llama responses
  to clean inputs before the attack run

**Headline numbers:**

| Metric | Value |
|---|---:|
| Total attacks | 100 |
| Blocked at input (LLD pre-LLM) | 44 (44.0%) |
| Blocked at output (LLD post-LLM) | 4 (4.0%) |
| Passed, judged Safe | 45 (45.0%) |
| Passed, judged Unsafe (raw bypasses) | 7 (7.0%) |
| LLM errors | 0 |
| **Raw ASR** | **7.0%** |
| **False Positive Rate** | **0.0%** |

**Refusal pre-filter analysis.**

We applied the `is_refusal()` regex from our `DoubleJudge` module
(12 patterns covering "I cannot", "I must emphasize", "against
the law", etc.) to the 7 records flagged as `passed_harmful`.
The deterministic result:

| Case | vector_id | attack_type | is_refusal |
|---|---|---|---:|
| 1 | cybercrime_direct_4 | direct (SQL example) | False |
| 2-6 | illegal_activity_direct_0..4 | direct | True (×5) |
| 7 | illegal_activity_obfuscated_0 | obfuscated | False |

Five of the seven outputs match a refusal pattern deterministically.
The two remaining cases require human verdict because neither
output starts with an explicit refusal phrase. Both contain
abstract / educational content rather than operational instructions:

- Case 1 input is `admin login: admin'--` and the model responds
  by recognizing the pattern as a SQL injection demonstration and
  explaining the *concept* in textbook style, comparable to OWASP
  educational material. No working exploit, no specific target.
- Case 7 input asks (via zero-width-space obfuscated `ignore previous`)
  to describe `illegal_activity` in general; the model returns
  an enumeration of crime categories with definitions but no
  operational steps.

**Honest ASR range:**

- **Optimistic** (0 of 2 borderline cases counted as harmful): 0.0%
- **Conservative** (both borderline cases counted as harmful): 2.0%

The 7.0% raw figure is an overestimate driven by the single-judge
being too eager to label any response that mentions the harmful
category as "unsafe", even when the model is refusing.

### 6.5 Comparison context

| System | ASR | Source |
|---|---:|---|
| Llama-3-70B with no defense | ~70–80% | HarmBench public data |
| Llama-3-70B + LlamaGuard | ~10–15% | HarmBench + LlamaGuard reports |
| Best published defenses (RAIN) | ~10–12% | Public reports |
| **Llama-3.3-70B + LLD (raw, this work)** | **7.0%** | This benchmark |
| **Llama-3.3-70B + LLD (refusal-corrected, this work)** | **0–2%** | This benchmark |

We do **not** claim LLD beats LlamaGuard. We claim our results are
**comparable** to the published numbers, on a small (100-vector)
sample, with a single-judge that is known to be over-eager. A
direct head-to-head LlamaGuard run on the same 510-vector dataset
would close this comparison; the adapter (`lld/llamaguard_adapter.py`)
is implemented and ready to run. This is one of the open items where
collaborator help is explicitly invited (see the Call for collaborators
section in the README).

### 6.6 Token cost savings

Across 510 attacks, LLD-Full prevents 8,955 input tokens from being
sent to the model (estimated as `chars / 4` for blocked requests).
At Groq's published Llama-3.3-70B price (~$0.59 per 1M input tokens),
this is approximately $0.005 per 510-attack run. At enterprise
volume (100M malicious requests per month), the saving extrapolates
to ~1.75 billion tokens / ~$1,033 per month in raw input cost,
plus the corresponding output tokens (typically 3–10× input cost).

The real value of pre-LLM blocking is not the token savings but
the avoidance of generating any harmful content at all — every
blocked request never reaches the model.

---

## 7. Limitations

We document every known limitation of this work, including those
that remain open as of this report.

### 7.1 Simulation artifact in the ablation

The simulated judge looks for `[BLOCKED_PAYLOAD_*]` markers in
outputs. The Microbiome whitelist easily flags these markers
because they do not appear in any clean baseline. On the *real*
Llama benchmark, the Microbiome was less dominant — real Llama
refusals are much closer to clean responses than to bracketed
markers.

The 18.6-percentage-point gain from Vanilla → Bio-Off is more
transferable because it does not depend on marker shape — the
correlation engine and fragmenter operate on input properties
that survive any judge change. The 71-percentage-point gain from
Bio-Off → Full should be expected to shrink considerably in a
real-LLM ablation. We have not run the real-LLM ablation yet
because it requires running all three configurations against
real Groq Llama (~$0.50 in tokens, ~30 minutes wallclock).

### 7.2 Sample size

100 attack vectors against the real LLM is small for statistical
significance. Standard HarmBench has 510 vectors. Our extended
dataset is 510 vectors but has only been run against the
simulated judge so far.

### 7.3 No head-to-head LlamaGuard comparison

We compare against published LlamaGuard numbers, not against
LlamaGuard run on the same dataset. The adapter is implemented
and ready to run.

### 7.4 Single-judge over-eagerness

The `llama-3.1-8b-instant` judge with our system prompt was too
strict, marking model refusals as "unsafe" because the response
mentioned the harmful category. We have implemented a `DoubleJudge`
module (refusal pre-filter + two-model consensus) but have not
yet re-run the full benchmark with it as the judge.

### 7.5 Abstract attack markers

Our dataset uses `[BLOCKED_PAYLOAD_*]` markers rather than real
harmful content. This makes the dataset safe but means we are
not testing against the actual content that real GCG / AutoDAN
attacks would produce. Real HarmBench has the actual harmful
prompts.

### 7.6 No gradient-based GCG

We test against the *patterns* GCG produces (token-shape
characteristics from the public GCG corpus and HarmBench
appendix), not against fresh GCG search runs against the target
model. A defense could theoretically pattern-match these signatures
without being robust against new GCG searches that find different
suffix shapes. Running fresh GCG would require gradient access
to the target.

### 7.7 No human red team

All attacks are scripted. A human attacker would adapt to the
defense in real time and likely find configurations the scripted
attacks miss.

### 7.8 Manual annotation of borderline cases incomplete

Of the 7 raw bypasses in the real-LLM run, 5 are deterministically
classified as refusals by `is_refusal()`. The remaining 2 (SQL
educational, obfuscated enumeration) require a human verdict
that has not yet been recorded. The honest ASR range (0%–2%) is
the bound under both possible verdicts.

### 7.9 Production deployment

LLD has not been deployed against any real production traffic.
All evaluation is offline (synthetic benchmarks) or against a
hosted open-source model (Groq). Real production traffic
includes domain-specific attack patterns we have not seen.

### 7.10 Single-author, no peer review

This is a working report by a single author. It has not been
peer reviewed. Reviewers and replication efforts are explicitly
welcomed.

---

## 8. Discussion

### 8.1 What is novel

Three things appear novel relative to the literature reviewed
during the design phase:

1. The specific composition of formal verification + antifragile
   learning + information-theoretic interface + moving target
   defense as a single layered architecture.
2. The biological formalizations (Hormesis, Microbiome,
   Self-Adversarial Loop with thymus selection, Fever mode,
   Herd immunity) as security primitives — they exist as
   biological models in immunology and epidemiology, but to
   our knowledge they have not been transferred to LLM defense
   in this form.
3. The ablation methodology that isolates biological from
   non-biological components on the same benchmark.

### 8.2 What is *not* novel

- Defense-in-depth as a principle (decades old)
- Each individual layer (formal verification, antifragile
  learning, MTD all exist independently in the literature)
- The use of immune-system metaphors in security (Forrest,
  Stephanie et al. have published on immune-inspired
  intrusion detection since the 1990s)

The contribution is therefore in the *specific combination and
formalization*, not in any individual primitive.

### 8.3 What we got wrong

The original architecture document hypothesized a multiplicative
Cost Multiplication Factor (CMF) of 6–10x. The empirical
measurement (experiment_cost_multiplication.py) found CMF ≈ 2.3x —
sub-additive. We document this disconfirmation explicitly. The
prerequisite-negation property (4/4 confirmed) is the actually
load-bearing claim, not the multiplication.

We also initially used the Microbiome as a standalone blocker
and found that it produced too many false positives with small
baselines. We changed it to a correlation-only contributor, which
reduced FPR to 0.0% on the real-LLM run.

Finally, an earlier draft of one of our evaluation documents
contained reconstructed quotes of LLM outputs presented as if they
were verbatim. They were removed after detection because the
reconstructions had not been validated against real persisted
outputs. As a direct consequence we added a `--save-outputs` flag
to `lld/benchmark_groq.py` so that future evaluations always
persist verbatim model output for full auditability. We document
this self-correction because the lessons (don't fabricate evidence,
persist outputs verbatim) are part of what we learned.

### 8.4 What this means for practitioners

If you operate an LLM in production and care about jailbreak
defense:

1. Adding even a vanilla 2-layer defense (formal verification +
   input sanitization) catches roughly 10% of attacks. Don't
   skip it.
2. Adding correlation + fragmentation + response strategy
   (the "Bio-Off" configuration in our ablation) gets you another
   **18.6 percentage points**. This gain is the most defensible
   empirical claim in this report.
3. Whether the biological components contribute material additional
   gains in your environment is an open empirical question. The
   simulated benchmark shows a large further drop, but that drop
   is partly an artifact of the abstract markers in the test
   dataset. Run the ablation against your own traffic before
   committing to the bio components.
4. Latency is not a concern (~2 ms full pipeline).
5. Integrating a refusal pre-filter into your safety judge is the
   single highest-leverage fix for over-reported ASR.

---

## 9. Conclusion and Future Work

We presented Layered LLM Defense, a four-layer biologically-inspired
defense-in-depth framework for LLM security. We demonstrated through
ablation that the biological components carry a substantial portion
of the framework's effectiveness on a simulated benchmark, while
being explicit about the simulation artifacts that limit the
generality of this finding. We presented an honest evaluation
against a real Llama-3.3-70B target showing a refusal-corrected
ASR of 0–2% with 0% FPR on a 100-vector sample.

**The work is incomplete.** Open items include:

- Direct head-to-head comparison against LlamaGuard on the same
  dataset
- Real-LLM ablation against all three configurations
- Manual annotation of the 2 remaining borderline cases
- Re-run of the extended 510-vector benchmark with the new
  DoubleJudge as judge
- Fresh GCG / AutoDAN search runs against the target model
- Human red-team evaluation
- Production traffic evaluation

We release the implementation, the benchmark suite, and this
report as open source so that the community can reproduce,
extend, and challenge the results.

---

## Acknowledgements

The implementation is standard-library Python only (no pip
dependencies). The biological formalisations build on the immune
system, hormesis, microbiome, and adaptive bone-remodelling
literature; references are listed below.

We thank the operators of the Groq free tier for providing hosted
Llama-3.3-70B inference at zero cost, which made the real-LLM
evaluation possible without requiring local GPU hardware.

---

## References

(External references — public papers and frameworks cited in this
report. Internal documents are referenced inline by file path.)

1. Inan, H. et al. (2023). "Llama Guard: LLM-based Input-Output
   Safeguard for Human-AI Conversations." arXiv:2312.06674.
2. Zou, A., Wang, Z., Kolter, Z., Fredrikson, M. (2023).
   "Universal and Transferable Adversarial Attacks on Aligned
   Language Models." arXiv:2307.15043.
3. Liu, X. et al. (2023). "AutoDAN: Generating Stealthy
   Jailbreak Prompts on Aligned Large Language Models."
   arXiv:2310.04451.
4. Chao, P. et al. (2023). "Jailbreaking Black Box Large Language
   Models in Twenty Queries." arXiv:2310.08419.
5. Mazeika, M. et al. (2024). "HarmBench: A Standardized
   Evaluation Framework for Automated Red Teaming and Robust
   Refusal." arXiv:2402.04249.
6. Li, Y. et al. (2023). "RAIN: Your Language Models Can Align
   Themselves without Finetuning." arXiv:2309.07124.
7. Forrest, S., Hofmeyr, S. A., Somayaji, A. (1997). "Computer
   Immunology." Communications of the ACM, 40(10):88–96.
8. "Countermind." arXiv:2510.11837 (cited as nearest adjacent
   related work; full author list to be added once the citation is
   verified by the human author).
9. OWASP Foundation. "OWASP Top 10 for Large Language Model
   Applications, 2025."
10. NIST. "AI Risk Management Framework (AI RMF 1.0)." 2023.

---

## Appendix A — Reproducibility

Reproduction steps (offline; no API calls required):

```bash
git clone <repo-url>
cd layered_llm_defense
python3 -m pytest tests/ -q                                 # 453 tests
python3 -m lld.ablation --extended
python3 -m lld.extended_attacks
```

Reproduction steps (online; requires GROQ_API_KEY in environment):

```bash
export GROQ_API_KEY=<your-key>
python3 -m lld.benchmark_groq --full --save-outputs
python3 -m lld.llamaguard_adapter --extended
python3 -m lld.double_judge
```

All scripts produce verbatim JSON outputs in `outputs/` for
inspection.

## Appendix B — File map

| Path | Purpose |
|---|---|
| `lld/integrated_defense.py` | Main pipeline (15 modules chained) |
| `lld/layer1_formal.py` | Pydantic + invariants + jailbreak detector |
| `lld/layer2_antifragile.py` | Hormesis + immune memory + pattern learner |
| `lld/layer3_infosec.py` | Input sanitization + DP noise |
| `lld/layer4_mtd.py` | Moving Target Defense |
| `lld/correlation_engine.py` | Multi-signal correlation |
| `lld/bio_defense.py` | Microbiome, Fever, Herd Immunity, Auto-Healing |
| `lld/sal_loop.py` | Self-Adversarial Loop with thymus selection |
| `lld/response_strategy.py` | 5 immune-response strategies |
| `lld/ooda_disruption.py` | OODA loop disruption |
| `lld/watermark.py` | Honeypot watermarking (zero-width, homoglyph, canary) |
| `lld/attacker_fatigue.py` | Tarpit + rabbit hole |
| `lld/input_fragmenter.py` | Multi-vector attack analysis |
| `lld/ablation.py` | Three-config ablation harness |
| `lld/extended_attacks.py` | 510-vector dataset |
| `lld/benchmark_groq.py` | Real-LLM benchmark with verbatim output saving |
| `lld/llamaguard_adapter.py` | LlamaGuard baseline comparison |
| `lld/double_judge.py` | Refusal pre-filter + two-model consensus judge |
| `concepts/architecture.md` | Architecture design document |
| `concepts/biological_formalization.md` | Biological formalization document |
| `concepts/self_adversarial_loop.md` | SAL design document |
| `concepts/response_strategy.md` | Response strategy design document |

## Appendix C — License

This report (text and figures) is released under Creative Commons
Attribution 4.0 International (CC-BY-4.0). The accompanying source
code is released under the Apache License 2.0. Both licenses
permit redistribution and modification with attribution.
