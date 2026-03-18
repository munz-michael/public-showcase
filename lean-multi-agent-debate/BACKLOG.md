# Backlog — Lean Multi-Provider Debate Framework

## Tier-3 Features (not yet scheduled)

### Debate Tree
Run multiple independent debate branches on sub-questions (from `--decompose`) and synthesize them into a final answer tree. Enables deeper exploration of complex multi-faceted problems.

### Self-Play Calibration
After a debate, re-run the same question with swapped roles (Gemini Thinking plays factual, Gemini Pro plays logical). Compare final answers — large divergence indicates the debate result is role-sensitive.

### Tool-Augmented Agents
Allow Gemini Pro to call real tools during Phase 1 (code execution, calculator, Wikipedia lookup). Would require an agent-level sandboxing layer.

### Outcome Tracking for Calibration
The `debate resolve` subcommand exists but requires manual entry. Future: automated outcome tracking via periodic re-evaluation or external data source linkage.

### Debate Tournament
Run N problems against multiple configuration profiles (e.g., standard vs MoA vs Delphi) and compare quality metrics. Enables configuration selection for specific problem types.

### Custom Model Injection
Allow users to substitute arbitrary OpenAI-compatible endpoints for Gemini (e.g., local Ollama, Mistral API). Would require abstracting the provider interface.

### Persistent Chat Across Sessions
Currently post-debate chat lives in Streamlit session state (lost on page reload). Persist chat history alongside the saved report in `output/`.

---

## Known Limitations

- **No ground-truth evaluation**: For controversial problems, there is no oracle. Quality is measured by internal consistency (consensus score, verification pass) rather than factual accuracy.
- **Calibration without automated outcomes**: Probabilistic claims are extracted and `debate resolve` allows manual outcome recording, but there is no automated pipeline to track real-world outcomes at scale.
- **Gemini grounding API**: The `--grounded` flag depends on Google's Search grounding API, which may have availability/quota constraints.
- **Rate limits**: Running the full flag combination (`--moa --delphi 3 --fact-check --arg-graph --calibrate --rounds 3 --judge`) can hit Claude Opus rate limits for consecutive runs.
- **Output dir is relative**: The `output/` directory is relative to the working directory. Running `debate` from outside the project root may create output in unexpected locations.
- **Context truncation**: Long uploaded files (PDF) are injected as raw text. No chunking/RAG — very large documents will hit context limits.
- **Chat history not persisted**: Post-debate chat (v1.5) lives in Streamlit session_state only; reloading the page loses the conversation.

---

## Research Findings (2026-03-13)

Six empirical experiments run via `debate compare` / `benchmarks/sycophancy_compare.py`.
All mock experiments use Claude×Claude (CxC); E1 used real Gemini API (GxC).

### Two-Dimensional Sycophancy Model

Sycophancy in LLM debates manifests along two independent axes:

| Dimension | Metric | Best reducer |
|---|---|---|
| **Echo chamber** | Echo Score (TF-cosine Phase1 → Final) | Cross-provider (GxC, Δ=-0.175) |
| **False consensus** | Agreement Score | Adversarial mode (Δ=-14.7%) |

These two dimensions are orthogonal: adversarial mode has no effect on Echo Score (E4: Δ=0.000), and cross-provider has no effect on Agreement Score (E1: Δ=-2%).

### E1 — Cross-Provider (empirical, real Gemini API)
```
Echo GxC=0.601  CxC=0.776  Δ=-0.175  ← provider identity drives echo
Agreement: GxC=93.8%  CxC=95.8%  Δ=-2.0%  ← not significant
Sycophancy signal rate: 25% (1/4 problems)
Strongest signal: Bitcoin (GxC=90% vs CxC=97%)
```
**Finding**: Cross-provider debate reduces echo chamber by 22% (relative). Provider identity is the primary lever for Echo Score.

### E2 — Toulmin Format (mock CxC, prose vs. Toulmin schema)
```
Echo Prose=0.818  Toulmin=0.827  Δ=+0.009  ← not significant
```
**Finding (null)**: Structured argument format (CLAIM/GROUNDS/WARRANT/QUALIFIER/REBUTTAL) does not reduce echo. Reason: Toulmin keywords appear in both Phase 1 and Phase 3, artefactually inflating cosine similarity. The Phase 3 synthesizer abstracts from format vocabulary.

### E3 — Adversarial Mode (mock CxC, standard vs. PRO/CONTRA role-locked)
```
Agreement: Standard=95.3%  Adversarial=80.7%  Δ=-14.7%
Echo: Standard=0.811  Adversarial=0.803  Δ=-0.008  ← not significant
Notable: Python GIL (factually settled): Standard 95% → Adversarial 55% (Δ=-40%)
```
**Finding**: Adversarial role-locking reduces Agreement Score by 14.7% but has no effect on Echo Score. Strongest effect on factually settled questions (forced CONTRA position generates genuine Phase 2 disagreement). Confirms Agreement and Echo are independent dimensions.

### E4 — Combined 2×2 Matrix (mock-only: provider×adversarial, mock CxC as GxC substitute)
```
GxC-std:  agreement=95.0%  echo=0.651
GxC-adv:  agreement=18.5%  echo=0.651   ← adversarial: -76.5% agreement, 0% echo
CxC-std:  agreement=96.0%  echo=0.785
CxC-adv:  agreement=71.5%  echo=0.802   ← adversarial: -24.5% agreement, +0% echo
```
**Finding**: Adversarial effect on Echo Score is exactly zero in both configs (0.651 vs 0.651). Confirms dimensional independence. Note: GxC-adv shows extreme agreement collapse (18.5%) — mock artefact of random prompt divergence, requires real GxC replication.

### E5 — Category Split (mock CxC, factual vs. controversial)
```
Factual:       echo=0.770  agreement=96.4%  sycophancy_signals=0/5
Controversial: echo=0.633  agreement=79.2%  sycophancy_signals=0/5
```
**Finding (counter-intuitive)**: Controversial questions show *lower* echo scores than factual questions (Δ=-0.137). Reason: Phase 1 agents generate genuinely divergent arguments on value-based questions → Phase 3 synthesizer must produce more original content to arbitrate → less vocabulary recycling. Factual questions produce convergent Phase 1 content → Phase 3 can simply summarize → higher echo. Sycophancy in the "echo" sense is paradoxically *less* problematic for controversial questions.

### E6 — Delphi Sycophancy (mock CxC, standard vs. delphi-2 vs. delphi-3)
```
Standard: agreement=95.7%  echo=0.753
Delphi-2: agreement=97.7%  echo=0.683  Δecho=-0.070  Δagr=+2.0%
Delphi-3: agreement=97.7%  echo=0.714  Δecho=-0.039  Δagr=+2.0%
```
**Finding (hypothesis falsified)**: Delphi *reduces* Echo Score (not amplifies). Mechanism: iterative refinement causes agents to update away from initial positions → Phase 3 final answer uses Phase-N vocabulary, not Phase-1. But Delphi *increases* Agreement Score by +2% — Delphi is the only mechanism that reduces echo while simultaneously amplifying consensus. Trade-off: use Delphi when echo reduction matters; avoid when agreement inflation is a concern.

### Implications for Debate Configuration

| Goal | Recommended config |
|---|---|
| Minimize echo chamber | `--no-mock` (real GxC) — strongest single lever |
| Minimize false consensus | `--adversarial` — Δ=-14.7% |
| Both | `--adversarial` + real GxC (E4 replication needed) |
| Reduce echo, accept some consensus | `--delphi 2` (Δecho=-0.070, Δagr=+2%) |
| Controversial questions | Standard config sufficient (naturally lower echo) |
| Factual questions | Cross-provider more important (higher baseline echo) |

---

## Open Research Questions

1. ~~Does cross-provider debate (Gemini × Claude) reduce sycophancy?~~ → **Answered (E1): Yes, Δecho=-0.175**
2. Does Delphi mode produce higher consensus scores than standard Phase 1 on controversial questions? → Partially answered (E6): yes, Δagr=+2% on factual
3. Is there a correlation between `--fact-check` reliability score and final consensus score?
4. How does `--moa` affect latency vs quality trade-off compared to single-model Phase 1?
5. Do probabilistic claims from Claude's calibration module converge toward 50% on genuinely uncertain questions, or do they show overconfidence?
6. Does post-debate chat change the user's interpretation of the consensus conclusion? (qualitative study)
7. **NEW**: Does GxC + adversarial show additive effect? (E4 with real Gemini — E4-mock showed extreme Δagr=-76.5%, likely artefact)
8. **NEW**: Does category (factual vs. controversial) moderate the cross-provider echo effect? (E5 used mock only)

---

## Technical Debt

- `debate_manager.py` has grown to ~1,400 lines — could benefit from splitting into phase-specific modules (`phases/phase1.py`, `phases/phase2.py`, etc.)
- `output_formatter.py` save_report() is ~300 lines of f-string templates — a Jinja2 template would be more maintainable
- No async streaming: all API calls wait for complete responses before displaying. Streaming would improve perceived latency for Phase 3 final answer
- `calibration_history.jsonl` has no schema migration strategy — adding new fields to `CalibrationRecord` could break existing history parsing
- Root-level legacy files (`main.py`, `debate_manager.py`, `models.py`, `output_formatter.py`, `config.py`) still exist alongside the `debate/` package — safe to delete once confirmed unused

---

## Changelog

### v1.9 (2026-03-13)
- **Toulmin Format** (`--format toulmin`): Phase 1 agents express arguments as structured Toulmin schema (CLAIM/GROUNDS/WARRANT/QUALIFIER/REBUTTAL). CLI flag + `DebateManager(debate_format=...)`. Benchmark result: no significant echo reduction (Δ=+0.009) — format-independent synthesizer.
- **Extended Sycophancy Benchmark** (`benchmarks/sycophancy_compare.py`): 4 new comparison modes:
  - `--compare-combined`: 2×2 matrix (provider × adversarial) — tests additive effects
  - `--compare-delphi`: standard vs. delphi-2 vs. delphi-3 — tests iterative consensus effect on echo
  - `--compare-formats`: prose vs. Toulmin echo score A/B test
  - `--compare-adversarial`: standard vs. PRO/CONTRA agreement/echo A/B test
- **`_run_one()` extended**: `delphi_rounds` parameter — routes to `mgr.run_delphi()` when >0
- **Research Findings documented** in `BACKLOG.md`: 6-experiment empirical study, two-dimensional sycophancy model (Echo=provider, Agreement=role-constraints)

### v1.8 (2026-03-13)
- **Sycophancy Benchmark** (`benchmarks/sycophancy_compare.py`): empirical cross-provider comparison harness. Runs identical questions in Gemini×Claude and Claude×Claude configurations, measures agreement score delta, contradiction count delta, echo score (TF-cosine similarity of final answer to Phase 1 content), and cross-answer similarity. CLI: `debate compare`. MCP tool: `debate_compare`.
- **UX Refactor** (`streamlit_app.py`): tabbed results layout (Answer / Analysis / Critique / Judge), summary metric banner, conditional expander for extensions, empty state with example question prefill, streaming chat export.

### v1.7 (2026-03-13)
- **Semantic Similarity Score**: TF-IDF cosine similarity between Phase 1 outputs (stdlib-only, no extra deps). Displayed as Content Similarity metric in Streamlit Phase 2 alongside rubric chart.
- **Rubric Radar Chart**: Replaced text-based rubric with Plotly Scatterpolar chart comparing Analysis A vs B across 4 dimensions (Logical Coherence, Evidence Quality, Completeness, Reasoning Depth).
- **Divergence Explanation**: When `consensus_score < 0.4`, Claude explains WHY models diverge (structural uncertainty / value assumptions / factual gaps / ambiguous framing). Shown as warning banner in Phase 3.
- **Chat Export**: Download post-debate chat as Markdown (`debate_chat.md`) — button alongside Clear.
- **Root cleanup**: Removed legacy root-level files (`main.py`, `debate_manager.py`, `models.py`, `output_formatter.py`, `config.py`). Package-only structure now enforced.

### v1.6 (2026-03-13)
- Expert Persona: `--persona DOMAIN` CLI flag + Streamlit sidebar (6 presets + free-form)
- Content-Delta Early Exit in Phase 2 loop (<12% novel word fraction → break)

### v1.5 (2026-03-13)
- Post-debate interactive chat with streaming (Claude Sonnet 4.6)
- 5 quick-action buttons: Executive Summary, Steelman, Decision Memo, Open Questions, Verdict Flip
- File upload for context: PDF (pypdf), Markdown, plain text

### v1.4 (2026-03-13)
- Mode presets: `--mode quick/standard/deep` (CLI + Streamlit)
- Context injection: `--context "..."` CLI flag + sidebar textarea
- `FinalAnswer` extended: `recommendation`, `key_uncertainties`, `next_steps`
- Calibration resolve: `debate resolve <id> <idx> <true|false>`
- Live cost estimate in Streamlit sidebar

### v1.3 (2026-03-12)
- Python package (`debate/`), `pyproject.toml`, `pip install -e .`
- Test suite: 32 tests, no API keys needed
- MCP Server (3 tools: debate_run, calibration_stats, list_reports)
- Benchmark suite: 15 problems, `--mock` mode
- Tier-1: `--moa`, `--fact-check`, `--decompose`
- Tier-2: `--arg-graph`, `--delphi N`, `--calibrate`
- Streamlit UI with Plotly gauges, Graphviz argument graph, Delphi chart

### v1.2 (prior)
- `--adversarial`, `--grounded`, `--multi-turn`, `--judge`
- `debate stats`, `debate list` subcommands
