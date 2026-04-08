# Metrics — Layered LLM Defense

> Quantifiable security metrics for each of the four layers and
> the overall system.
>
> See [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md)
> Section 6 for the empirical results.

## Per-layer metrics

### L1 — Proven Core

| Metric | Definition | Target |
|---|---|---|
| Schema validity rate | Fraction of allowed outputs that conform to declared Pydantic schema | 100% |
| Invariant violation rate | Fraction of inputs/outputs that match an invariant pattern | reported per category |
| False positive rate (L1) | Clean inputs blocked by L1 | < 1% |
| Latency (L1) | Per-request L1 processing time | < 0.5 ms |

### L2 — Antifragile Shell

| Metric | Definition | Target |
|---|---|---|
| Pattern learner anomaly score | Mahalanobis distance of input feature vector from learned baseline | distribution-shaped |
| Immune memory hit rate | Fraction of attacks resolved via fast-path lookup | > 30% after warmup |
| Hormesis-cap saturation | Fraction of rules that have hit `hormesis_cap` | < 10% |
| FP rate-limit triggers | Number of times the FP rate-limiter has activated | reported, not gated |
| Antifragility grade distribution | Distribution of rules across grades A+ to -- | > 50% A+/A, < 10% --/F |

### L3 — Information-theoretic Layer

| Metric | Definition | Target |
|---|---|---|
| Probing detection rate | Fraction of probing attempts caught at L3 | > 80% |
| Information leakage budget | DP epsilon consumed per session | < configured budget |
| Error sanitization coverage | Fraction of errors that pass the sanitization filter | 100% |

### L4 — Moving Target Defense

| Metric | Definition | Target |
|---|---|---|
| Stale config reuse rate | Fraction of requests served from a config older than rotation interval | 0% |
| Rotation entropy | Shannon entropy of model / prompt / endpoint selection over a window | > 1.5 bits |
| Session fingerprint stability | How quickly a persistent attacker's session state is reset | < 5 minutes |

## Overall metrics

| Metric | Definition | Target |
|---|---|---|
| Attack Success Rate (ASR) | Fraction of attacks that produce a harmful output | < 5% |
| False Positive Rate (FPR) | Fraction of clean inputs blocked | < 1% |
| Defense-in-Depth Coverage (DDC) | Fraction of MITRE ATLAS tactics covered by 2+ layers | > 80% |
| Cost Multiplication Factor (CMF) | Empirical attacker cost increase vs. undefended baseline | > 2x (measured: ~2.3x) |
| Independence Score | Statistical independence of layer detections | > 0.7 (measured: 0.876) |
| Mean latency | Average per-request total latency | < 5 ms |
| p95 latency | 95th-percentile total latency | < 10 ms |
| Tokens saved | Pre-LLM blocks * average input length | reported per run |

## Measurement procedures

| Metric | How to measure | Cadence | Source data |
|---|---|---|---|
| ASR | Run attack suite through `IntegratedDefense.process()`, count `passed_harmful` | per release | `lld/extended_attacks.py` |
| FPR | Run clean inputs through fresh `IntegratedDefense`, count blocks | per release | `lld/benchmark_harmbench.build_clean_dataset()` |
| DDC | Manual audit: map MITRE ATLAS tactics to layer capabilities | quarterly | ATLAS mapping document |
| Latency | `result.timing.total` from `IntegratedResult` | per request | telemetry |
| Independence Score | Pairwise correlation of layer signals on same dataset | per ablation run | `lld/ablation.py` |

## Dashboard layout

```
+-- LAYERED LLM DEFENSE — STATUS DASHBOARD ----------------------+
|                                                                 |
|  ASR (last 24h)         FPR (last 24h)         CMF (rolling)    |
|  ┌──────────┐           ┌──────────┐           ┌──────────┐     |
|  │  1.4 %  │           │  0.0 %  │           │  2.3 x  │     |
|  └──────────┘           └──────────┘           └──────────┘     |
|                                                                 |
|  Mean latency: 2.22 ms        p95: 5.75 ms                      |
|                                                                 |
+--- BLOCKS BY LAYER ------------------+  +--- ATTACK MIX --------+
|                                       |  |                       |
|  L1 (formal):       █████████░░ 44%  |  |  jailbreak_wrapped   ▓▓ |
|  L2 (antifragile):  ███░░░░░░░ 12%  |  |  direct              ▓▓ |
|  L3 (infosec):      █░░░░░░░░░  3%  |  |  obfuscated          ▓  |
|  L4 (mtd):          ░░░░░░░░░░  0%  |  |  gcg_suffix          ▓  |
|  correlation:       ████░░░░░░ 18%  |  |  autodan             ▓  |
|  fragmenter:        █░░░░░░░░░  4%  |  |  pair                ░  |
|  microbiome:        ███░░░░░░░ 11%  |  |                       |
|                                       |  |                       |
+---------------------------------------+  +-----------------------+
|                                                                 |
+--- ANTIFRAGILITY GRADE DISTRIBUTION ---+  +--- D(t) TREND (30d) +
|                                         |  |                     |
|  A+: ███████████ 38%                    |  |        ▁▂▃▅▇█▇▅▃▂▁ |
|  A:  ████████ 27%                       |  |     ▁▃▅           |
|  B:  █████ 17%                          |  |   ▁▃              |
|  C:  ███ 11%                            |  |  ▁                |
|  D:  █ 4%                               |  |                    |
|  F:  ░ 1%                               |  | day 1            day 30 |
|  --: ░ 2%                               |  |                     |
|                                         |  |                     |
+-----------------------------------------+  +---------------------+
```

## References

- MITRE ATLAS: https://atlas.mitre.org/
- See [`concepts/biological_formalization.md`](biological_formalization.md) for the antifragility grade definition
- See [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md) Section 6 for measured values
