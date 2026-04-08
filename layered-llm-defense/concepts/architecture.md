# Architecture — Layered LLM Defense

> The four-layer defense-in-depth architecture for LLM security.
> The complete formal description is in
> [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md),
> Section 3 (Architecture).

## 1. Design principles

### 1.1 Cost increase through layering

The original hypothesis was that combined cost would scale
multiplicatively (`C1 * C2 * C3 * C4`). Empirical measurement
disconfirmed this:

```
Measured CMF (Cost Multiplication Factor):  ~2.3x   (sub-additive)
Expected CMF if additive:                    6.2x
Expected CMF if multiplicative:             11.8x
```

The cause is shared blind spots: attacks that bypass Layer 1 (no
known patterns) tend to bypass Layers 2-4 as well. Layers are
independent in their detection logic (Independence Score 0.876),
but their coverage does not overlap enough for true cost
multiplication.

### 1.2 Prerequisite negation (the actually load-bearing claim)

What does hold is **prerequisite negation** — each layer eliminates
a specific precondition required by the next attacker step:

| Layer | Eliminated precondition | Confirmed by |
|---|---|---|
| L4 (MTD) | Stable target for reconnaissance | 0% stale config reuse across rotations |
| L3 (Information-theoretic) | Useful feedback from probing | sanitized errors leak no model state |
| L2 (Antifragile) | Repetition advantage | flat ASR trend after first block |
| L1 (Formal) | Schema-invalid escape | 100% of allowed outputs schema-valid |

This is the **honest claim**:

```
CMF_real ≈ 2-3x (sub-additive, with potential for more via
                 redundancy increase)
Prerequisite-negation: 4/4 confirmed (per-layer guarantees hold)
```

### 1.3 Biological architectural primitives

| Biological model | Security mapping | Layer |
|---|---|---|
| Immune system (primary/secondary) | First detection slow, known patterns blocked instantly | L2 |
| Hormesis curve | Aggressive filters cause autoimmunity (FPs); optimal dose required | L2 |
| Wolff's Law | Security rules harden context-specifically, not globally | L2 |
| Barbell strategy | 90% conservative core (formally proven) + 10% exploratory heuristics | L1 + L2 |
| Gut microbiome diversity | Multiple models / strategies confer resilience to domain shift | L4 |
| Physarum networks | Reinforce successful defense paths; explore new ones | L2 + L4 |

See [`concepts/biological_formalization.md`](biological_formalization.md)
for the formal mathematical models and Python sketches.

## 2. Layer pipeline

```
                ┌─── Incoming Request ───┐
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L4: MOVING TARGET DEFENSE          │  │
│  Endpoint, model, prompt rotation   │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L3: INFORMATION-THEORETIC LAYER    │  │
│  Input sanitization, error masking  │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L2: ANTIFRAGILE SHELL              │  │
│  Immune memory, pattern learner,    │  │
│  hormesis-calibrated rules          │  │
└─────────────────────────────────────┘  │
                │                         │
                ▼                         │
┌─────────────────────────────────────┐  │
│  L1: PROVEN CORE                    │  │
│  Pydantic schemas, invariant        │  │
│  monitor, jailbreak detector        │  │
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

## 3. Failure modes considered

| Failure mode | Mitigation |
|---|---|
| Antifragile vs. false positives | Hormesis cap + calibration damping |
| Biological metaphors as window dressing | Each model has a formal mathematical contract; see `biological_formalization.md` |
| MTD attack-surface explosion | Bounded number of rotation states; ablation shows MTD adds <0.1ms latency |
| Layer-2 immune memory poisoning | FP rate-limiting + barbell isolation (formal layer is unaffected by L2 state) |
| Single point of failure between layers | Correlation engine combines signals across layers using independent-failure model |

## See also

- [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md) — full architecture description
- [`concepts/biological_formalization.md`](biological_formalization.md) — formal biological models
- [`concepts/self_adversarial_loop.md`](self_adversarial_loop.md) — self-hardening loop
- [`concepts/response_strategy.md`](response_strategy.md) — five immune response types
- [`concepts/metrics.md`](metrics.md) — defense quality metrics
- [`concepts/experiment_findings.md`](experiment_findings.md) — what we measured and what was disconfirmed
