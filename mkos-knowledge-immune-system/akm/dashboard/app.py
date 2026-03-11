"""AKM Dashboard - Hauptapplikation."""

from __future__ import annotations

import os
import sqlite3

import streamlit as st

from akm.config import Config


def get_connection() -> sqlite3.Connection:
    """Get a read-only SQLite connection."""
    config = Config.from_env()
    if not os.path.exists(config.db_path):
        st.error(f"Datenbank nicht gefunden: {config.db_path}")
        st.info("Fuehre zuerst `python -m akm setup` aus.")
        st.stop()
    conn = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> None:
    st.set_page_config(
        page_title="AKM Dashboard",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.sidebar.title("AKM Dashboard")
    page = st.sidebar.radio(
        "Navigation",
        ["Uebersicht", "Knowledge Graph", "Immunsystem", "Benchmarks"],
    )

    conn = get_connection()

    try:
        if page == "Uebersicht":
            from akm.dashboard.views.overview import render
            render(conn)
        elif page == "Knowledge Graph":
            from akm.dashboard.views.knowledge_graph import render
            render(conn)
        elif page == "Immunsystem":
            from akm.dashboard.views.immune_monitor import render
            render(conn)
        elif page == "Benchmarks":
            from akm.dashboard.views.benchmarks import render
            render(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
