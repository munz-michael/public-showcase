# Blind Watchdog Protocol — Anonymous Mutual Oversight for Autonomous Multi-Agent Systems

> Who watches the watchers? Everyone — but no one knows who watches whom.

The Blind Watchdog Protocol (BWP) constructs a directed oversight graph where each autonomous agent has exactly one hidden watchdog, but no agent knows the identity of its watcher. Compliance emerges from the mere possibility of observation — a Panopticon equilibrium — without centralized authority, known reviewers, or self-enforcement.

## The Problem

As AI agents gain autonomy, oversight becomes critical. Three approaches exist, each with a structural flaw:

| Approach | Flaw |
|----------|------|
| Centralized monitoring (RLHF, Constitutional AI) | Single point of failure, trust bottleneck |
| Peer monitoring (multi-agent debate) | Known reviewers can be gamed or colluded against |
| Self-enforcement (guardrails) | "The tool stopped itself" is weaker than "the system stopped it" |

BWP introduces a fourth approach: **anonymous mutual oversight** where compliance is structurally enforced.

## Core Properties

| Property | How |
|----------|-----|
| **Anonymous** | Watchdog identity hidden via ZKP commitments + mixnet |
| **Mutual** | Every agent is both watcher and watched (directed graph, in-degree = out-degree = 1) |
| **Decentralized** | No central monitor; topology via multi-party computation |
| **Nash-stable** | Compliance is a strict Nash equilibrium (closed-form proof, not simulation) |

## Results

Across 1,000 simulation runs (500 agents, 50 ticks, 10% defectors):

| Metric | Value |
|--------|-------|
| Detection rate | **100%** |
| False positive rate | **0%** |
| Mean detection time | ~7 ticks |
| Scale | 500 agents in <10 seconds |
| Adversarial strategies tested | 6 (all mitigated) |

## Nash Equilibrium Theorem

Compliance is a strict Nash equilibrium iff:

```
b_v < b_c * T / T_term + c_d * p_d + c_t / T_term
```

Under default parameters: critical benefit = 13.57, actual violation benefit = 2.0. **Nash holds with margin 11.57.** Formal 6-step proof, not parameter sweep.

## Architecture

```
+--------------------------------------------------+
|           Blind Watchdog Protocol v1.0            |
|    run_protocol() . escalate() . observe()       |
+------+-------+--------+--------+--------+--------+
| Graph| Crypto | Agent  | Proto- | Game   | Simula-|
|      |        |        | col    | Theory | tion   |
+------+-------+--------+--------+--------+--------+
|           8 Composable Plugins                    |
| Reputation | Staking | Mixnet | Rotation |        |
| Correlat.  | Adapt-K | Convic.| Know.Gate|        |
+--------------------------------------------------+
```

## Biological Foundations

10 biological oversight mechanisms mapped 1:1 to executable code:

| Biological System | BWP Mechanism |
|-------------------|---------------|
| Worker Policing (Apis mellifera) | Watchdog graph + derangement |
| Complement Cascade | 5-level escalation |
| MHC Antigen Presentation | ZKP watchdog commitments |
| Quorum Sensing (V. fischeri) | k-of-n consensus |
| Audience Effect | Fog of War equilibrium |
| Apoptosis | Level 4 termination |
| Autoimmunity Prevention | No fixpoints (derangement) |
| Immunological Memory | Reputation score + decay |
| Thymus Selection | MPC trusted setup |
| Clonal Expansion | Adaptive watcher count |

## Threat Model

11 attack vectors analyzed, 6 adversarial strategies tested (threshold riding, intermittent defection, gradual degradation, watcher probing, budget draining, collusion with deduction):

- 10/11 vectors mitigated (including Sybil via 3-tier identity and traffic analysis via constant-rate dummy traffic)
- Known limit: Nash breaks above ~30% coordinated colluders (Byzantine fault tolerance ceiling, Lamport 1982)

## Layered Defense

BWP separates immediate containment from delayed adjudication:

| Layer | Speed | Action |
|-------|-------|--------|
| Escalation L1-L3 | **Immediate** | Warning → Restricted → Suspended |
| Escalation L4 | Delayed (challenge period) | Terminated + Optimistic Slashing |

A suspended agent cannot act — damage stops immediately. Optimistic Slashing resolves the economic question (stake confiscation) without time pressure.

## Limitations

1. **Simulation-only.** Not deployed in production agent networks.
2. **Assessment model dependency + monoculture risk.** Detection quality depends on observation model. Model diversity enforcement mitigates correlated failures (5 tests).
3. **Sybil resistance via three-tier identity.** Economic (admission staking) + cryptographic (DID) + structural (Proof-of-Personhood). Economic is default; DID/PoP require external providers.
4. **TLA+ model-checked (PASSED).** TLC verified NashInvariant: 2,071 states, zero violations. Bounded check (default parameters only).
5. **Single-author project.** 5,757 LOC + 422 tests.

## Status

v1.0.0 — 422 tests. 10 composable plugins. Nash equilibrium theorem (closed-form, TLC model-checked). 10 biological analogies. Distributed prototype. Integrated with TRE (24 tests passing). Stress-tested: stochastic observation, collusion sweep, Dark DAO economics, latency profiling.

## Paper

See [paper/blind_watchdog_protocol_paper.md](paper/blind_watchdog_protocol_paper.md) for the full working paper with formal proofs, threat model, and benchmarks.

## Related Work

- [Knowledge Fingerprint (KFP)](https://doi.org/10.5281/zenodo.19519682) — provides epistemic fitness gating for BWP's KnowledgeGatePlugin (DOI: 10.5281/zenodo.19519682)
- [Knowledge OS (KOS)](https://doi.org/10.5281/zenodo.19629734) — uses BWP for agent control in the 7-dimension trust layer (DOI: 10.5281/zenodo.19629734)

## License

[PolyForm Noncommercial 1.0](LICENSE)

## A Note on Process

This system and paper were developed with significant AI assistance. AI coding tools were used as collaborative development aids. Human judgment guided all design decisions and validated all results against code.
