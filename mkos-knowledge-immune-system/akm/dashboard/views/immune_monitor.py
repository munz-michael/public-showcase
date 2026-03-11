"""Immunsystem Monitor - Threat-Erkennung und Gesundheitsstatus."""

from __future__ import annotations

import json
import sqlite3

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


THREAT_COLORS = {
    "hallucination": "#E74C3C",
    "staleness": "#F39C12",
    "bias": "#9B59B6",
    "contradiction": "#E67E22",
    "healthy": "#2ECC71",
}


def render(conn: sqlite3.Connection) -> None:
    st.title("Immunsystem Monitor")

    # --- Health overview ---
    total_chunks = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
    total_scans = conn.execute("SELECT COUNT(*) as c FROM immune_scan_results").fetchone()["c"]
    unresolved = conn.execute(
        "SELECT COUNT(*) as c FROM immune_scan_results WHERE resolved = 0"
    ).fetchone()["c"]
    total_patterns = conn.execute("SELECT COUNT(*) as c FROM immune_patterns").fetchone()["c"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Chunks gesamt", f"{total_chunks:,}")
    col2.metric("Scans durchgefuehrt", total_scans)
    col3.metric("Offene Threats", unresolved, delta=-unresolved if unresolved else None,
                delta_color="inverse")
    col4.metric("Immune Patterns", total_patterns)

    st.divider()

    # --- Threat distribution ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Threats nach Typ")
        threat_rows = conn.execute(
            "SELECT threat_type, COUNT(*) as c, AVG(confidence) as avg_conf "
            "FROM immune_scan_results GROUP BY threat_type ORDER BY c DESC"
        ).fetchall()

        if threat_rows:
            types = [r["threat_type"] for r in threat_rows]
            counts = [r["c"] for r in threat_rows]
            colors = [THREAT_COLORS.get(t, "#888") for t in types]

            fig = go.Figure(data=[go.Bar(
                x=types, y=counts,
                marker_color=colors,
                text=counts, textposition="auto",
            )])
            fig.update_layout(
                xaxis_title="Threat-Typ", yaxis_title="Anzahl",
                showlegend=False, height=350,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Noch keine Scan-Ergebnisse vorhanden.")

    with col_right:
        st.subheader("Durchschnittliche Konfidenz")
        if threat_rows:
            fig = go.Figure(data=[go.Bar(
                x=[r["threat_type"] for r in threat_rows],
                y=[r["avg_conf"] for r in threat_rows],
                marker_color=[THREAT_COLORS.get(r["threat_type"], "#888") for r in threat_rows],
                text=[f"{r['avg_conf']:.2f}" for r in threat_rows],
                textposition="auto",
            )])
            fig.update_layout(
                xaxis_title="Threat-Typ", yaxis_title="Konfidenz",
                yaxis_range=[0, 1], showlegend=False, height=350,
            )
            st.plotly_chart(fig, use_container_width=True)

    # --- Immune Memory / Patterns ---
    st.divider()
    st.subheader("Immune Memory - Pattern Fitness")

    pattern_rows = conn.execute(
        "SELECT pattern_type, pattern_signature, fitness_score, times_detected, "
        "times_effective, created_at, last_seen_at "
        "FROM immune_patterns ORDER BY fitness_score DESC LIMIT 50"
    ).fetchall()

    if pattern_rows:
        col_radar, col_table = st.columns([1, 2])

        with col_radar:
            # Fitness by pattern type
            type_fitness = {}
            for r in pattern_rows:
                ptype = r["pattern_type"]
                if ptype not in type_fitness:
                    type_fitness[ptype] = []
                type_fitness[ptype].append(r["fitness_score"])

            categories = list(type_fitness.keys())
            avg_fitness = [sum(v) / len(v) for v in type_fitness.values()]

            fig = go.Figure(data=go.Scatterpolar(
                r=avg_fitness + [avg_fitness[0]] if avg_fitness else [],
                theta=categories + [categories[0]] if categories else [],
                fill="toself",
                marker_color="#3498DB",
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
                showlegend=False, height=300,
                title="Avg. Fitness pro Typ",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_table:
            st.dataframe(
                [{
                    "Typ": r["pattern_type"],
                    "Signatur": r["pattern_signature"][:60],
                    "Fitness": f"{r['fitness_score']:.3f}",
                    "Erkannt": r["times_detected"],
                    "Effektiv": r["times_effective"],
                    "Zuletzt": r["last_seen_at"][:10] if r["last_seen_at"] else "-",
                } for r in pattern_rows],
                use_container_width=True,
                height=300,
            )
    else:
        st.info("Noch keine Immune Patterns vorhanden. Fuehre einen Immune Scan durch.")

    # --- Recent scan results ---
    st.divider()
    st.subheader("Letzte Scan-Ergebnisse")

    recent_rows = conn.execute(
        "SELECT isr.id, isr.chunk_id, isr.threat_type, isr.threat_description, "
        "isr.confidence, isr.resolved, isr.scanned_at, "
        "c.heading "
        "FROM immune_scan_results isr "
        "LEFT JOIN chunks c ON c.id = isr.chunk_id "
        "ORDER BY isr.scanned_at DESC LIMIT 25"
    ).fetchall()

    if recent_rows:
        for row in recent_rows:
            color = THREAT_COLORS.get(row["threat_type"], "#888")
            status = "resolved" if row["resolved"] else "offen"
            heading = row["heading"][:40] if row["heading"] else f"Chunk {row['chunk_id']}"

            with st.expander(
                f"{'✅' if row['resolved'] else '⚠️'} [{row['threat_type']}] "
                f"{heading} - Konfidenz: {row['confidence']:.2f}"
            ):
                st.markdown(f"**Typ:** {row['threat_type']}")
                st.markdown(f"**Konfidenz:** {row['confidence']:.2f}")
                st.markdown(f"**Status:** {status}")
                st.markdown(f"**Beschreibung:** {row['threat_description']}")
                st.markdown(f"**Gescannt:** {row['scanned_at']}")
    else:
        st.info("Noch keine Scan-Ergebnisse. Fuehre `python -m akm immune-scan` aus.")
