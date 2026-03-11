"""Fermentation chamber -- staging area for new knowledge."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class FermentingItem:
    id: int
    raw_content: str
    title: str
    source_path: str
    status: str
    confidence_score: float
    fermentation_started_at: str
    fermentation_duration_hours: float
    cross_ref_count: int
    contradiction_count: int
    enrichment_notes: str


class FermentationChamber:
    """Manages the fermentation staging area."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        default_duration_hours: float = 24.0,
    ) -> None:
        self.conn = conn
        self.default_duration_hours = default_duration_hours

    def ingest(
        self,
        content: str,
        title: str = "",
        source_path: str = "",
        duration_hours: float | None = None,
    ) -> int:
        """Add new content to the fermentation chamber."""
        cursor = self.conn.execute(
            "INSERT INTO fermentation_chamber "
            "(raw_content, title, source_path, fermentation_duration_hours) "
            "VALUES (?, ?, ?, ?)",
            (content, title, source_path,
             duration_hours if duration_hours is not None else self.default_duration_hours),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def get_by_id(self, fermentation_id: int) -> FermentingItem | None:
        row = self.conn.execute(
            "SELECT * FROM fermentation_chamber WHERE id = ?",
            (fermentation_id,),
        ).fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def get_fermenting(self) -> list[FermentingItem]:
        rows = self.conn.execute(
            "SELECT * FROM fermentation_chamber WHERE status = 'fermenting' "
            "ORDER BY fermentation_started_at ASC"
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_ready(self) -> list[FermentingItem]:
        """Return items whose fermentation duration has elapsed."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM fermentation_chamber "
            "WHERE status = 'fermenting' "
            "AND datetime(fermentation_started_at, '+' || CAST(fermentation_duration_hours AS TEXT) || ' hours') <= ?",
            (now,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def update_confidence(
        self, fermentation_id: int, new_score: float, notes: str = ""
    ) -> None:
        self.conn.execute(
            "UPDATE fermentation_chamber SET confidence_score = ?, enrichment_notes = ? "
            "WHERE id = ?",
            (new_score, notes, fermentation_id),
        )

    def update_counts(
        self, fermentation_id: int, cross_refs: int, contradictions: int
    ) -> None:
        self.conn.execute(
            "UPDATE fermentation_chamber SET cross_ref_count = ?, contradiction_count = ? "
            "WHERE id = ?",
            (cross_refs, contradictions, fermentation_id),
        )

    def promote(self, fermentation_id: int) -> None:
        """Mark item as promoted."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE fermentation_chamber SET status = 'promoted', promoted_at = ? "
            "WHERE id = ?",
            (now, fermentation_id),
        )

    def reject(self, fermentation_id: int, reason: str = "") -> None:
        self.conn.execute(
            "UPDATE fermentation_chamber SET status = 'rejected', enrichment_notes = ? "
            "WHERE id = ?",
            (reason, fermentation_id),
        )

    def get_all(self, limit: int = 50) -> list[FermentingItem]:
        rows = self.conn.execute(
            "SELECT * FROM fermentation_chamber ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def _row_to_item(self, row: sqlite3.Row) -> FermentingItem:
        return FermentingItem(
            id=row["id"],
            raw_content=row["raw_content"],
            title=row["title"],
            source_path=row["source_path"],
            status=row["status"],
            confidence_score=row["confidence_score"],
            fermentation_started_at=row["fermentation_started_at"],
            fermentation_duration_hours=row["fermentation_duration_hours"],
            cross_ref_count=row["cross_ref_count"],
            contradiction_count=row["contradiction_count"],
            enrichment_notes=row["enrichment_notes"],
        )
