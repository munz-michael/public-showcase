# Public Showcase

[![License: PolyForm Noncommercial 1.0](https://img.shields.io/badge/License-PolyForm_NC_1.0-blue.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0/)

Selected research projects. Papers, benchmarks, and results. All projects include an [AI transparency note](#transparency).

## Projects

### [Knowledge Fingerprint (KFP)](./knowledge-fingerprint/)
Epistemological identity for knowledge and AI agents. A 7-dimensional taxonomy with a formally proven Meet-Semilattice composition algebra, dual-fingerprinting for metadata inconsistency detection (82% misclassification found), agent behavioral profiling with drift detection, and portable Knowledge Units. 914 tests. [DOI: 10.5281/zenodo.19519682](https://doi.org/10.5281/zenodo.19519682)

- [Research Paper (PDF)](./knowledge-fingerprint/paper/knowledge_fingerprint_paper.pdf)

### [MKOS — Mycelial Knowledge Operating System](./mkos-knowledge-immune-system/)
Automated quality management for knowledge bases using a two-phase detection pipeline inspired by biological immune systems. Detects hallucinations, staleness, bias, and contradictions. Macro-F1 0.975 vs. LLM Few-Shot 0.842 (McNemar p < 0.003). [DOI: 10.5281/zenodo.19545770](https://doi.org/10.5281/zenodo.19545770)

- [Paper (PDF)](./mkos-knowledge-immune-system/paper/mkos_paper.pdf)

### [Layered LLM Defense (LLD)](./layered-llm-defense/)
Biologically-inspired defense-in-depth for Large Language Models. Four orthogonal layers plus six biological primitives. Ablation study: Vanilla to Bio-Off transferable gain of 18.6 percentage points. Real-LLM evaluation against Llama-3.3-70B: refusal-corrected ASR 0-2%. 453 tests. Looking for collaborators.

- [Architecture & Results](./layered-llm-defense/README.md)

### [Lean Multi-Provider Debate Framework](./lean-multi-agent-debate/)
Multi-agent debate engine pitting Google Gemini against Anthropic Claude. Empirical sycophancy research: heterogeneous providers reduce echo chamber effects vs. homogeneous setups.

- [Paper (PDF)](./lean-multi-agent-debate/paper/debate_paper.pdf)

### [Agent Learning Approaches](./agent-learning-approaches/)
Empirical benchmark comparing seven agent learning strategies across 14 tasks. Taxonomy of 20 paradigms, practitioner decision framework, ablation study, real LLM validation with Claude Haiku. CLL dominates stable patterns (6/8 tasks), Debate is most robust allrounder.

- [Paper](./agent-learning-approaches/how_ai_agents_learn_taxonomy_and_empirical_comparison.md)

### [Degressive Democracy](./degressive-democracy/)
Agent-based simulation of irreversible vote withdrawal as democratic accountability mechanism. Formal Nash proof, Prospect Theory satisfaction model, Germany-specific scenarios. Promise-keeping is Nash equilibrium, populists are always eliminated.

- [Interactive Dashboard](./degressive-democracy/output/dashboard.html)

---

<a id="transparency"></a>
## A Note on Process and Transparency

All projects in this showcase were developed in close collaboration with AI coding tools. For each project, the human author designed the architecture, formulated research questions, made strategic decisions, and interpreted results. The AI assistant implemented code, ran experiments, and drafted text.

Each project README contains a specific transparency note. We believe honest disclosure of AI involvement in research is more valuable than pretending it didn't happen.

## License

All projects in this repository are licensed under the [PolyForm Noncommercial License 1.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).

**You may freely use this for:**
- Non-commercial academic research, teaching, and publication
- Personal evaluation and non-production testing
- Contributions back to this repository

**Commercial use requires a separate license.**

Copyright (c) 2026 Michael Munz. All rights reserved.
