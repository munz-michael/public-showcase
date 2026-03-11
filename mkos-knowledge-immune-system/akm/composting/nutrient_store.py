"""SQLite store for composted nutrients."""

from __future__ import annotations

import sqlite3

from akm.composting.decomposer import Nutrient
from akm.search.engine import sanitize_fts_query


class NutrientStore:
    """CRUD + FTS search for extracted nutrients."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert(
        self,
        nutrient: Nutrient,
        source_chunk_id: int | None = None,
        source_document_id: int | None = None,
    ) -> int:
        cursor = self.conn.execute(
            "INSERT INTO nutrients "
            "(source_chunk_id, source_document_id, nutrient_type, title, content, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                source_chunk_id,
                source_document_id,
                nutrient.nutrient_type,
                nutrient.title,
                nutrient.content,
                nutrient.confidence,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """FTS search over nutrients."""
        fts_query = sanitize_fts_query(query)
        rows = self.conn.execute(
            "SELECT n.*, rank FROM nutrients n "
            "JOIN nutrients_fts ON nutrients_fts.rowid = n.id "
            "WHERE nutrients_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (fts_query, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_type(self, nutrient_type: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM nutrients WHERE nutrient_type = ? "
            "ORDER BY confidence DESC, usage_count DESC LIMIT ?",
            (nutrient_type, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM nutrients ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def increment_usage(self, nutrient_id: int) -> None:
        self.conn.execute(
            "UPDATE nutrients SET usage_count = usage_count + 1 WHERE id = ?",
            (nutrient_id,),
        )

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) as c FROM nutrients").fetchone()["c"]
        by_type = self.conn.execute(
            "SELECT nutrient_type, COUNT(*) as c, AVG(confidence) as avg_conf "
            "FROM nutrients GROUP BY nutrient_type"
        ).fetchall()
        top_used = self.conn.execute(
            "SELECT title, nutrient_type, usage_count FROM nutrients "
            "WHERE usage_count > 0 ORDER BY usage_count DESC LIMIT 5"
        ).fetchall()

        return {
            "total": total,
            "by_type": {r["nutrient_type"]: {"count": r["c"], "avg_confidence": round(r["avg_conf"], 3)} for r in by_type},
            "top_used": [dict(r) for r in top_used],
        }
