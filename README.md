# Public Showcase

Selected research projects. All projects include an [AI transparency note](#transparency) describing the collaboration between human author and AI assistant.

## Projects

### [MKOS — Mycelial Knowledge Operating System](./mkos-knowledge-immune-system/)
Automated quality management for knowledge bases using a two-phase detection pipeline inspired by biological immune systems. Detects hallucinations, staleness, bias, and contradictions in unstructured text.

- [Source Code](./mkos-knowledge-immune-system/akm/)
- [Paper (PDF)](./mkos-knowledge-immune-system/paper/mkos_paper.pdf)
- [Benchmark Suite (KQAB)](./mkos-knowledge-immune-system/akm/benchmarks/)

### [Lean Multi-Provider Debate Framework](./lean-multi-agent-debate/)
Multi-agent debate engine that pits Google Gemini against Anthropic Claude to produce adversarially-vetted answers. Includes empirical sycophancy research: a two-dimensional model showing that echo chamber effects and false consensus are independent failure modes requiring different interventions.

- [Source Code](./lean-multi-agent-debate/debate/)
- [Paper (PDF)](./lean-multi-agent-debate/paper/debate_paper.pdf)
- [Sycophancy Benchmark](./lean-multi-agent-debate/benchmarks/sycophancy_compare.py)
- [Research Findings](./lean-multi-agent-debate/BACKLOG.md#research-findings-2026-03-13)

### [Agent Learning Approaches — How AI Agents Learn](./agent-learning-approaches/)
Empirical benchmark comparing seven agent learning strategies (CLL, RAG, Reflexion, ICL, CLL+RAG, Debate, SimLLM) across 14 tasks. Includes a taxonomy of 20 learning paradigms, a practitioner's decision framework, ablation study, statistical validation (McNemar p<0.001, Cohen's h effect sizes), and real LLM validation with Claude Haiku. Key finding: file-based institutional memory (CLL) wins 6/8 core tasks but fails on complex coding-agent scenarios where RAG dominates.

- [Paper](./agent-learning-approaches/how_ai_agents_learn_taxonomy_and_empirical_comparison.md)
- [Interactive Explainer](./agent-learning-approaches/explainer.html)
- [LinkedIn Summary](./agent-learning-approaches/linkedin_post.md)

### [Layered LLM Defense (LLD)](./layered-llm-defense/)
Biologically-inspired defense-in-depth framework for Large Language Models. Four orthogonal layers (formal verification, antifragile shell, information-theoretic interface, moving target defense) plus six biological primitives (Hormesis, Immune Memory, Microbiome, Self-Adversarial Loop with thymus selection, Fever mode, Herd Immunity). Includes an ablation study isolating the contribution of each architectural step (Vanilla → Bio-Off transferable gain of 18.6 percentage points on a 510-vector simulated benchmark) and a real-LLM evaluation against Llama-3.3-70B via Groq with refusal-corrected ASR of 0–2% on a small 100-vector sample. Standard-library Python, 453 deterministic unit tests, Apache 2.0. Honest about every limitation. Looking for collaborators for real-LLM benchmarking at scale, independent red-teaming, and production traffic evaluation.

- [Interactive Explainer](./layered-llm-defense/explainer.html)
- [Source Code](./layered-llm-defense/lld/)
- [Technical Report](./layered-llm-defense/outputs/technical_report_2026-04-07.md)
- [Executive Summary](./layered-llm-defense/outputs/executive_summary_2026-04-08.md)
- [Limitations Report](./layered-llm-defense/outputs/limitations_report_2026-04-07.md)
- [Quickstart Example](./layered-llm-defense/examples/quickstart.py)

### [Degressive Democracy](./degressive-democracy/)
Agent-based simulation of irreversible vote withdrawal as democratic accountability mechanism. 249 tests, formal Nash proof, Prospect Theory satisfaction model, Germany-specific scenarios, interactive dashboard. Shows that promise-keeping is Nash equilibrium, populists are always eliminated, and at municipal level the mechanism works as dormant institution.

- [Source Code](./degressive-democracy/degressive_democracy/)
- [Paper](./degressive-democracy/paper/degressive_democracy_irreversible_vote_withdrawal.md)
- [Findings Report](./degressive-democracy/FINDINGS.md)
- [Interactive Dashboard](./degressive-democracy/output/dashboard.html)
- [Nash Proof](./degressive-democracy/concepts/nash_proof.md)

---

<a id="transparency"></a>
## A Note on Process and Transparency

All projects in this showcase were developed in close collaboration with AI coding tools. For each project, the human author designed the architecture, formulated research questions, made strategic decisions, and interpreted results. The AI assistant implemented code, ran experiments, and drafted text.

Each project README contains a specific transparency note describing the division of work for that project. We believe honest disclosure of AI involvement in research is more valuable than pretending it didn't happen.
