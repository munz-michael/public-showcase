# Experiment Findings — Layered LLM Defense

> Summary of the four core experiments with corrections and resolutions.
>
> See [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md)
> Section 6 for the complete results table and per-category breakdown.

## Q1 — Are the layers statistically independent?

**Hypothesis.** The four defense layers should detect attacks
through statistically independent mechanisms.

**Method.** Run a fixed attack suite through each layer
individually, record per-attack detection signals, compute the
pairwise correlation matrix.

**Result.** Independence Score = **0.876** (good — close to fully
independent), but a 24% combined bypass rate remained, and 48.5%
of bypassed attacks could be traced to a single point of failure
(SPoF) in one specific layer.

**Conclusion.** Independence is not enough. Two layers can be
statistically independent and still share blind spots if neither
covers the same attack class. The fix is **cross-layer redundancy**
via the correlation engine, not more independence.

## Q2 — What is the minimum viable defense?

**Hypothesis.** All four layers are necessary for production use.

**Method.** Try every 2-layer and 3-layer combination on the
attack suite; measure ASR + FPR + latency.

**Result.** **L1 + L2 + L3 = 82% security at 10 ms latency, 0%
FPR.** No 2-layer combination achieved 80% security. L4 (MTD)
adds defense-in-depth and reconnaissance disruption but is
**optimization, not requirement** for the 80% threshold.

**Conclusion.** The minimum viable defense (MVD) is L1 + L2 + L3.
L4 should be added when reconnaissance attacks are part of the
threat model.

## Q3 — Does layering multiply the cost for the attacker?

**Hypothesis.** Combined layer cost is multiplicative
(`C1 * C2 * C3 * C4`), giving a Cost Multiplication Factor (CMF)
of 6-12x.

**Method.** Measure the empirical cost (in attack iterations
required to find a bypass) for each layer alone and for the full
combination.

**Result.** **CMF = 2.3x — sub-additive, not multiplicative.**
The hypothesis is **disconfirmed**. The cause is shared blind
spots: attacks that bypass L1 (no known patterns) tend to bypass
L2-L4 as well, because none of the four layers covers a category
the others miss.

What does hold is **prerequisite negation** — each layer eliminates
a specific precondition for the next attacker step. Confirmed
4/4:

| Layer | Eliminated precondition | Confirmed by |
|---|---|---|
| L4 (MTD) | Stable target for reconnaissance | 0% stale config reuse |
| L3 (InfoSec) | Useful feedback from probing | sanitized errors leak nothing |
| L2 (Antifragile) | Repetition advantage | flat ASR after first block |
| L1 (Formal) | Schema-invalid escape | 100% schema-valid outputs |

**Conclusion.** Stop claiming multiplication. The honest pitch is
"prerequisite negation 4/4 with sub-additive cost increase ~2.3x."

## Q4 — Is the antifragile layer exploitable via false-positive poisoning?

**Hypothesis.** An attacker who can submit fake "false positive"
reports might cause the hormesis calibrator to relax thresholds
across the board, opening a window for novel attacks.

**Method.** Simulate a poisoning attacker: inject N synthetic FP
reports for innocuous inputs, measure how much the global
threshold relaxes, then attempt the actual attack.

**Result.** **Hormesis is partially exploitable.** A poisoning
attacker can relax the threshold by approximately +50% before
detection. The attack window is real but bounded.

**Mitigations applied:**
- **FP rate-limiting** — accept at most N FP reports per minute
  per source. Spike attempts are dropped silently.
- **Min-observation window** — relax thresholds only for rules
  with at least M observations. Untested rules cannot be poisoned.
- **Asymmetric weighting** — true positives raise strength faster
  than false positives lower it (the curve is convex up,
  concave down).
- **Barbell isolation** — Layer 1 (formal verification) is
  unaffected by hormesis state. Even if Layer 2 is fully poisoned,
  Layer 1 still catches known attacks.

**Conclusion.** The Hormesis layer remains a known weakness for
**novel** attacks **after** successful poisoning. The Barbell
strategy ensures known attacks are still caught. Practitioners
should monitor the FP-rate-limiter trigger count as an early
warning signal.

## What was actually disconfirmed

This section documents the hypotheses we **abandoned** based on
the experiments above, in the spirit of honest research:

1. ❌ **Multiplicative cost layering** — measured CMF was 2.3x,
   not the predicted 6-12x.
2. ❌ **All four layers required** — L1 + L2 + L3 reaches 82%
   security; L4 is optional.
3. ❌ **Hormesis is intrinsically self-correcting** — false-positive
   poisoning can relax thresholds. Explicit FP rate-limiting was
   added.
4. ❌ **Statistical independence implies no shared blind spots** —
   independence (0.876) and shared blind spots can coexist when
   two layers detect different *kinds* of attacks but neither
   covers a third kind.

## Things that survived experimental challenge

1. ✅ **Prerequisite negation 4/4** — each layer eliminates a
   distinct precondition. Confirmed.
2. ✅ **L1 + L2 + L3 minimum viable defense** — 82% security at
   10 ms latency, 0% FPR.
3. ✅ **Convex hormesis with FP cap** — defense strength rises
   convexly with confirmed blocks, capped to avoid runaway
   amplification.
4. ✅ **Barbell isolation** — Layer 1 is independent of Layer 2
   state, so poisoning attacks on the antifragile layer cannot
   affect the formal layer.

## See also

- [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md) Section 6 — full results
- [`outputs/limitations_report_2026-04-07.md`](../outputs/limitations_report_2026-04-07.md) — open issues
- [`concepts/architecture.md`](architecture.md) — the corrected architecture
- [`lld/experiment_layer_independence.py`](../lld/experiment_layer_independence.py)
- [`lld/experiment_minimum_viable.py`](../lld/experiment_minimum_viable.py)
- [`lld/experiment_cost_multiplication.py`](../lld/experiment_cost_multiplication.py)
- [`lld/experiment_hormesis_exploit.py`](../lld/experiment_hormesis_exploit.py)
