"""
Lean Multi-Agent Debate Engine — Streamlit Web UI
Run: streamlit run streamlit_app.py
"""

import asyncio
import sys
import time
import uuid
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, "/workspaces/Claude Code/config")

# Package imports (debate/ sub-package takes precedence when installed)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Multi-Agent Debate Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: #0e1117;
    border: 1px solid #262730;
    border-radius: 8px;
    padding: 12px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_async(coro):
    return asyncio.run(coro)


def _confidence_bar(value: float) -> str:
    filled = int(value * 20)
    return f"{'█' * filled}{'░' * (20 - filled)}  {value:.0%}"


def _argument_graph_to_dot(graph) -> str:
    """Convert ArgumentGraph to Graphviz DOT format for st.graphviz_chart()."""
    type_shapes = {
        "premise": "box", "conclusion": "diamond",
        "evidence": "ellipse", "assumption": "hexagon",
    }
    type_colors = {
        "premise": "#4fc3f7", "conclusion": "#81c784",
        "evidence": "#ffb74d", "assumption": "#ce93d8",
    }
    edge_styles = {"supports": "solid", "derives": "bold", "contradicts": "dashed"}
    edge_colors = {"supports": "darkgreen", "derives": "steelblue", "contradicts": "crimson"}

    lines = ['digraph G {', '  rankdir=LR;', '  bgcolor="#0e1117";',
             '  node [fontcolor=white fontname="Arial" fontsize=10];',
             '  edge [fontcolor=white fontname="Arial" fontsize=9];']
    for n in graph.nodes:
        shape = type_shapes.get(n.node_type, "box")
        color = type_colors.get(n.node_type, "#888888")
        label = n.content[:40].replace('"', "'")
        lines.append(
            f'  {n.id} [label="{n.id}\\n{label}" shape={shape} '
            f'style=filled fillcolor="{color}" color="white"];'
        )
    for e in graph.edges:
        style = edge_styles.get(e.edge_type, "solid")
        color = edge_colors.get(e.edge_type, "gray")
        lines.append(
            f'  {e.from_id} -> {e.to_id} [label="{e.edge_type}" '
            f'style={style} color="{color}"];'
        )
    lines.append("}")
    return "\n".join(lines)


def _scores_gauge(value: float, title: str, color: str = "#00d4ff") -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value * 100,
        number={"suffix": "%", "font": {"size": 28, "color": "white"}},
        title={"text": title, "font": {"size": 14, "color": "#aaaaaa"}},
        gauge={
            "axis": {"range": [0, 100], "tickcolor": "#666"},
            "bar": {"color": color},
            "bgcolor": "#1a1a2e",
            "steps": [
                {"range": [0, 40], "color": "#2d1b1b"},
                {"range": [40, 70], "color": "#2d2d1b"},
                {"range": [70, 100], "color": "#1b2d1b"},
            ],
        },
    ))
    fig.update_layout(
        height=200, margin=dict(t=40, b=10, l=20, r=20),
        paper_bgcolor="#0e1117", font_color="white",
    )
    return fig


def _delphi_chart(rounds_data: list) -> go.Figure:
    round_nums = [r.round_n for r in rounds_data]
    conf_a = [r.confidence_a * 100 for r in rounds_data]
    conf_b = [r.confidence_b * 100 for r in rounds_data]
    deltas = [r.delta * 100 for r in rounds_data]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=round_nums, y=conf_a, mode="lines+markers",
        name="Analysis A", line=dict(color="#4fc3f7", width=2),
        marker=dict(size=8),
    ))
    fig.add_trace(go.Scatter(
        x=round_nums, y=conf_b, mode="lines+markers",
        name="Analysis B", line=dict(color="#81c784", width=2),
        marker=dict(size=8),
    ))
    fig.add_trace(go.Bar(
        x=round_nums, y=deltas, name="Δ Delta",
        marker_color="rgba(255,183,77,0.4)", yaxis="y2",
    ))
    fig.update_layout(
        title="Confidence Evolution across Delphi Rounds",
        xaxis=dict(title="Round", tickmode="linear", dtick=1, color="white"),
        yaxis=dict(title="Confidence (%)", range=[0, 105], color="white"),
        yaxis2=dict(title="Δ Change (%)", overlaying="y", side="right",
                    range=[0, 50], color="#ffb74d"),
        paper_bgcolor="#0e1117", plot_bgcolor="#1a1a2e",
        font_color="white", legend=dict(bgcolor="rgba(0,0,0,0)"),
        height=320, margin=dict(t=50, b=40),
    )
    return fig


def _calibration_chart(claims: list) -> go.Figure:
    labels = [f"{c.claim[:50]}…" if len(c.claim) > 50 else c.claim for c in claims]
    probs = [c.probability * 100 for c in claims]
    ci_lower = [c.ci_lower * 100 for c in claims]
    ci_upper = [c.ci_upper * 100 for c in claims]
    colors = ["#81c784" if p >= 70 else "#e57373" if p <= 30 else "#ffb74d" for p in probs]
    err_minus = [p - l for p, l in zip(probs, ci_lower)]
    err_plus = [u - p for u, p in zip(ci_upper, probs)]

    fig = go.Figure(go.Bar(
        y=labels, x=probs, orientation="h",
        marker_color=colors,
        error_x=dict(type="data", symmetric=False,
                     array=err_plus, arrayminus=err_minus,
                     color="rgba(255,255,255,0.5)", thickness=2),
    ))
    fig.update_layout(
        title="Probabilistic Claims with 90% CI",
        xaxis=dict(title="Probability (%)", range=[0, 105], color="white"),
        yaxis=dict(color="white", automargin=True),
        paper_bgcolor="#0e1117", plot_bgcolor="#1a1a2e",
        font_color="white", height=max(250, len(claims) * 50),
        margin=dict(t=50, b=40, l=20, r=20),
    )
    return fig


def _fact_check_pie(fact_check) -> go.Figure:
    fig = go.Figure(go.Pie(
        labels=["Confirmed", "Refuted", "Uncertain"],
        values=[fact_check.confirmed_count, fact_check.refuted_count, fact_check.uncertain_count],
        marker_colors=["#81c784", "#e57373", "#ffb74d"],
        textinfo="label+percent",
        hole=0.45,
    ))
    fig.update_layout(
        title="Fact-Check Claim Status",
        paper_bgcolor="#0e1117", font_color="white",
        height=280, margin=dict(t=50, b=10),
        showlegend=False,
    )
    return fig


# ── Rendering helpers ─────────────────────────────────────────────────────────

def show_phase1(logical, factual):
    st.subheader("📊 Phase 1 — Initial Thesis")
    col_a, col_b = st.columns(2)

    with col_a:
        role_label = logical.role.replace("_", " ").title()
        with st.container(border=True):
            st.markdown(f"**Analysis A** — {role_label}  \n`{logical.model_id}`")
            st.markdown(logical.content)
            if logical.chain_of_thought:
                with st.expander("Chain of Thought"):
                    st.markdown(logical.chain_of_thought)
            if logical.aggregated_from:
                st.caption("MoA sources: " + " · ".join(logical.aggregated_from))
            if logical.known_unknowns:
                with st.expander("Known Unknowns"):
                    for u in logical.known_unknowns:
                        st.markdown(f"- {u}")
            st.progress(logical.confidence, text=f"Confidence: {logical.confidence:.0%}")

    with col_b:
        role_label_b = factual.role.replace("_", " ").title()
        with st.container(border=True):
            st.markdown(f"**Analysis B** — {role_label_b}  \n`{factual.model_id}`")
            st.markdown(factual.content)
            if factual.chain_of_thought:
                with st.expander("Reasoning"):
                    st.markdown(factual.chain_of_thought)
            if factual.aggregated_from:
                st.caption("MoA sources: " + " · ".join(factual.aggregated_from))
            if factual.known_unknowns:
                with st.expander("Known Unknowns"):
                    for u in factual.known_unknowns:
                        st.markdown(f"- {u}")
            if factual.sources:
                with st.expander("Grounded Sources"):
                    for s in factual.sources[:5]:
                        st.markdown(f"- {s}")
            st.progress(factual.confidence, text=f"Confidence: {factual.confidence:.0%}")


def show_decomposition(decomposition):
    st.subheader("🔍 Phase 0 — Problem Decomposition")
    complexity_color = {"simple": "green", "moderate": "orange", "complex": "red"}.get(
        decomposition.complexity, "gray"
    )
    st.markdown(f"**Complexity:** :{complexity_color}[{decomposition.complexity.upper()}]  |  {decomposition.reasoning}")
    rows = [{"#": i + 1, "Aspect": sq.aspect.upper(), "Sub-Question": sq.question}
            for i, sq in enumerate(decomposition.sub_questions)]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def show_fact_check(fact_check):
    st.subheader("🔎 Phase 1.5 — Claim-Level Fact-Check")
    col_pie, col_meta = st.columns([1, 2])
    with col_pie:
        st.plotly_chart(_fact_check_pie(fact_check), use_container_width=True)
    with col_meta:
        st.metric("Overall Reliability", f"{fact_check.overall_reliability:.0%}")
        st.markdown(fact_check.summary)

    status_icons = {"confirmed": "✅", "refuted": "❌", "uncertain": "⚠️"}
    rows = [
        {
            "Status": f"{status_icons.get(c.status, '·')} {c.status.upper()}",
            "Source": c.source_role,
            "Claim": c.claim,
            "Evidence": c.evidence[:120],
        }
        for c in fact_check.claims
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def show_argument_graph(graph):
    st.subheader("🕸️ Phase 1.6 — Structured Argument Graph")
    st.caption(graph.summary)

    tab_graph, tab_nodes, tab_edges = st.tabs(["Graph", "Nodes", "Edges"])
    with tab_graph:
        dot_src = _argument_graph_to_dot(graph)
        st.graphviz_chart(dot_src, use_container_width=True)
        with st.expander("Mermaid source (for reports)"):
            st.code(graph.to_mermaid(), language="text")
    with tab_nodes:
        node_rows = [{"ID": n.id, "Type": n.node_type, "Source": n.source_role, "Content": n.content}
                     for n in graph.nodes]
        st.dataframe(node_rows, use_container_width=True, hide_index=True)
    with tab_edges:
        edge_rows = [{"From": e.from_id, "Relation": e.edge_type, "To": e.to_id}
                     for e in graph.edges]
        st.dataframe(edge_rows, use_container_width=True, hide_index=True)
        n_contra = len(graph.contradiction_edges)
        if n_contra:
            st.error(f"⚡ {n_contra} contradiction(s) in argument chains")
        else:
            st.success("No structural contradictions")


def show_delphi(delphi):
    st.subheader("🔄 Phase 1 — Delphi Iterative Refinement")
    if delphi.converged:
        st.success(f"Converged at round {delphi.convergence_round}")
    else:
        st.warning(f"Ran all {len(delphi.rounds)} rounds without convergence")
    st.plotly_chart(_delphi_chart(delphi.rounds), use_container_width=True)


def show_calibration(record, history_stats=None):
    st.subheader("📐 Calibration Tracking")
    if record.fact_check_alignment is not None:
        st.metric("Fact-Check Alignment", f"{record.fact_check_alignment:.0%}")
    st.plotly_chart(_calibration_chart(record.claims), use_container_width=True)
    if history_stats and history_stats.get("total_debates", 0) > 1:
        st.caption(
            f"Historical: {history_stats['total_debates']} debates · "
            f"{history_stats['total_claims']} total claims tracked"
        )


def _rubric_radar(synthesis) -> go.Figure:
    """Plotly polar/radar chart comparing rubric scores for Analysis A vs B."""
    categories = ["Logical Coherence", "Evidence Quality", "Completeness", "Reasoning Depth"]
    r_a = synthesis.rubric_logical
    r_b = synthesis.rubric_factual
    vals_a = [r_a.logical_coherence, r_a.evidence_quality, r_a.completeness, r_a.reasoning_depth]
    vals_b = [r_b.logical_coherence, r_b.evidence_quality, r_b.completeness, r_b.reasoning_depth]
    # Close the polygon
    cats_closed = categories + [categories[0]]
    vals_a_closed = vals_a + [vals_a[0]]
    vals_b_closed = vals_b + [vals_b[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals_a_closed, theta=cats_closed,
        fill="toself", name="Analysis A (Logical)",
        line_color="#4fc3f7", fillcolor="rgba(79,195,247,0.15)",
    ))
    fig.add_trace(go.Scatterpolar(
        r=vals_b_closed, theta=cats_closed,
        fill="toself", name="Analysis B (Factual)",
        line_color="#81c784", fillcolor="rgba(129,199,132,0.15)",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5])),
        showlegend=True,
        legend=dict(orientation="h", y=-0.15),
        margin=dict(l=20, r=20, t=20, b=30),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def show_critique(synthesis, verification):
    st.subheader("⚔️ Phase 2 — Adversarial Critique")

    if synthesis.contradictions:
        st.error(f"**{len(synthesis.contradictions)} Contradiction(s) detected**")
        for c in synthesis.contradictions:
            sev_color = "red" if c.severity == "major" else "orange"
            with st.container(border=True):
                st.markdown(f":{sev_color}[**{c.severity.upper()}**]")
                col1, col2 = st.columns(2)
                col1.markdown(f"**A:** {c.claim_a}")
                col2.markdown(f"**B:** {c.claim_b}")
    else:
        st.success("No contradictions detected")

    with st.expander("Synthesis Draft"):
        st.markdown(synthesis.synthesis_draft)

    if synthesis.assumptions_challenged:
        with st.expander(f"Assumptions Challenged ({len(synthesis.assumptions_challenged)})"):
            for a in synthesis.assumptions_challenged:
                st.markdown(f"- {a}")

    # v1.7: Rubric radar chart + semantic similarity metric
    col_radar, col_sim = st.columns([3, 1])
    with col_radar:
        st.markdown("**Quality Rubric (1–5 scale)**")
        st.plotly_chart(_rubric_radar(synthesis), use_container_width=True)
    with col_sim:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if synthesis.semantic_similarity is not None:
            sim_pct = synthesis.semantic_similarity
            delta_label = "high overlap" if sim_pct >= 0.6 else ("moderate" if sim_pct >= 0.3 else "divergent focus")
            st.metric(
                "Content Similarity",
                f"{sim_pct:.0%}",
                delta=delta_label,
                help="TF-IDF cosine similarity between Phase 1 outputs. High = models analyzed similar content; Low = divergent focus areas.",
            )

    st.divider()
    st.markdown("**Verification** (Gemini Thinking)")
    if verification.verified:
        st.success("Synthesis verified — no new logical errors")
    else:
        st.warning("Verification flagged issues")
    if verification.logical_errors:
        with st.expander(f"Logical errors ({len(verification.logical_errors)})"):
            for e in verification.logical_errors:
                st.markdown(f"- {e}")
    if verification.wishful_thinking:
        with st.expander(f"Wishful thinking ({len(verification.wishful_thinking)})"):
            for w in verification.wishful_thinking:
                st.markdown(f"- {w}")
    if verification.verification_notes:
        st.caption(verification.verification_notes)


def show_rebuttal(rebuttal):
    st.subheader("💬 Phase 2b — Gemini Rebuttal")
    st.progress(rebuttal.rebuttal_score, text=f"Position maintained: {rebuttal.rebuttal_score:.0%}")
    st.markdown(rebuttal.rebuttal_content)
    col_c, col_m = st.columns(2)
    with col_c:
        st.markdown("**Points Conceded**")
        for p in rebuttal.points_conceded or ["(none)"]:
            st.markdown(f"- {p}")
    with col_m:
        st.markdown("**Points Maintained**")
        for p in rebuttal.points_maintained or ["(none)"]:
            st.markdown(f"- {p}")


def show_final(final, synthesis):
    st.subheader("✅ Phase 3 — Final Consensus Answer")

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        st.plotly_chart(_scores_gauge(final.consensus_score, "Consensus Score", "#4fc3f7"),
                        use_container_width=True)
    with col_g2:
        st.plotly_chart(_scores_gauge(final.confidence, "Confidence", "#81c784"),
                        use_container_width=True)
    with col_g3:
        st.plotly_chart(_scores_gauge(synthesis.agreement_score, "Agreement Score", "#ce93d8"),
                        use_container_width=True)

    # v1.7: Divergence alert when consensus is low
    if final.consensus_score < 0.4 and final.divergence_explanation:
        st.warning(f"⚠️ **Significant Divergence** (C = {final.consensus_score:.0%})\n\n{final.divergence_explanation}")

    # v1.4: Recommendation box (prominent)
    if final.recommendation:
        st.info(f"**Recommendation:** {final.recommendation}")

    with st.container(border=True):
        st.markdown(final.content)

    # v1.4: Key uncertainties + next steps
    if final.key_uncertainties or final.next_steps:
        col_u, col_ns = st.columns(2)
        with col_u:
            if final.key_uncertainties:
                st.markdown("**Key Uncertainties**")
                for u in final.key_uncertainties:
                    st.markdown(f"- ❓ {u}")
        with col_ns:
            if final.next_steps:
                st.markdown("**Next Steps**")
                for i, s in enumerate(final.next_steps, 1):
                    st.markdown(f"{i}. {s}")

    if final.key_disagreements:
        with st.expander(f"Key Disagreements ({len(final.key_disagreements)})"):
            for d in final.key_disagreements:
                st.markdown(f"- {d}")


def show_judge(verdict):
    st.subheader("🧑‍⚖️ Phase 4 — Skeptical Judge")
    st.metric("Reliability Score", f"{verdict.reliability_score:.0%}")
    with st.container(border=True):
        st.markdown(verdict.judgment)
    if verdict.bias_flags:
        with st.expander(f"Bias Flags ({len(verdict.bias_flags)})"):
            for b in verdict.bias_flags:
                st.markdown(f"- {b}")
    if verdict.missed_perspectives:
        with st.expander(f"Missed Perspectives ({len(verdict.missed_perspectives)})"):
            for p in verdict.missed_perspectives:
                st.markdown(f"- {p}")
    with st.expander("Reasoning"):
        st.markdown(verdict.reasoning)


# ── Empty state + tabbed results ──────────────────────────────────────────────

_EXAMPLE_QUESTIONS = [
    ("Security", "Is RSA-2048 under threat from quantum computing in the next 5 years?"),
    ("AI", "Will AGI arrive before 2030?"),
    ("Infrastructure", "Should a 12-person team migrate from Docker Swarm to Kubernetes?"),
    ("Work", "Is remote work more productive than office work for knowledge workers?"),
]


def _show_empty_state() -> None:
    st.divider()
    st.markdown("#### Try one of these questions")
    cols = st.columns(2)
    for i, (label, question) in enumerate(_EXAMPLE_QUESTIONS):
        with cols[i % 2]:
            btn_label = f"**{label}:** {question[:70]}…" if len(question) > 70 else f"**{label}:** {question}"
            if st.button(btn_label, key=f"example_{i}", use_container_width=True):
                st.session_state["_prefill"] = question
                st.rerun()


def _show_results_tabbed(session: dict) -> None:
    """Display debate results: summary banner + tabs (Answer first)."""
    final = session["final"]
    synthesis = session["synthesis"]

    # ── Summary Banner ────────────────────────────────────────────────────────
    st.divider()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Consensus", f"{final.consensus_score:.0%}",
              help="Weighted agreement across all agents")
    m2.metric("Confidence", f"{final.confidence:.0%}",
              help="Model's stated confidence in the conclusion")
    m3.metric("Agreement", f"{synthesis.agreement_score:.0%}",
              help="Claude's self-assessment of convergence")
    m4.metric("Runtime", f"{session['elapsed']:.0f}s",
              help=f"Debate ID: {session['debate_id']}")

    if final.recommendation:
        st.info(f"**Recommendation:** {final.recommendation}")

    if final.consensus_score < 0.4 and final.divergence_explanation:
        st.warning(
            f"⚠️ **Significant Divergence** (C = {final.consensus_score:.0%})\n\n"
            f"{final.divergence_explanation}"
        )

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_labels = ["✅ Answer", "🔬 Analysis", "⚔️ Critique"]
    if session.get("judge_verdict"):
        tab_labels.append("🧑‍⚖️ Judge")

    tabs = st.tabs(tab_labels)

    # Answer tab — most important content first
    with tabs[0]:
        with st.container(border=True):
            st.markdown(final.content)
        if final.key_uncertainties or final.next_steps:
            col_u, col_ns = st.columns(2)
            with col_u:
                if final.key_uncertainties:
                    st.markdown("**Key Uncertainties**")
                    for u in final.key_uncertainties:
                        st.markdown(f"- ❓ {u}")
            with col_ns:
                if final.next_steps:
                    st.markdown("**Next Steps**")
                    for i, s in enumerate(final.next_steps, 1):
                        st.markdown(f"{i}. {s}")
        if final.key_disagreements:
            with st.expander(f"Key Disagreements ({len(final.key_disagreements)})"):
                for d in final.key_disagreements:
                    st.markdown(f"- {d}")

    # Analysis tab — all intermediate phases
    with tabs[1]:
        if session.get("decomposition"):
            show_decomposition(session["decomposition"])
            st.divider()
        if session.get("delphi_process"):
            show_delphi(session["delphi_process"])
            st.divider()
        show_phase1(session["logical"], session["factual"])
        if session.get("fact_check_result"):
            st.divider()
            show_fact_check(session["fact_check_result"])
        if session.get("argument_graph"):
            st.divider()
            show_argument_graph(session["argument_graph"])
        if session.get("calibration_record"):
            st.divider()
            show_calibration(
                session["calibration_record"],
                session.get("history_stats"),
            )

    # Critique tab
    with tabs[2]:
        if session.get("rebuttal"):
            show_rebuttal(session["rebuttal"])
            st.divider()
        show_critique(session["synthesis"], session["verification"])

    # Judge tab (conditional)
    if len(tabs) > 3 and session.get("judge_verdict"):
        with tabs[3]:
            show_judge(session["judge_verdict"])


# ── Main debate runner ────────────────────────────────────────────────────────

def _run_debate(
    problem: str,
    mock_gemini: bool,
    rounds: int,
    save: bool,
    adversarial: bool,
    grounded: bool,
    multi_turn: bool,
    judge: bool,
    moa: bool,
    fact_check: bool,
    decompose: bool,
    arg_graph: bool,
    delphi_rounds: int,
    calibrate: bool,
    context_text: str = "",
    persona: str = "",
) -> None:
    from debate.debate_manager import (
        DebateManager,
        calculate_agreement_score,
        compute_calibration_stats,
        load_calibration_history,
        save_calibration_history,
    )
    from debate.models import DebateResult
    from debate.output_formatter import OutputFormatter

    debate_id = f"debate-{uuid.uuid4().hex[:8]}"
    start = time.monotonic()

    mgr = DebateManager(
        mock_gemini=mock_gemini,
        max_rounds=rounds,
        adversarial=adversarial,
        grounded=grounded,
        multi_turn=multi_turn,
        judge=judge,
        moa=moa,
        fact_check=fact_check,
        decompose=decompose,
        arg_graph=arg_graph,
        delphi_rounds=delphi_rounds,
        calibrate=calibrate,
        context_text=context_text,
        persona=persona,
    )

    # ── Phase 0 ───────────────────────────────────────────────────────────────
    decomposition = None
    if decompose:
        with st.status("Phase 0: Problem Decomposition…", expanded=False) as s:
            decomposition = run_async(mgr.decompose_problem(problem))
            s.update(label="Phase 0 complete ✓", state="complete")

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    delphi_process = None
    if delphi_rounds > 0:
        with st.status(f"Phase 1: Delphi ({delphi_rounds} rounds)…", expanded=False) as s:
            logical, factual, delphi_process = run_async(
                mgr.run_delphi(problem, decomposition=decomposition)
            )
            s.update(label="Phase 1 complete (Delphi) ✓", state="complete")
    else:
        label = "MoA" if moa else ("PRO/CONTRA" if adversarial else "Gemini Thinking + Pro")
        with st.status(f"Phase 1: {label} in parallel…", expanded=False) as s:
            logical, factual = run_async(
                mgr.get_initial_takes(problem, decomposition=decomposition)
            )
            s.update(label="Phase 1 complete ✓", state="complete")

    # ── Phase 1.5 ─────────────────────────────────────────────────────────────
    fact_check_result = None
    if fact_check:
        with st.status("Phase 1.5: Claim-Level Fact-Check…", expanded=False) as s:
            fact_check_result = run_async(mgr.run_fact_check(problem, logical, factual))
            s.update(label="Phase 1.5 complete ✓", state="complete")

    # ── Phase 1.6 ─────────────────────────────────────────────────────────────
    argument_graph = None
    if arg_graph:
        with st.status("Phase 1.6: Argument Graph…", expanded=False) as s:
            argument_graph = run_async(mgr.build_argument_graph(problem, logical, factual))
            s.update(label="Phase 1.6 complete ✓", state="complete")

    # ── Calibration extraction ────────────────────────────────────────────────
    calibration_record = None
    history_stats = None
    if calibrate:
        with st.status("Extracting calibration claims…", expanded=False) as s:
            calibration_record = run_async(
                mgr.extract_calibration(debate_id, problem, logical, factual,
                                        fact_check=fact_check_result)
            )
            history = load_calibration_history()
            history_stats = compute_calibration_stats(history) if history else None
            save_calibration_history(calibration_record)
            s.update(label="Calibration complete ✓", state="complete")

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    with st.status("Phase 2: Adversarial Critique Loop…", expanded=False) as s:
        synthesis, rebuttal, verification = run_async(
            mgr.run_critique_loop(problem, logical, factual, fact_check=fact_check_result)
        )
        s.update(label="Phase 2 complete ✓", state="complete")

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    with st.status("Phase 3: Final Consensus Answer…", expanded=False) as s:
        final = run_async(
            mgr.get_final_answer(problem, logical, factual, synthesis, verification,
                                 rebuttal=rebuttal, fact_check=fact_check_result)
        )
        s.update(label="Phase 3 complete ✓", state="complete")

    elapsed = time.monotonic() - start

    # ── Phase 4 ───────────────────────────────────────────────────────────────
    judge_verdict = None
    if judge:
        with st.status("Phase 4: Skeptical Judge…", expanded=False) as s:
            judge_verdict = run_async(
                mgr.get_judge_verdict(problem, logical, factual, synthesis,
                                      verification, final, rebuttal=rebuttal,
                                      fact_check=fact_check_result)
            )
            s.update(label="Phase 4 complete ✓", state="complete")

    # ── Persist all results for tabbed display ────────────────────────────────
    st.session_state["last_debate"] = {
        "problem": problem, "debate_id": debate_id,
        "logical": logical, "factual": factual,
        "synthesis": synthesis, "verification": verification,
        "final": final, "elapsed": elapsed,
        "decomposition": decomposition, "fact_check_result": fact_check_result,
        "argument_graph": argument_graph, "delphi_process": delphi_process,
        "calibration_record": calibration_record, "rebuttal": rebuttal,
        "judge_verdict": judge_verdict,
        "history_stats": history_stats,
    }

    # ── Save report ───────────────────────────────────────────────────────────
    if save:
        result = DebateResult(
            problem=problem,
            decomposition=decomposition,
            logical_analysis=logical,
            factual_context=factual,
            fact_check=fact_check_result,
            argument_graph=argument_graph,
            delphi_process=delphi_process,
            calibration=calibration_record,
            critique=synthesis,
            rebuttal=rebuttal,
            verification=verification,
            final_answer=final,
            judge=judge_verdict,
        )
        fmt = OutputFormatter()
        report_path = fmt.save_report(result, elapsed)
        st.success(f"Report saved: `{report_path}`")

        report_md = Path(report_path).read_text(encoding="utf-8")
        st.download_button(
            label="⬇ Download Report (.md)",
            data=report_md,
            file_name=Path(report_path).name,
            mime="text/markdown",
        )


# ── Cost estimate helper ──────────────────────────────────────────────────────

def _ui_cost_estimate(rounds, moa, fact_check, decompose, arg_graph,
                      delphi_rounds, judge, calibrate, mock_gemini):
    base_usd = 0.04; base_s = 30
    if rounds > 1:   base_usd += (rounds - 1) * 0.01; base_s += (rounds - 1) * 10
    if moa:          base_usd += 0.01; base_s += 5
    if fact_check:   base_usd += 0.02; base_s += 15
    if decompose:    base_usd += 0.01; base_s += 10
    if arg_graph:    base_usd += 0.02; base_s += 15
    if delphi_rounds > 0: base_usd += delphi_rounds * 0.03; base_s += delphi_rounds * 20
    if judge:        base_usd += 0.02; base_s += 15
    if calibrate:    base_usd += 0.01; base_s += 10
    mock_note = " (mock)" if mock_gemini else ""
    return f"~{base_s}s · ~${base_usd:.2f}{mock_note}"


# ── Preset definitions (mirrors cli.py _PRESETS) ──────────────────────────────

_UI_PRESETS = {
    "quick":    dict(rounds=1, adversarial=False, grounded=False, multi_turn=False,
                     judge=False, moa=False, fact_check=False, decompose=False,
                     arg_graph=False, delphi_rounds=0, calibrate=False),
    "standard": dict(rounds=1, adversarial=False, grounded=False, multi_turn=False,
                     judge=True, moa=False, fact_check=True, decompose=False,
                     arg_graph=False, delphi_rounds=0, calibrate=False),
    "deep":     dict(rounds=2, adversarial=False, grounded=False, multi_turn=True,
                     judge=True, moa=False, fact_check=True, decompose=True,
                     arg_graph=True, delphi_rounds=0, calibrate=True),
}


# ── Post-debate chat ──────────────────────────────────────────────────────────

def _build_debate_system_prompt(session: dict) -> str:
    lines = [
        "You are a debate analyst and thinking partner. Below is a complete multi-agent debate transcript.",
        "Answer questions concisely. Reference specific phases when relevant.",
        "Help the user explore reasoning, reframe conclusions for different audiences, and explore 'what if' scenarios.",
        "Do NOT repeat large sections of the transcript verbatim unless explicitly asked.",
        "",
        "═══ DEBATE TRANSCRIPT ═══",
        f"Problem: {session['problem']}",
        "",
    ]

    if session.get("decomposition"):
        d = session["decomposition"]
        lines.append(f"Phase 0 — Problem Decomposition (complexity: {d.complexity})")
        for sq in d.sub_questions:
            lines.append(f"  [{sq.aspect}] {sq.question}")
        lines.append("")

    logical = session.get("logical")
    factual = session.get("factual")
    if logical:
        lines += [
            f"Phase 1A — Logical Analysis ({logical.model_id}, confidence: {logical.confidence:.0%})",
            logical.content[:1500], "",
        ]
    if factual:
        lines += [
            f"Phase 1B — Factual Context ({factual.model_id}, confidence: {factual.confidence:.0%})",
            factual.content[:1500], "",
        ]

    if session.get("fact_check_result"):
        fc = session["fact_check_result"]
        lines += [
            f"Phase 1.5 — Fact-Check: {fc.confirmed_count} confirmed / {fc.refuted_count} refuted"
            f" / {fc.uncertain_count} uncertain. Reliability: {fc.overall_reliability:.0%}",
            f"  Summary: {fc.summary}", "",
        ]

    synthesis = session.get("synthesis")
    if synthesis:
        lines.append(f"Phase 2 — Critique (agreement: {synthesis.agreement_score:.0%})")
        if synthesis.contradictions:
            lines.append(f"  {len(synthesis.contradictions)} contradiction(s):")
            for c in synthesis.contradictions[:3]:
                lines.append(f"    [{c.severity}] A: {c.claim_a[:80]} | B: {c.claim_b[:80]}")
        lines += [f"  Synthesis: {synthesis.synthesis_draft[:800]}", ""]

    if session.get("verification"):
        v = session["verification"]
        lines.append(f"Verification: {'passed' if v.verified else 'failed'}")
        if v.logical_errors:
            lines.append(f"  Errors: {'; '.join(v.logical_errors[:3])}")
        lines.append("")

    if session.get("rebuttal"):
        rb = session["rebuttal"]
        lines += [
            f"Phase 2b — Rebuttal (position maintained: {rb.rebuttal_score:.0%})",
            rb.rebuttal_content[:600], "",
        ]

    final = session.get("final")
    if final:
        lines += [
            f"Phase 3 — Final Answer (consensus: {final.consensus_score:.0%}, confidence: {final.confidence:.0%})",
            final.content[:2000],
        ]
        if final.recommendation:
            lines.append(f"  Recommendation: {final.recommendation}")
        if final.key_uncertainties:
            lines.append(f"  Key Uncertainties: {'; '.join(final.key_uncertainties)}")
        if final.next_steps:
            lines.append(f"  Next Steps: {'; '.join(final.next_steps)}")
        lines.append("")

    if session.get("judge_verdict"):
        jv = session["judge_verdict"]
        lines += [
            f"Phase 4 — Judge (reliability: {jv.reliability_score:.0%})",
            jv.judgment[:800],
        ]
        if jv.bias_flags:
            lines.append(f"  Bias flags: {'; '.join(jv.bias_flags[:3])}")
        lines.append("")

    lines.append("═══ END TRANSCRIPT ═══")
    return "\n".join(lines)


_CHAT_QUICK_ACTIONS = [
    ("📋 Executive Summary", "Write a concise 3-paragraph executive summary of the debate outcome and recommendation."),
    ("🧱 Steelman minority", "Present the strongest possible version of the minority or dissenting position in this debate."),
    ("📊 Decision memo", "Write a decision memo (max 200 words) suitable for a non-technical decision-maker."),
    ("🔑 Open questions", "List the 5 most important unresolved questions that remain after this debate."),
    ("↩️ What would flip the verdict?", "What single piece of evidence or argument would most likely reverse the consensus conclusion?"),
]


def show_chat_interface(session: dict) -> None:
    st.divider()
    st.subheader("💬 Explore this Debate")
    st.caption(
        f"Ask follow-up questions about: **{session['problem'][:90]}{'…' if len(session['problem']) > 90 else ''}**"
    )

    # Quick-action buttons
    cols = st.columns(len(_CHAT_QUICK_ACTIONS))
    triggered_prompt: str | None = None
    for col, (label, prompt) in zip(cols, _CHAT_QUICK_ACTIONS):
        if col.button(label, use_container_width=True, key=f"qa_{label}"):
            triggered_prompt = prompt

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    # Render existing messages
    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Ask anything about this debate…") or triggered_prompt

    if user_input:
        st.session_state["chat_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        system_prompt = _build_debate_system_prompt(session)

        with st.chat_message("assistant"):
            from debate.config import settings as _cfg
            import anthropic as _ant

            _client = _ant.Anthropic(api_key=_cfg.anthropic_api_key)

            def _stream_gen():
                with _client.messages.stream(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=system_prompt,
                    messages=[
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state["chat_history"]
                    ],
                ) as stream:
                    yield from stream.text_stream

            response = st.write_stream(_stream_gen())

        st.session_state["chat_history"].append({"role": "assistant", "content": response})

    if st.session_state.get("chat_history"):
        # v1.7: Export + Clear buttons
        chat_md = f"# Debate Chat\n\n**Problem:** {session['problem']}\n\n---\n\n"
        for msg in st.session_state["chat_history"]:
            role_label = "**You**" if msg["role"] == "user" else "**Assistant**"
            chat_md += f"{role_label}:\n\n{msg['content']}\n\n---\n\n"

        col_export, col_clear = st.columns(2)
        with col_export:
            st.download_button(
                "📥 Export Chat", chat_md,
                file_name="debate_chat.md", mime="text/markdown",
                use_container_width=True,
            )
        with col_clear:
            if st.button("🗑 Clear chat", key="clear_chat", use_container_width=True):
                st.session_state["chat_history"] = []
                st.rerun()


# ── UI Layout ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Configuration")
    st.divider()

    # v1.4: Mode selector
    st.subheader("Mode")
    mode = st.radio(
        "Preset",
        options=["quick", "standard", "deep", "custom"],
        index=1,
        horizontal=True,
        label_visibility="collapsed",
        help="quick=~30s, standard=~60s (default), deep=~120s, custom=manual flags",
    )

    preset = _UI_PRESETS.get(mode, None)
    _p = preset or {}

    st.divider()
    st.subheader("Base Settings")
    mock_gemini = st.checkbox("Mock Gemini (use Claude)", value=False,
                               help="Replace Gemini with Claude for testing without API key")
    rounds = st.slider("Critique rounds", min_value=1, max_value=5,
                       value=_p.get("rounds", 1),
                       disabled=(mode != "custom"),
                       help="Max rounds in Phase 2 adversarial loop")
    save_report = st.checkbox("Save report (.md)", value=False)

    st.divider()
    _ext_label = "Extensions (custom mode only)" if mode != "custom" else "Extensions"
    _ext_ctx = st.expander(_ext_label, expanded=False) if mode != "custom" else st.container()
    with _ext_ctx:
        adversarial = st.checkbox("Adversarial (PRO/CONTRA)", value=_p.get("adversarial", False),
                                   disabled=(mode != "custom"),
                                   help="Lock Gemini models into opposing PRO and CONTRA positions")
        grounded = st.checkbox("Google Search Grounding", value=_p.get("grounded", False),
                                disabled=(mode != "custom"),
                                help="Gemini Pro uses live Google Search for factual context")
        multi_turn = st.checkbox("Multi-Turn Rebuttal", value=_p.get("multi_turn", False),
                                  disabled=(mode != "custom"),
                                  help="Gemini defends its position after Claude's critique (Phase 2b)")
        judge = st.checkbox("Skeptical Judge (Phase 4)", value=_p.get("judge", False),
                             disabled=(mode != "custom"),
                             help="Independent Claude judge evaluates the full debate")
        moa = st.checkbox("Mixture of Agents (MoA)", value=_p.get("moa", False),
                           disabled=(mode != "custom"),
                           help="Both Gemini models run per role, Claude aggregates")
        fact_check = st.checkbox("Claim-Level Fact-Check", value=_p.get("fact_check", False),
                                  disabled=(mode != "custom"),
                                  help="Claude verifies 6–10 atomic claims after Phase 1 (Phase 1.5)")
        decompose = st.checkbox("Problem Decomposition", value=_p.get("decompose", False),
                                 disabled=(mode != "custom"),
                                 help="Claude breaks problem into sub-questions first (Phase 0)")
        arg_graph = st.checkbox("Argument Graph", value=_p.get("arg_graph", False),
                                 disabled=(mode != "custom"),
                                 help="Formal directed graph of premises, conclusions, evidence (Phase 1.6)")
        delphi_rounds = st.slider("Delphi rounds (0 = off)", min_value=0, max_value=5,
                                   value=_p.get("delphi_rounds", 0),
                                   disabled=(mode != "custom"),
                                   help="Iterative anonymized consensus rounds (replaces standard Phase 1)")
        calibrate = st.checkbox("Calibration Tracking", value=_p.get("calibrate", False),
                                 disabled=(mode != "custom"),
                                 help="Extract probabilistic claims, persist to calibration_history.jsonl")

    st.divider()
    # v1.6: Expert persona
    st.subheader("Expert Persona (optional)")
    persona = st.text_input(
        "Domain",
        placeholder="cybersecurity · finance · medicine · technology · policy · science · or any domain",
        label_visibility="collapsed",
        help="Assigns domain-expert perspectives to Gemini agents (presets: cybersecurity, finance, medicine, technology, policy, science)",
    )

    st.divider()
    # v1.4: Context input (text + file upload)
    st.subheader("Context (optional)")
    context_text = st.text_area(
        "Additional context",
        placeholder="Paste relevant documents, data, or constraints here…",
        height=80,
        label_visibility="collapsed",
        help="Injected into all prompts as grounding context",
    )
    uploaded_files = st.file_uploader(
        "Upload context files",
        type=["pdf", "md", "txt", "markdown"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="PDF, Markdown or plain text — extracted text is appended to context",
    )
    if uploaded_files:
        extracted_parts: list[str] = []
        for uf in uploaded_files:
            try:
                if uf.name.endswith(".pdf"):
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(uf)
                        pages_text = "\n".join(
                            p.extract_text() or "" for p in reader.pages
                        )
                        extracted_parts.append(f"[{uf.name}]\n{pages_text.strip()}")
                    except ImportError:
                        st.warning("pypdf not installed — run `pip install pypdf` to enable PDF upload")
                else:
                    extracted_parts.append(f"[{uf.name}]\n{uf.read().decode('utf-8', errors='replace').strip()}")
            except Exception as exc:
                st.warning(f"Could not read {uf.name}: {exc}")
        if extracted_parts:
            file_context = "\n\n".join(extracted_parts)
            context_text = (context_text + "\n\n" + file_context).strip() if context_text.strip() else file_context
            with st.expander(f"Extracted from {len(uploaded_files)} file(s) — preview"):
                st.text(file_context[:800] + ("…" if len(file_context) > 800 else ""))

    st.divider()
    # v1.4: Cost estimate
    cost_str = _ui_cost_estimate(rounds, moa, fact_check, decompose, arg_graph,
                                  delphi_rounds, judge, calibrate, mock_gemini)
    st.caption(f"💰 Estimated: {cost_str}")

    # v1.4: Load previous debate
    st.divider()
    with st.expander("📂 Load previous debate"):
        from pathlib import Path as _Path
        _reports = sorted(_Path("output").rglob("*_report.md"), reverse=True) if _Path("output").exists() else []
        if _reports:
            _selected = st.selectbox("Report", [r.parent.name for r in _reports[:20]])
            if st.button("Load", key="load_prev"):
                st.info(f"Report: `output/{_selected}/`  \nOpen the .md file to view full results.")
        else:
            st.caption("No saved reports yet.")

# ── Main ──────────────────────────────────────────────────────────────────────

st.title("⚡ Multi-Agent Debate Engine")
st.caption("Gemini Thinking + Pro  ×  Claude Opus 4.6  |  v1.7")

# Prefill support from example questions
_prefill = st.session_state.pop("_prefill", "")

problem = st.text_area(
    "Problem / Question",
    value=_prefill,
    placeholder="Is RSA-2048 under threat from quantum computing in the next 5 years?",
    height=80,
    label_visibility="collapsed",
)

run_btn = st.button("▶ Run Debate", type="primary", disabled=not problem.strip(),
                    use_container_width=True)

if run_btn and problem.strip():
    # API key pre-check
    try:
        from debate.config import settings as _cfg_check
        if not _cfg_check.anthropic_api_key and not mock_gemini:
            st.error("ANTHROPIC_API_KEY not configured. Add it to your .env file or enable **Mock Gemini** mode.")
            st.stop()
    except Exception:
        pass
    # Clear previous chat when a new debate starts
    st.session_state.pop("chat_history", None)
    _run_debate(
        problem=problem.strip(),
        mock_gemini=mock_gemini,
        rounds=rounds,
        save=save_report,
        adversarial=adversarial,
        grounded=grounded,
        multi_turn=multi_turn,
        judge=judge,
        moa=moa,
        fact_check=fact_check,
        decompose=decompose,
        arg_graph=arg_graph,
        delphi_rounds=delphi_rounds,
        calibrate=calibrate,
        context_text=context_text,
        persona=persona,
    )

# Show tabbed results + chat whenever a debate result is in session state
if st.session_state.get("last_debate"):
    _show_results_tabbed(st.session_state["last_debate"])
    show_chat_interface(st.session_state["last_debate"])
elif not run_btn:
    _show_empty_state()
