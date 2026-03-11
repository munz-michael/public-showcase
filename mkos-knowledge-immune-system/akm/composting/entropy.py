"""Entropy scoring for knowledge chunks."""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone


class EntropyScorer:
    """Compute and track entropy scores for knowledge chunks.

    Entropy represents knowledge decay: 0.0 = fresh, 1.0 = fully decayed.
    Formula: E(t) = 1 - exp(-decay_rate * days_since_validation)
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        base_decay_rate: float = 0.01,
        validation_reset: float = 0.3,
    ) -> None:
        self.conn = conn
        self.base_decay_rate = base_decay_rate
        self.validation_reset = validation_reset

    def compute_age_entropy(self, chunk_id: int) -> float:
        """Entropy based on age since last validation or creation."""
        row = self.conn.execute(
            "SELECT last_validated_at FROM chunk_entropy "
            "WHERE chunk_id = ? ORDER BY created_at DESC LIMIT 1",
            (chunk_id,),
        ).fetchone()

        if row:
            last_validated = datetime.fromisoformat(row["last_validated_at"])
        else:
            # Fallback to document indexed_at
            row = self.conn.execute(
                "SELECT d.indexed_at FROM chunks c "
                "JOIN documents d ON d.id = c.document_id "
                "WHERE c.id = ?",
                (chunk_id,),
            ).fetchone()
            if not row:
                return 0.5
            last_validated = datetime.fromisoformat(row["indexed_at"])

        if last_validated.tzinfo is None:
            last_validated = last_validated.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        days = (now - last_validated).total_seconds() / 86400.0
        return 1.0 - math.exp(-self.base_decay_rate * days)

    def compute_content_entropy(
        self, chunk_id: int, llm: object
    ) -> float:
        """LLM-assessed entropy: how likely is this content outdated?"""
        row = self.conn.execute(
            "SELECT c.content, c.heading FROM chunks c WHERE c.id = ?",
            (chunk_id,),
        ).fetchone()
        if not row:
            return 0.5

        result = llm.extract_json(  # type: ignore[union-attr]
            system_prompt=(
                "You assess how likely a piece of knowledge is to be outdated. "
                "Consider: Does it reference specific versions, dates, or tools that change rapidly? "
                "Is it about a fast-moving domain (tech, AI, politics) or stable domain (math, physics)? "
                "Respond with: {\"entropy\": 0.0-1.0, \"reason\": \"brief explanation\"}"
            ),
            user_content=f"Heading: {row['heading']}\n\nContent:\n{row['content'][:2000]}",
        )
        if isinstance(result, dict):
            return float(result.get("entropy", 0.5))
        return 0.5

    def compute_combined_entropy(
        self, chunk_id: int, llm: object | None = None
    ) -> float:
        """Weighted combination of age and content entropy."""
        age_entropy = self.compute_age_entropy(chunk_id)
        if llm is None:
            return age_entropy

        content_entropy = self.compute_content_entropy(chunk_id, llm)
        # Weight: 40% age, 60% content assessment
        return 0.4 * age_entropy + 0.6 * content_entropy

    def score_chunk(
        self, chunk_id: int, llm: object | None = None, source: str = "auto"
    ) -> float:
        """Score a single chunk and persist the result."""
        score = self.compute_combined_entropy(chunk_id, llm)
        self.conn.execute(
            "INSERT INTO chunk_entropy (chunk_id, entropy_score, validation_source) "
            "VALUES (?, ?, ?)",
            (chunk_id, score, source),
        )
        return score

    def score_all_chunks(
        self, llm: object | None = None, batch_size: int = 50
    ) -> list[tuple[int, float]]:
        """Score all chunks, return list of (chunk_id, entropy_score)."""
        rows = self.conn.execute(
            "SELECT id FROM chunks ORDER BY id LIMIT ?", (batch_size,)
        ).fetchall()

        results = []
        for row in rows:
            score = self.score_chunk(row["id"], llm)
            results.append((row["id"], score))
        return results

    def get_compostable(self, threshold: float = 0.7) -> list[dict]:
        """Return chunks with latest entropy above threshold."""
        rows = self.conn.execute(
            "SELECT ce.chunk_id, ce.entropy_score, c.heading, c.content, "
            "c.document_id "
            "FROM chunk_entropy ce "
            "JOIN chunks c ON c.id = ce.chunk_id "
            "WHERE ce.entropy_score >= ? "
            "AND ce.id = (SELECT MAX(id) FROM chunk_entropy WHERE chunk_id = ce.chunk_id) "
            "ORDER BY ce.entropy_score DESC",
            (threshold,),
        ).fetchall()
        return [dict(r) for r in rows]

    def validate_chunk(self, chunk_id: int) -> float:
        """Mark a chunk as validated, reducing its entropy."""
        self.conn.execute(
            "INSERT INTO chunk_entropy (chunk_id, entropy_score, validation_source) "
            "VALUES (?, ?, 'manual')",
            (chunk_id, self.validation_reset),
        )
        return self.validation_reset
