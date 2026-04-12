# Lean Multi-Provider Debate Framework

Multi-agent debate system that pits two heterogeneous AI providers (Google Gemini and Anthropic Claude) against each other to produce calibrated, adversarially-vetted answers.

> **Paper:** [Lean Multi-Provider Debate: Heterogeneous AI Discourse Engine](./paper/debate_paper.pdf)

## Problem

Single-provider AI systems are susceptible to sycophancy — the tendency to agree with the user rather than provide accurate answers. Homogeneous multi-agent setups (Claude × Claude) inherit shared training biases. LMAD uses cross-provider debate to surface genuine disagreements.

## Architecture

```
Problem ──▶ Phase 0: Decomposition (optional)
               │
               ▼
         Phase 1: Independent Analysis (Gemini A + Gemini B)
               │
               ▼
         Phase 1.5: Fact-Check (claim-level verification)
               │
               ▼
         Phase 2: Claude Critique + Verification
               │
               ▼
         Phase 3: Consensus Synthesis
               │
               ▼
         Phase 4: Independent Judge (skeptical review)
```

Key features:
- **Cross-provider debate** — Gemini vs Claude to minimize shared biases
- **Delphi iterative refinement** — multi-round convergence
- **Argument graph construction** — formal argument structure
- **Probabilistic calibration tracking** — confidence over time
- **Sycophancy benchmark** — empirical comparison of heterogeneous vs homogeneous setups

## Key Results

Sycophancy comparison (heterogeneous Gemini×Claude vs homogeneous Claude×Claude):
- Lower `echo_score` (TF-cosine similarity) in cross-provider setup
- Higher `n_contradictions` — genuine disagreements surfaced
- Lower `cross_answer_similarity` — independent reasoning confirmed

## Citation

```bibtex
@techreport{munz2026debate,
  title  = {Lean Multi-Provider Debate: Heterogeneous AI Discourse Engine},
  author = {Munz, Michael},
  year   = {2026}
}
```

## A Note on Process and Transparency

This project was developed with AI coding assistance. Architecture, research questions, and interpretation of results are human contributions. See the [repository-level transparency note](../README.md#transparency) for details.

## License

PolyForm Noncommercial 1.0

## Author

Michael Munz
