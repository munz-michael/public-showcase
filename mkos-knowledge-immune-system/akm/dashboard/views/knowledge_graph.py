"""Knowledge Graph - Interaktive Visualisierung der Wissensbeziehungen."""

from __future__ import annotations

import sqlite3

import streamlit as st
from streamlit_agraph import agraph, Config as AgraphConfig, Edge, Node


def render(conn: sqlite3.Connection) -> None:
    st.title("Knowledge Graph")

    # Sidebar filters
    projects = conn.execute("SELECT id, name, slug FROM projects ORDER BY name").fetchall()
    project_names = ["Alle"] + [r["name"] for r in projects]
    selected_project = st.sidebar.selectbox("Projekt filtern", project_names)

    max_nodes = st.sidebar.slider("Max. Knoten", 10, 200, 50)
    show_cross_refs = st.sidebar.checkbox("Querverweise anzeigen", value=True)
    show_contradictions = st.sidebar.checkbox("Widersprueche anzeigen", value=True)

    # Build graph
    nodes = []
    edges = []
    node_ids = set()

    # Get project filter
    project_filter = ""
    params: list = []
    if selected_project != "Alle":
        project_filter = "AND p.slug = ?"
        match = [r for r in projects if r["name"] == selected_project]
        if match:
            params.append(match[0]["slug"])

    # Fetch chunks with project info
    chunk_rows = conn.execute(
        f"SELECT c.id, c.heading, c.token_count, p.name as project_name, p.slug "
        f"FROM chunks c "
        f"JOIN documents d ON d.id = c.document_id "
        f"JOIN projects p ON p.id = d.project_id "
        f"WHERE 1=1 {project_filter} "
        f"ORDER BY c.id LIMIT ?",
        (*params, max_nodes),
    ).fetchall()

    # Color map for projects
    project_colors = {}
    palette = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
               "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9"]
    for i, p in enumerate(projects):
        project_colors[p["slug"]] = palette[i % len(palette)]

    for row in chunk_rows:
        label = row["heading"][:30] if row["heading"] else f"Chunk {row['id']}"
        color = project_colors.get(row["slug"], "#888888")
        nodes.append(Node(
            id=str(row["id"]),
            label=label,
            size=max(10, min(30, row["token_count"] // 20)),
            color=color,
            title=f"{row['project_name']}\n{row['heading']}\n{row['token_count']} tokens",
        ))
        node_ids.add(str(row["id"]))

    # Cross-references from fermentation
    if show_cross_refs:
        ref_rows = conn.execute(
            "SELECT fcr.fermentation_id, fcr.related_chunk_id, "
            "fcr.relationship_type, fcr.similarity_score, fc.title "
            "FROM fermentation_cross_refs fcr "
            "JOIN fermentation_chamber fc ON fc.id = fcr.fermentation_id "
            "WHERE fcr.relationship_type != 'contradicts' "
            "LIMIT 200"
        ).fetchall()

        for row in ref_rows:
            ferm_id = f"ferm_{row['fermentation_id']}"
            chunk_id = str(row["related_chunk_id"])

            if ferm_id not in node_ids:
                label = row["title"][:25] if row["title"] else f"Ferm {row['fermentation_id']}"
                nodes.append(Node(
                    id=ferm_id, label=label, size=15,
                    color="#FFD700", shape="diamond",
                    title=f"Fermentation: {row['title']}",
                ))
                node_ids.add(ferm_id)

            if chunk_id in node_ids:
                edges.append(Edge(
                    source=ferm_id, target=chunk_id,
                    label=row["relationship_type"][:15],
                    color="#4ECDC4", width=max(1, row["similarity_score"] * 3),
                ))

    # Contradictions
    if show_contradictions:
        contra_rows = conn.execute(
            "SELECT fcr.fermentation_id, fcr.related_chunk_id, "
            "fcr.explanation, fc.title "
            "FROM fermentation_cross_refs fcr "
            "JOIN fermentation_chamber fc ON fc.id = fcr.fermentation_id "
            "WHERE fcr.relationship_type = 'contradicts' "
            "LIMIT 100"
        ).fetchall()

        for row in contra_rows:
            ferm_id = f"ferm_{row['fermentation_id']}"
            chunk_id = str(row["related_chunk_id"])

            if ferm_id not in node_ids:
                label = row["title"][:25] if row["title"] else f"Ferm {row['fermentation_id']}"
                nodes.append(Node(
                    id=ferm_id, label=label, size=15,
                    color="#FFD700", shape="diamond",
                ))
                node_ids.add(ferm_id)

            if chunk_id in node_ids:
                edges.append(Edge(
                    source=ferm_id, target=chunk_id,
                    label="widerspricht",
                    color="#FF4444", width=3, dashes=True,
                ))

    if not nodes:
        st.info("Keine Daten fuer den Knowledge Graph vorhanden.")
        return

    # Render graph
    config = AgraphConfig(
        width=1200,
        height=700,
        directed=False,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7DC6F",
        collapsible=True,
    )

    st.info(f"{len(nodes)} Knoten, {len(edges)} Kanten")
    agraph(nodes=nodes, edges=edges, config=config)

    # Legend
    st.divider()
    st.subheader("Legende")
    legend_cols = st.columns(min(len(project_colors), 5))
    for i, (slug, color) in enumerate(project_colors.items()):
        col = legend_cols[i % len(legend_cols)]
        col.markdown(f"<span style='color:{color}'>&#9632;</span> {slug}", unsafe_allow_html=True)
    st.markdown("&#9670; Gelb = Fermentation Item | <span style='color:#FF4444'>---</span> Rot = Widerspruch", unsafe_allow_html=True)
