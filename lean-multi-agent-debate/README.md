# Lean Multi-Provider Debate Framework

**v1.9 · Gemini × Claude adversarial discourse engine**

Multi-agent debate system that pits two heterogeneous AI providers (Google Gemini and Anthropic Claude) against each other to produce calibrated, adversarially-vetted answers. Cross-provider debate, Delphi iterative refinement, argument graph construction, probabilistic calibration tracking, post-debate interactive chat, and semantic similarity analysis.

---

## Quick Start

```bash
# Install
cd research/lean_multi_agent_debate
pip install -e ".[dev]"

# Copy and fill in API keys
cp .env.example .env   # add ANTHROPIC_API_KEY + GOOGLE_API_KEY

# Run a debate
debate --problem "Is RSA-2048 under threat from quantum computing in 5 years?"

# Test without API keys (Claude substitutes for Gemini)
debate --problem "Test question" --mock-gemini

# Use a preset
debate --problem "Will AGI arrive before 2030?" --mode deep --save
```

---

## Installation

**Requirements:** Python 3.11+, API keys for Anthropic and Google (unless using `--mock-gemini`)

```bash
pip install -e .               # minimal install
pip install -e ".[dev]"        # + pytest for running tests
```

**Environment variables** (`.env` file):
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
```

---

## CLI Reference

### Core

| Flag | Description |
|---|---|
| `--problem "..."` | The question or problem to debate *(required)* |
| `--rounds N` | Max critique-verification rounds in Phase 2 (default: 1, max: 5) |
| `--mock-gemini` | Replace Gemini with Claude for testing (no Google API key needed) |
| `--save` | Save full debate report as Markdown to `output/` |

### v1.4 — Mode Presets

| Flag | Description |
|---|---|
| `--mode quick` | Minimal run: Phase 1 + Phase 2 + Phase 3 only (~30s, ~$0.04) |
| `--mode standard` | Default: + fact-check + judge (~60s, ~$0.08) |
| `--mode deep` | Full: + decompose + arg-graph + multi-turn + calibrate + 2 rounds (~120s, ~$0.18) |
| `--mode custom` | Use individual flags below (default if `--mode` is omitted) |

### v1.4 — Context Injection

| Flag | Description |
|---|---|
| `--context "..."` | Inject additional context into all Phase 1 prompts (constraints, background, data) |

### v1.6 — Expert Persona

| Flag | Description |
|---|---|
| `--persona DOMAIN` | Domain expert perspective for Gemini agents (e.g. `cybersecurity`, `finance`, `medicine`, `technology`, `policy`, `science`, or any free-form domain) |

### v1.2 — Extensions

| Flag | Description |
|---|---|
| `--adversarial` | Lock Gemini models into PRO vs CONTRA positions |
| `--grounded` | Gemini Pro uses live Google Search for factual context |
| `--multi-turn` | Gemini defends its position after Claude's critique (Phase 2b) |
| `--judge` | Add an independent Claude skeptical judge in Phase 4 |

### v1.3 Tier-1

| Flag | Description |
|---|---|
| `--moa` | Mixture of Agents: both Gemini models per role, Claude aggregates |
| `--fact-check` | Claim-level fact-checking after Phase 1 (Phase 1.5) |
| `--decompose` | Claude breaks the problem into sub-questions first (Phase 0) |

### v1.3 Tier-2

| Flag | Description |
|---|---|
| `--arg-graph` | Build a formal argument graph (Phase 1.6) |
| `--delphi N` | Delphi iterative refinement: N rounds (1–5, replaces Phase 1) |
| `--calibrate` | Extract probabilistic claims, persist to `calibration_history.jsonl` |

### Subcommands

```bash
debate stats                                    # Calibration history statistics (JSON)
debate list                                     # List saved reports in output/ (JSON)
debate resolve <debate_id> <claim_idx> <true|false> [--note "..."]  # Record outcome
```

### Examples

```bash
# Minimal
debate --problem "Is remote work more productive than office work?"

# With context (inject background knowledge)
debate --problem "Should we migrate to Kubernetes?" \
  --context "We run 12 microservices on Docker Swarm, team of 4 engineers" \
  --mode standard

# Full kitchen-sink
debate --problem "Will AGI arrive before 2030?" \
  --adversarial --grounded --multi-turn --judge \
  --moa --fact-check --decompose --arg-graph \
  --delphi 2 --calibrate --rounds 2 --save

# API-free test
debate --problem "Test" --mock-gemini --decompose --fact-check

# Record calibration outcome
debate resolve debate-abc123 0 true --note "Confirmed by Q4 report"
```

---

## Streamlit UI (v1.7)

```bash
streamlit run streamlit_app.py
```

Opens at `http://localhost:8501`. Features:

- **Mode selector** (quick / standard / deep / custom) with live cost estimate
- **Context input** — paste text or upload PDF, Markdown, TXT files as grounding context
- **All CLI flags** as sidebar controls (disabled in preset modes)
- **Interactive Plotly charts**: consensus gauges, Delphi convergence, calibration CI bars
- **Graphviz argument graph** with node/edge tables
- **Post-debate chat** — ask follow-up questions about any completed debate with streaming responses and quick-action buttons (Executive Summary, Steelman, Decision Memo, Open Questions, Verdict Flip); **export chat as Markdown**
- **Rubric Radar Chart** — Plotly polar chart comparing Analysis A vs B across 4 quality dimensions
- **Content Similarity metric** — TF-IDF cosine similarity between Phase 1 outputs (no extra deps)
- **Divergence Alert** — when consensus < 40%, Claude explains WHY models diverge

---

## MCP Server (Claude Code integration)

After installing npm dependencies, the debate engine is available as a Claude Code MCP tool:

```bash
cd mcp_server && npm install
```

The server is pre-configured in `.mcp.json`. Restart Claude Code to activate.

**Available MCP tools:**
- `debate_run` — Run a debate on any problem
- `debate_calibration_stats` — Show calibration history
- `debate_list_reports` — List saved reports

---

## Running Tests

```bash
pytest tests/ -v         # all 32 tests, no API keys needed
pytest tests/ -k models  # only model validation tests
```

---

## Benchmark Suite

```bash
# API-free: 3 problems (one per category)
python benchmarks/runner.py --mock

# 5 problems, mock mode
python benchmarks/runner.py --problems 5 --mock

# Factual category only
python benchmarks/runner.py --category factual --mock

# Full 15-problem benchmark (requires API keys)
python benchmarks/runner.py --all --output results.json
```

### Sycophancy Benchmark

Tests the core hypothesis: *heterogeneous providers (Gemini × Claude) exhibit less sycophancy than same-provider setups (Claude × Claude).*

Metrics compared: `agreement_score`, `consensus_score`, `n_contradictions`, `echo_score` (TF-cosine similarity of final answer to Phase 1 content), `cross_answer_similarity`.

```bash
# API-free harness test (Claude×Claude × 2):
python benchmarks/sycophancy_compare.py --mock-only --problems 3

# Real comparison (requires GOOGLE_API_KEY):
python benchmarks/sycophancy_compare.py --problems 5 --output output/sycophancy_report.json

# Single question:
python benchmarks/sycophancy_compare.py --problem "Will AGI arrive before 2030?"
```

Or via CLI / MCP:
```bash
debate compare --mock-only --problems 3
# MCP tool: debate_compare
```

---

## Architecture

See [00_ARCHITECTURE.md](00_ARCHITECTURE.md) for design decisions, phase diagram, and consensus formula.

---

## Output

Reports saved to `output/YYYY-MM-DD_slug/` as Markdown with YAML frontmatter (CDS-compatible):

```
output/
├── 2026-03-13_is-rsa-2048-under-threat/
│   └── 2026-03-13_is-rsa-2048-under-threat_report.md
└── calibration_history.jsonl
```

### Final Answer fields (v1.4+)

Every debate produces a `FinalAnswer` with:
- `content` — full consensus answer
- `recommendation` — single actionable recommendation (1–2 sentences)
- `key_uncertainties` — list of what would resolve remaining uncertainty
- `next_steps` — ordered list of concrete follow-up actions
- `consensus_score`, `confidence`, `key_disagreements`

## A Note on Process and Transparency

This project was developed with AI coding assistance. Architecture, research questions, and interpretation of results are human contributions. See the [repository-level transparency note](../README.md#transparency) for details.

## License

PolyForm Noncommercial 1.0

## Author

Michael Munz
