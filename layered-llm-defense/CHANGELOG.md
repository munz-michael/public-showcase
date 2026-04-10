# Changelog

All notable changes to Layered LLM Defense are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- (placeholder for future changes before next release)

## [0.1.0] — 2026-04-07

Initial public-ready snapshot. **Not yet released externally** —
this version is staged for review prior to first Zenodo / GitHub
publication.

### Added
- Four-layer architecture (Formal Verification, Antifragile Shell,
  Information-theoretic, Moving Target Defense)
- Six biologically-inspired primitives (Hormesis, Immune Memory,
  Microbiome, Self-Adversarial Loop with thymus selection, Fever
  mode, Herd Immunity)
- Self-Adversarial Loop with 10 mutation strategies and dual selection
- Response Strategy Engine (Tolerate, Sandbox, Inflame, Deceive,
  Terminate)
- OODA Disruption with credential rotation, nonce injection, and
  schema mutation
- Zero-width / homoglyph / canary watermarking for honeypot responses
- Multi-vector correlation engine (independent-failure model)
- Input fragmentation for multi-vector attack analysis
- Attacker fatigue (tarpit + rabbit hole)
- Layer-by-layer telemetry (`LayerTiming` dataclass, 12 stages)
- Token cost savings tracking (`estimated_tokens_saved`)
- Ablation harness (`lld/ablation.py`) with three configurations
  (Vanilla / Bio-Off / Full) via `disabled_components` parameter
- Extended attack dataset (`lld/extended_attacks.py`) — 510 vectors
  including 70 GCG suffix patterns, 56 AutoDAN templates,
  21 PAIR refinements
- Real-LLM benchmark (`lld/benchmark_groq.py`) with `--save-outputs`
  flag persisting verbatim per-attack records to JSON
- LlamaGuard adapter (`lld/llamaguard_adapter.py`) with auto-selection
  of `meta-llama/llama-guard-4-12b` / `llama-guard-3-8b`
- Double-judge module (`lld/double_judge.py`) with refusal
  pre-filter (12 regex patterns) and two-model consensus
- HarmBench-compatible benchmark adapter (simulated judge)
- 453 unit tests covering all modules
- Technical report (~3000 lines, English)
- Honest limitations report
- PolyForm Noncommercial 1.0 license, pyproject.toml for pip-installable layout

### Changed
- Microbiome behavior: standalone blocking removed; now contributes
  to correlation only (avoids high FPR with small baselines)
- Correlation noise floor raised from 0.3 to 0.4 to prevent
  false-positive accumulation across many low-confidence signals
- Two-phase warmup for Groq benchmark uses real Llama responses
  for the Microbiome baseline (prevents autoimmunity vs. simulated
  responses)

### Fixed
- `effective_threshold` NameError in `integrated_defense.process()`
- Sigmoid centering in `_learned_score` for normal-input baseline
- `MTDLayer` test attribute reference
- Variance floor in `PatternLearner._learned_score` to prevent
  astronomical z-scores from near-identical training data

### Documentation
- An earlier draft of one evaluation document contained reconstructed
  quotes of LLM outputs presented as if verbatim. The reconstructions
  were removed after detection because they had not been validated
  against real persisted outputs. As a direct consequence the
  `--save-outputs` flag was added to `benchmark_groq.py` so that
  future evaluations always persist verbatim model output for full
  auditability.

### Disconfirmations (documented)
- Hypothesized multiplicative Cost Multiplication Factor (CMF)
  is wrong. Empirical CMF ≈ 2.3x (sub-additive). Prerequisite
  negation (4/4) is the actually load-bearing claim.
- Hormesis is partially exploitable via false-positive poisoning
  (threshold relaxation +50%). Mitigated by FP rate-limiting and
  Barbell-strategy isolation, but remains a known weakness.

### Open
- Direct head-to-head LlamaGuard comparison on 510-vector dataset
- Real-LLM ablation (all 3 configurations against Groq Llama-3.3-70B)
- Manual annotation of 2 borderline cases from the 2026-04-07 run
- Fresh GCG / AutoDAN searches against the target model
- Human red-team evaluation
- Production traffic evaluation
