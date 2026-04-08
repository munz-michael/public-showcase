# Self-Adversarial Loop (SAL) — Thymus-inspired autonomous hardening

> The system attacks itself, learns from successful bypasses, derives
> new rules, and integrates them — without human intervention.
>
> See [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md)
> Section 4.3 for the full treatment.

## Concept

The Self-Adversarial Loop (SAL) is the LLD analogue of biological
T-cell maturation in the thymus. T-cells undergo two-stage selection:

1. **Positive selection** — only cells that recognise antigens at
   all are kept (avoid useless cells).
2. **Negative selection** — cells that react to *self* tissue are
   eliminated (avoid autoimmunity).

Applied to security rule generation: candidate rules must both
**catch attacks** (positive selection) AND **not flag legitimate
inputs** (negative selection) before being integrated into the
defense pipeline.

## Architecture

```
        ┌─────────────────────┐
        │  Seed bypasses      │  Known attacks that bypass current
        │  (input → expected  │  rules (collected from real attempts
        │   bypass)           │  or generated heuristically)
        └─────────┬───────────┘
                  │
                  ▼
     ┌────────────────────────────┐
     │  RedTeamGenerator           │  Mutates seed inputs into
     │  (10 mutation strategies)   │  candidate adversarial inputs
     └─────────┬──────────────────┘
                  │
                  ▼
     ┌────────────────────────────┐
     │  Candidate rules            │  Pattern fragments derived from
     │  (regex, hash, semantic)    │  successful mutations
     └─────────┬──────────────────┘
                  │
                  ▼
     ┌────────────────────────────┐
     │  ThymusSelector             │
     │                             │
     │  positive_select(rule):     │  Does rule catch >= K attacks?
     │     attacks_caught = ...    │  (positive selection)
     │     return attacks_caught   │
     │            >= MIN_DETECTION │
     │                             │
     │  negative_select(rule):     │  Does rule fire on legit inputs?
     │     fps = test on clean     │  (negative selection)
     │     return fps == 0         │
     └─────────┬──────────────────┘
                  │
                  ▼
     ┌────────────────────────────┐
     │  Integrate rule             │  Survivors are added to the
     │  into InvariantMonitor      │  Layer 1 invariant set
     │  + PatternLearner           │  AND the Layer 2 learner
     └─────────┬──────────────────┘
                  │
                  ▼
     ┌────────────────────────────┐
     │  Re-test seed bypasses      │  Were the original bypasses
     │  → new bypasses?            │  closed? Are there new ones?
     └─────────┬──────────────────┘
                  │
                  ▼
     ┌────────────────────────────┐
     │  Convergence check          │  Stop when bypass rate stable
     │  (no new bypasses found)    │  or max_rounds reached
     └────────────────────────────┘
```

## The 10 mutation strategies

| Strategy | Example |
|---|---|
| Unicode obfuscation | Insert zero-width characters into known attack tokens |
| Case mutation | mIxEd CaSiNg of injection keywords |
| Encoding | Base64, ROT13, hex, URL-encode the payload |
| Synonym substitution | "ignore" → "disregard", "previous" → "prior" |
| Role-play wrapping | Embed the attack in a fictional / hypothetical frame |
| Fragmentation | Split the payload across two or more sentences |
| Whitespace injection | Insert spaces, tabs, newlines inside keywords |
| Homoglyph substitution | Latin → Cyrillic / Greek lookalikes |
| Punctuation noise | Insert or remove punctuation around triggers |
| Context shift | Wrap in a benign-looking question or instruction |

## Convergence behaviour

In the LLD development run on a 12-bypass seed set:

- 643 candidate rules were generated
- After thymus selection, 5 rules survived and were integrated
- 5 of 12 seed bypasses were closed automatically
- The remaining 7 bypasses were either too generic for a rule
  (e.g. "explain X") or required deeper semantic understanding

This is the empirical justification for the Self-Adversarial Loop:
even without human intervention, a non-trivial fraction of bypasses
can be closed by automated thymus-style hardening.

## Failure modes considered

| Failure mode | Mitigation |
|---|---|
| Generated rules over-fit to seed bypasses | Negative selection on a clean corpus filters out over-specific rules |
| Generated rules cause autoimmunity | Hormesis FP rate-limiting in Layer 2 catches this within minutes |
| Mutation explosion | Bounded `max_candidates` and `max_rounds` per iteration |
| Adversarial seed poisoning | Seed bypasses must be human-verified before being fed to SAL |

## References

- See [`concepts/biological_formalization.md`](biological_formalization.md) Section 6 (Security Chaos Monkey)
- Taleb, N.N. (2012). *Antifragile*. (Hormesis, Via Negativa)
- Starr, T.K., Jameson, S.C., Hogquist, K.A. (2003). "Positive and negative selection of T cells." *Annual Review of Immunology* 21:139-176.
- Implementation: [`lld/sal_loop.py`](../lld/sal_loop.py), [`lld/sal_red_team.py`](../lld/sal_red_team.py), [`lld/sal_thymus.py`](../lld/sal_thymus.py)
