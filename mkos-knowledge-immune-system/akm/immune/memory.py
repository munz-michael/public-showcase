"""Immune memory -- persistent pattern library for known knowledge pathogens."""

from __future__ import annotations

import sqlite3

from akm.immune.antigens import Threat


class ImmuneMemory:
    """Trained immunity: builds faster detection for repeat patterns."""

    STOP_WORDS = frozenset({
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "and", "but", "or", "nor", "not", "so", "yet",
        "it", "its", "this", "that", "these", "those", "all", "each", "every",
        "both", "few", "more", "most", "other", "some", "such", "no", "only",
        "own", "same", "than", "too", "very", "just", "also", "up", "out",
    })

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def match_pattern(self, content: str, threat_type: str) -> dict | None:
        """Check if content matches any known pathogen pattern."""
        rows = self.conn.execute(
            "SELECT * FROM immune_patterns "
            "WHERE pattern_type = ? AND fitness_score > 0.3 "
            "ORDER BY fitness_score DESC LIMIT 10",
            (threat_type,),
        ).fetchall()

        content_lower = content.lower()
        for row in rows:
            keywords = [k for k in row["pattern_signature"].lower().split("|") if k]
            if not keywords:
                continue
            # Require majority of keywords to match (not just one)
            matches = sum(1 for kw in keywords if kw in content_lower)
            if matches >= max(2, len(keywords) * 0.6):
                self.conn.execute(
                    "UPDATE immune_patterns SET last_seen_at = datetime('now'), "
                    "times_detected = times_detected + 1 WHERE id = ?",
                    (row["id"],),
                )
                return dict(row)
        return None

    @classmethod
    def _build_signature(cls, text: str, max_terms: int = 8) -> str:
        """Build pattern signature from text, excluding stop words."""
        words = text.lower().split()
        keywords = [w for w in words if w not in cls.STOP_WORDS and len(w) > 2]
        return "|".join(keywords[:max_terms])

    def record_detection(self, threat: Threat, detection_successful: bool) -> int:
        """Record a detection. Create new pattern or update existing."""
        if threat.matched_pattern_id:
            if detection_successful:
                self.conn.execute(
                    "UPDATE immune_patterns SET times_effective = times_effective + 1, "
                    "last_seen_at = datetime('now') WHERE id = ?",
                    (threat.matched_pattern_id,),
                )
            return threat.matched_pattern_id

        # Build signature from key terms in the evidence (no stop words)
        signature = self._build_signature(threat.evidence)
        cursor = self.conn.execute(
            "INSERT INTO immune_patterns "
            "(pattern_type, pattern_signature, detection_strategy, severity, "
            "times_effective) VALUES (?, ?, ?, ?, ?)",
            (
                threat.threat_type.value,
                signature,
                threat.description[:200],
                "medium",
                1 if detection_successful else 0,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def get_top_patterns(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM immune_patterns "
            "ORDER BY fitness_score DESC, times_effective DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def prune_ineffective(self, min_fitness: float = 0.2) -> int:
        """Remove patterns with low fitness (immune tolerance)."""
        cursor = self.conn.execute(
            "DELETE FROM immune_patterns WHERE fitness_score < ? AND times_detected > 3",
            (min_fitness,),
        )
        return cursor.rowcount

    def get_stats(self) -> dict:
        total = self.conn.execute("SELECT COUNT(*) as c FROM immune_patterns").fetchone()["c"]
        by_type = self.conn.execute(
            "SELECT pattern_type, COUNT(*) as c, AVG(fitness_score) as avg_fitness "
            "FROM immune_patterns GROUP BY pattern_type"
        ).fetchall()
        return {
            "total_patterns": total,
            "by_type": {r["pattern_type"]: {"count": r["c"], "avg_fitness": round(r["avg_fitness"], 3)} for r in by_type},
        }
