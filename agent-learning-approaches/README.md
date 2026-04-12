# Agent Learning Approaches — How AI Agents Learn

> A practitioner's taxonomy, decision framework, and empirical benchmark comparing seven agent learning strategies across 14 tasks.

## The Problem

AI agents need to learn from experience across sessions. But which learning approach should you choose? The landscape is fragmented: file-based memory, RAG, fine-tuning, reinforcement learning — each community advocates its own approach without systematic comparison.

## What This Project Provides

1. **Taxonomy** — 20 agent learning paradigms organized into 5 categories (Weight-Based, Context-Based, Hybrid, Structural, Meta)
2. **Decision Framework** — 9x7 trade-off matrix + decision tree for practitioners
3. **Benchmark** — 7 strategies, 14 tasks, deterministic and reproducible
4. **Ablation Study** — Component-level analysis of CLL improvements
5. **Failure Analysis** — Not just who wins, but why others fail
6. **Statistical Validation** — Multi-seed reproducibility, Cohen's h effect sizes, sensitivity analysis

> **Paper:** [How AI Agents Learn: Taxonomy and Empirical Comparison](./how_ai_agents_learn_taxonomy_and_empirical_comparison.md)

## Key Results

| Strategy | Avg Final Score | Tasks Won | State Size |
|----------|----------------|-----------|------------|
| **CLL** | **0.953** | **6/8** | 490 B |
| CLL+RAG | 0.941 | 1/8 | 7.2 KB |
| **Debate** | **0.925** | **0/14** | 8.1 KB |
| Reflexion | 0.875 | 1/8 | 0 B |
| RAG | 0.870 | 0/8 | 6.8 KB |
| ICL | 0.650 | 0/8 | 350 B |

**CLL** (file-based institutional memory) dominates on stable patterns. **RAG** wins only at 50+ rules. **Debate** wins no single task but is the most robust allrounder — never worse than #4. Real LLM validation with Claude Haiku confirmed rankings for 4 cents (150 API calls).

## Decision Tree

```
Need persistent learning across sessions?
├─ NO → ICL or Reflexion
└─ YES ↓
   Have access to model weights?
   ├─ NO (API-only)
   │  ├─ Few core rules (<50) → CLL
   │  ├─ Large knowledge corpus → RAG
   │  ├─ Both → CLL + RAG
   │  └─ Executable skills → Voyager
   └─ YES ↓
      Privacy/Auditability critical?
      ├─ YES → CLL, optionally CLL + local RAG
      └─ NO → Fine-Tuning or RAFT
```

## Citation

```bibtex
@techreport{munz2026ala,
  title  = {How AI Agents Learn: A Taxonomy and Empirical Comparison
            of Agent Learning Strategies},
  author = {Munz, Michael},
  year   = {2026}
}
```

## A Note on Process and Transparency

This project was developed with AI coding assistance. Architecture, research questions, and interpretation of results are human contributions. The author takes full responsibility for all claims and conclusions presented.

## License

PolyForm Noncommercial 1.0
