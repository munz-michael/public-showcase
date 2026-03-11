"""Uebersicht - Dashboard-Startseite mit KPIs und Projektstatistiken."""

from __future__ import annotations

import sqlite3

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


def render(conn: sqlite3.Connection) -> None:
    st.title("AKM Wissensbasis - Uebersicht")

    # --- KPI Row ---
    projects = conn.execute("SELECT COUNT(*) as c FROM projects").fetchone()["c"]
    documents = conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
    chunks = conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
    tokens = conn.execute("SELECT COALESCE(SUM(token_count), 0) as c FROM chunks").fetchone()["c"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Projekte", projects)
    col2.metric("Dokumente", documents)
    col3.metric("Chunks", f"{chunks:,}")
    col4.metric("Tokens", f"{tokens:,}")

    st.divider()

    # --- Projects breakdown ---
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Chunks pro Projekt")
        rows = conn.execute(
            "SELECT p.name, COUNT(c.id) as chunk_count "
            "FROM projects p "
            "JOIN documents d ON d.project_id = p.id "
            "JOIN chunks c ON c.document_id = d.id "
            "GROUP BY p.id ORDER BY chunk_count DESC"
        ).fetchall()
        if rows:
            fig = px.bar(
                x=[r["name"] for r in rows],
                y=[r["chunk_count"] for r in rows],
                labels={"x": "Projekt", "y": "Chunks"},
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Daten vorhanden.")

    with col_right:
        st.subheader("Dateitypen")
        type_rows = conn.execute(
            "SELECT file_type, COUNT(*) as c FROM documents GROUP BY file_type"
        ).fetchall()
        if type_rows:
            fig = px.pie(
                names=[r["file_type"] for r in type_rows],
                values=[r["c"] for r in type_rows],
            )
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Keine Daten vorhanden.")

    # --- Composting & Fermentation status ---
    st.divider()
    col_comp, col_ferm = st.columns(2)

    with col_comp:
        st.subheader("Composting")
        nutrients = conn.execute("SELECT COUNT(*) as c FROM nutrients").fetchone()["c"]
        composted = conn.execute("SELECT COUNT(*) as c FROM compost_log").fetchone()["c"]

        c1, c2 = st.columns(2)
        c1.metric("Naehrstoffe extrahiert", nutrients)
        c2.metric("Chunks kompostiert", composted)

        # Nutrient types
        nt_rows = conn.execute(
            "SELECT nutrient_type, COUNT(*) as c FROM nutrients GROUP BY nutrient_type"
        ).fetchall()
        if nt_rows:
            fig = px.bar(
                x=[r["nutrient_type"] for r in nt_rows],
                y=[r["c"] for r in nt_rows],
                labels={"x": "Typ", "y": "Anzahl"},
            )
            fig.update_layout(showlegend=False, height=250)
            st.plotly_chart(fig, use_container_width=True)

    with col_ferm:
        st.subheader("Fermentation")
        fermenting = conn.execute(
            "SELECT COUNT(*) as c FROM fermentation_chamber WHERE status = 'fermenting'"
        ).fetchone()["c"]
        promoted = conn.execute(
            "SELECT COUNT(*) as c FROM fermentation_chamber WHERE status = 'promoted'"
        ).fetchone()["c"]
        rejected = conn.execute(
            "SELECT COUNT(*) as c FROM fermentation_chamber WHERE status = 'rejected'"
        ).fetchone()["c"]

        c1, c2, c3 = st.columns(3)
        c1.metric("Fermentierend", fermenting)
        c2.metric("Promoted", promoted)
        c3.metric("Rejected", rejected)

        status_rows = conn.execute(
            "SELECT status, COUNT(*) as c FROM fermentation_chamber GROUP BY status"
        ).fetchall()
        if status_rows:
            fig = px.pie(
                names=[r["status"] for r in status_rows],
                values=[r["c"] for r in status_rows],
            )
            fig.update_layout(height=250)
            st.plotly_chart(fig, use_container_width=True)
