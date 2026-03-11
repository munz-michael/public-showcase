"""Benchmark Charts - Vergleich der MKOS-Komponenten."""

from __future__ import annotations

import json
import sqlite3

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render(conn: sqlite3.Connection) -> None:
    st.title("Benchmark Ergebnisse")

    # Load benchmark runs
    runs = conn.execute(
        "SELECT id, benchmark_name, component, variant, metrics_json, "
        "run_duration_seconds, run_at "
        "FROM benchmark_runs ORDER BY run_at DESC"
    ).fetchall()

    if not runs:
        st.info("Noch keine Benchmark-Ergebnisse. Fuehre `python -m akm benchmark` aus.")
        return

    # --- Run selector ---
    run_dates = list(dict.fromkeys(r["run_at"][:19] for r in runs))
    selected_run = st.sidebar.selectbox("Benchmark Run", run_dates)

    filtered = [r for r in runs if r["run_at"][:19] == selected_run]

    # --- Summary metrics ---
    total_duration = sum(r["run_duration_seconds"] for r in filtered)
    st.metric("Gesamtdauer", f"{total_duration:.1f}s")

    # --- Immune benchmark ---
    immune_runs = [r for r in filtered if r["component"] == "immune"]
    if immune_runs:
        st.divider()
        st.subheader("Immunsystem Benchmark")

        metrics = json.loads(immune_runs[0]["metrics_json"])

        # F1 comparison bar chart
        strategies = []
        f1_scores = []
        precisions = []
        recalls = []

        for key in ["no_immune", "simple_heuristic", "llm_few_shot", "mkos_ais"]:
            if key in metrics:
                m = metrics[key]
                label = {
                    "no_immune": "No Immune",
                    "simple_heuristic": "Heuristik",
                    "llm_few_shot": "LLM Few-Shot",
                    "mkos_ais": "MKOS AIS",
                }.get(key, key)
                strategies.append(label)
                f1_scores.append(m.get("f1", 0))
                precisions.append(m.get("precision", 0))
                recalls.append(m.get("recall", 0))

        if strategies:
            fig = go.Figure(data=[
                go.Bar(name="F1", x=strategies, y=f1_scores,
                       marker_color="#3498DB", text=[f"{v:.3f}" for v in f1_scores],
                       textposition="auto"),
                go.Bar(name="Precision", x=strategies, y=precisions,
                       marker_color="#2ECC71", text=[f"{v:.3f}" for v in precisions],
                       textposition="auto"),
                go.Bar(name="Recall", x=strategies, y=recalls,
                       marker_color="#E74C3C", text=[f"{v:.3f}" for v in recalls],
                       textposition="auto"),
            ])
            fig.update_layout(
                barmode="group", height=400,
                yaxis_range=[0, 1.05],
                title="Strategie-Vergleich: F1 / Precision / Recall",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Per-class F1 for AIS
        ais_metrics = metrics.get("mkos_ais", {})
        per_class = ais_metrics.get("per_class", {})
        if per_class:
            st.subheader("AIS Per-Class F1")

            threat_colors = {
                "hallucination": "#E74C3C",
                "staleness": "#F39C12",
                "bias": "#9B59B6",
                "contradiction": "#E67E22",
                "healthy": "#2ECC71",
            }

            classes = list(per_class.keys())
            class_f1 = []
            for cls in classes:
                val = per_class[cls]
                if isinstance(val, dict):
                    class_f1.append(val.get("f1", 0))
                else:
                    class_f1.append(val)

            colors = [threat_colors.get(c, "#888") for c in classes]

            fig = go.Figure(data=[go.Bar(
                x=classes, y=class_f1,
                marker_color=colors,
                text=[f"{v:.3f}" for v in class_f1],
                textposition="auto",
            )])
            fig.update_layout(
                yaxis_range=[0, 1.05], height=350,
                title="F1-Score pro Threat-Klasse",
            )
            st.plotly_chart(fig, use_container_width=True)

        # Groundedness & Retrieval
        col_g, col_r = st.columns(2)

        with col_g:
            ground = metrics.get("groundedness", {})
            if ground:
                st.subheader("Groundedness")
                g1, g2 = st.columns(2)
                g1.metric("Citation Accuracy",
                          f"{ground.get('citation_accuracy', 0):.1%}")
                g2.metric("Avg. Overlap",
                          f"{ground.get('avg_word_overlap', 0):.3f}")

        with col_r:
            retrieval = metrics.get("retrieval_quality", {})
            if retrieval:
                st.subheader("Retrieval Quality")
                r1, r2 = st.columns(2)
                r1.metric("Hit Rate",
                          f"{retrieval.get('hit_rate', 0):.1%}")
                r2.metric("MRR",
                          f"{retrieval.get('mrr', 0):.3f}")

        # Latency
        latency = metrics.get("latency", {})
        if latency:
            st.subheader("Latenz")
            lat_cols = st.columns(4)
            lat_cols[0].metric("P50", f"{latency.get('p50', 0):.2f}s")
            lat_cols[1].metric("P90", f"{latency.get('p90', 0):.2f}s")
            lat_cols[2].metric("P95", f"{latency.get('p95', 0):.2f}s")
            lat_cols[3].metric("P99", f"{latency.get('p99', 0):.2f}s")

    # --- Composting benchmark ---
    comp_runs = [r for r in filtered if r["component"] == "composting"]
    if comp_runs:
        st.divider()
        st.subheader("Composting Benchmark")
        metrics = json.loads(comp_runs[0]["metrics_json"])

        mkos = metrics.get("mkos_composting", {})
        if mkos:
            c1, c2, c3 = st.columns(3)
            c1.metric("Chunks kompostiert", mkos.get("chunks_composted", 0))
            c2.metric("Naehrstoffe extrahiert", mkos.get("nutrients_extracted", 0))
            c3.metric("Enrichments", mkos.get("enrichments_applied", 0))

        density = {k: v for k, v in metrics.items()
                   if k not in ("baseline_archive_only", "mkos_composting")}
        if density:
            st.json(density)

    # --- Fermentation benchmark ---
    ferm_runs = [r for r in filtered if r["component"] == "fermentation"]
    if ferm_runs:
        st.divider()
        st.subheader("Fermentation Benchmark")
        metrics = json.loads(ferm_runs[0]["metrics_json"])

        immediate = metrics.get("immediate_integration", {})
        fermented = metrics.get("fermented_integration", {})

        if immediate and fermented:
            fig = go.Figure(data=[
                go.Bar(
                    name="Immediate",
                    x=["Widersprueche erkannt", "Cross-Refs"],
                    y=[immediate.get("contradictions_detected", 0),
                       immediate.get("cross_refs_found", 0)],
                    marker_color="#E74C3C",
                ),
                go.Bar(
                    name="Fermented",
                    x=["Widersprueche erkannt", "Cross-Refs"],
                    y=[fermented.get("contradictions_detected", 0),
                       fermented.get("cross_refs_found", 0)],
                    marker_color="#2ECC71",
                ),
            ])
            fig.update_layout(barmode="group", height=350,
                              title="Immediate vs. Fermented Integration")
            st.plotly_chart(fig, use_container_width=True)

    # --- Raw JSON ---
    with st.expander("Rohdaten (JSON)"):
        for r in filtered:
            st.markdown(f"**{r['component']}** ({r['variant']})")
            st.json(json.loads(r["metrics_json"]))
