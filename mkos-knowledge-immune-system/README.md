# MKOS — Mycelial Knowledge Operating System

Automated quality management for knowledge bases using a two-phase detection pipeline inspired by biological immune systems. Detects hallucinations, staleness, bias, and contradictions in unstructured text.

> **Paper:** [MKOS: A Biomimetic Architecture for Knowledge Base Quality Management](./paper/mkos_paper.pdf)

## Problem

Knowledge bases that power RAG systems accumulate quality issues over time. For internal/proprietary KBs, an LLM has no training data to verify claims against — standard few-shot classification is insufficient. MKOS uses retrieval-augmented verification against the KB itself.

## Architecture

```
  KB Chunk ──▶ Phase 1: Innate Classifier (1 LLM call)
                  │
                  ├── healthy ──▶ PASS
                  │
                  ▼
               Phase 0: Immune Memory (pattern cache)
                  │
                  ▼
               Phase 2: Adaptive Detectors ◄── Hybrid Search (FTS5 + vector)
                  ├── HallucinationDetector
                  ├── StalenessDetector
                  ├── BiasDetector
                  └── ContradictionDetector
```

Phase 1 gates healthy content with a single LLM call. Only flagged threats trigger retrieval-augmented analysis in Phase 2.

Additional subsystems:
- **Stigmergy** — Pheromone signals between components, decaying over time
- **Quorum sensing** — Collective action when threats cluster in a domain
- **Homeostasis** — Measures system vitals and recommends parameter adjustments
- **Composting** — Entropy-scored knowledge recycling
- **Fermentation** — Verification chamber for new content

## Benchmark Results

KQAB (Knowledge Quality Assurance Benchmark), single-annotator synthetic dataset, 321 items, 5-class:

| System | Macro-F1 |
|--------|----------|
| MKOS (2-phase) | 0.975 |
| LLM Few-Shot (same model) | 0.842 |
| LLM Chain-of-Thought | 0.816 |

McNemar p < 0.003, permutation test p < 0.003. Same underlying model (Claude Sonnet 4).

**Limitations:** Results are on a small, single-annotator dataset. The architecture is model-sensitive — GPT-4o achieves F1 = 0.869 with the same prompts (vs. 0.975 with Claude). Independent validation on larger, multi-annotator datasets is needed.

Full KQAB suite covers 4 tasks with synthetic and public (MNLI, FEVER) dataset variants, totaling 923 items.

## Quick Start

```bash
pip install -e .
cp .env.example .env   # add your ANTHROPIC_API_KEY

akm setup
akm index
akm immune-scan --sample-size 20

# Benchmark
akm kqab --cache --variant synth
akm kqab --cache --variant public --tasks T2,T4
```

## Project Structure

```
akm/
├── immune/          # Two-phase detection (system.py, detectors.py, memory.py)
├── search/          # Hybrid search: FTS5 + sqlite-vec + RRF fusion
├── stigmergy/       # Pheromone-based component coordination
├── quorum/          # Collective threat detection
├── homeostasis/     # Self-regulating parameter tuning
├── composting/      # Entropy-based knowledge recycling
├── fermentation/    # Content verification chamber
├── rag/             # RAG pipeline + evaluation
├── benchmarks/      # KQAB, baselines, statistics, ablation
├── llm/             # Claude + OpenAI clients, SQLite response cache
├── storage/         # SQLite with FTS5, schema migrations V1–V4
└── cli.py           # CLI entry point
paper/               # LaTeX source + compiled PDF
tests/               # Unit tests for all subsystems
```

## Stack

- Python 3.13, SQLite FTS5, sqlite-vec
- fastembed (BAAI/bge-small-en-v1.5, 384d)
- Claude Sonnet 4 (default, configurable)
- SQLite-backed LLM cache for reproducible benchmarks

## Citation

```bibtex
@article{munz2026mkos,
  title={MKOS: A Biomimetic Architecture for Knowledge Base Quality Management},
  author={Munz, Michael},
  year={2026}
}
```

## A Note on Process and Transparency

This project was developed with AI coding assistance. Architecture, research questions, and interpretation of results are human contributions. See the [repository-level transparency note](../README.md#transparency) for details.

## License

MIT
