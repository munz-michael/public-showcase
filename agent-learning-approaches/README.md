# Agent Learning Approaches — How AI Agents Learn

> A practitioner's taxonomy, decision framework, and empirical benchmark comparing seven agent learning strategies across 14 tasks.

## The Problem

AI agents need to learn from experience across sessions. But which learning approach should you choose? The landscape is fragmented: file-based memory, RAG, fine-tuning, reinforcement learning — each community advocates its own approach without systematic comparison.

## What This Project Provides

1. **Taxonomy** — 20 agent learning paradigms organized into 5 categories (Weight-Based, Context-Based, Hybrid, Structural, Meta)
2. **Decision Framework** — 9×7 trade-off matrix + decision tree for practitioners
3. **Benchmark** — 7 strategies, 14 tasks, deterministic and reproducible
4. **Ablation Study** — Component-level analysis of CLL improvements
5. **Failure Analysis** — Not just who wins, but why others fail
6. **Statistical Validation** — Multi-seed reproducibility, Cohen's h effect sizes, sensitivity analysis

## Key Results

| Strategy | Avg Final Score | Tasks Won | State Size |
|----------|----------------|-----------|------------|
| **CLL** | **0.953** | **6/8** | 490 B |
| CLL+RAG | 0.941 | 1/8 | 7.2 KB |
| **Debate** | **0.925** | **0/14** | 8.1 KB |
| Reflexion | 0.875 | 1/8 | 0 B |
| RAG | 0.870 | 0/8 | 6.8 KB |
| ICL | 0.650 | 0/8 | 350 B |

**CLL** (file-based institutional memory) dominates on stable patterns. **RAG** wins only at 50+ rules and shows advantage on coding-agent tasks (code_review, error_triage) where large example corpora matter. **Reflexion** wins at pattern shifts. **CLL+RAG** is optimal at scale (500 rules). **Debate** (dual-agent CLL+RAG with trust model) wins no single task but is the **most robust allrounder** — never worse than #4, often #2-3 across all task types. **SimLLM** validates that strategy rankings hold even with simulated LLM overhead (noise, latency) — no API key needed for full reproducibility. **Real LLM validation** with Claude Haiku confirmed rankings for 4 cents (150 API calls). Multi-seed analysis confirms sigma=0.000 on 4/7 tasks; Cohen's h effect sizes quantify differences (e.g., CLL vs ICL: h=0.85, large effect).

## Quick Start

```bash
cd research/agent_learning_approaches

# Run full benchmark
python -m poc benchmark

# Overall ranking
python -m poc compare

# Failure analysis
python -m poc analyze

# Ablation study (CLL variants)
python -m poc ablation

# Noise robustness analysis
python -m poc noise

# Parameter sensitivity analysis (28 configurations)
python -m poc sensitivity

# List available tasks and strategies
python -m poc tasks
python -m poc strategies

# Run specific task
python -m poc benchmark --task adaptive_scoring --steps 200

# Run tests (181 tests)
python -m pytest poc/tests/ -v

# LLM validation (requires ANTHROPIC_API_KEY in .env, see .env.example)
python -m poc validate
```

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

## Ablation: What Makes CLL v2 Better

| Component | Where it helps | Delta |
|-----------|---------------|-------|
| Drift Detection | Pattern shifts (adaptive_scoring) | +0.075→+0.150 |
| Sequence Rules | Temporal patterns (sequence_learning) | +0.225 |
| Majority Vote | Noisy/contradictory data | +0.075 |

All three improvements are **orthogonal** — each addresses a different failure mode, none degrades stable-pattern performance.

## Architecture

```
poc/
├── __main__.py           # CLI interface (benchmark, compare, analyze, ablation, noise, sensitivity, tasks, strategies)
├── strategies/           # 7 learning strategies with shared interface
│   ├── base.py           # LearningStrategy ABC, Observation, Prediction, StrategyMetrics
│   ├── cll.py            # Compound Learning Loop + DriftDetector
│   ├── rag.py            # Retrieval-Augmented Generation
│   ├── reflexion.py      # Verbal Self-Critique (Reflexion)
│   ├── icl.py            # In-Context Learning (few-shot)
│   ├── hybrid_cll_rag.py # CLL + RAG hybrid
│   ├── simulated_llm.py  # SimLLM — simulated LLM overhead for API-free validation
│   └── debate.py          # Multi-Agent Debate (dual CLL+RAG with trust model)
├── benchmark/
│   ├── tasks.py          # 14 benchmark tasks (8 core + 4 generative + 2 external)
│   ├── runner.py         # Strategy x Task runner
│   ├── metrics.py        # Scoring + comparison
│   ├── failure_analysis.py  # WHY strategies fail (confusion matrix, temporal clusters)
│   ├── multi_seed.py     # Multi-seed reproducibility (sigma per task)
│   ├── sensitivity.py    # Parameter sensitivity analysis (28 configurations)
│   ├── noise.py          # Noise robustness tests
│   └── statistics.py     # Cohen's h effect sizes + statistical significance
├── tests/                # 181 tests (13 test files)
├── results/              # Benchmark reports + raw data + figures
│   ├── benchmark_report.md
│   ├── ablation_study.md
│   ├── failure_analysis.md
│   ├── sensitivity_analysis.md
│   ├── significance_report.md
│   ├── multi_seed_report.md
│   └── figures/          # Paper figures (heatmap, convergence, ablation)
└── run_benchmark.py      # Legacy CLI
```

## Benchmark Tasks (14 Tasks)

| Task | Steps | Type | Tests |
|------|-------|------|-------|
| category_scoring | 200 | Core | Basic pattern recognition |
| adaptive_scoring | 200 | Core | Pattern shift at midpoint |
| noisy_scoring | 200 | Core | 10% label noise |
| multifeature_scoring | 200 | Core | Multi-feature rules |
| sequence_learning | 200 | Core | Temporal context |
| scaling_stress | 200 | Core | 50 unique rules |
| extreme_scaling | 1000 | Core | 500 unique rules |
| contradictory | 200 | Core | 60/40 label conflict |
| code_pattern_learning | 200 | Coding | Code pattern recognition (RAG advantage) |
| api_usage_learning | 200 | Coding | API usage patterns (RAG advantage) |
| generative_* (4 tasks) | 200 | Generative | Open-ended generation tasks |
| iris_classification | 200 | External | Real-world Iris dataset |
| sentiment_classification | 200 | External | Sentiment analysis |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ (stdlib only, no external deps) |
| Testing | pytest (181 tests, 13 test files) |
| LOC | ~5,265 lines across 7 strategies, 14 tasks, 8 benchmark modules |
| Metrics | Custom StrategyMetrics (convergence, drift, state size) |
| Statistics | Cohen's h effect sizes, McNemar's test, multi-seed sigma |
| Analysis | FailureTracker (confusion matrix, temporal clusters) |
| Visualization | matplotlib/seaborn (optional) |

## Paper

See [how_ai_agents_learn_taxonomy_and_empirical_comparison.md](how_ai_agents_learn_taxonomy_and_empirical_comparison.md) for the full research paper (529 lines) with taxonomy, decision framework, results, ablation study, LLM validation (Appendix D), related work, and 16 references.

## A Note on Process and Transparency

This project was developed with AI coding assistance. Architecture, research questions, and interpretation of results are human contributions. The author takes full responsibility for all claims and conclusions presented.
