"""Clonal selection -- amplify effective detection strategies, prune ineffective ones."""

from __future__ import annotations

import sqlite3


class ClonalSelector:
    """Implements clonal selection for immune pattern fitness."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        fitness_boost: float = 0.1,
        fitness_penalty: float = 0.05,
    ) -> None:
        self.conn = conn
        self.fitness_boost = fitness_boost
        self.fitness_penalty = fitness_penalty

    def update_fitness(self, pattern_id: int, was_correct: bool) -> float:
        """Update fitness score based on detection outcome."""
        row = self.conn.execute(
            "SELECT fitness_score FROM immune_patterns WHERE id = ?",
            (pattern_id,),
        ).fetchone()
        if not row:
            return 0.0

        current = row["fitness_score"]
        if was_correct:
            new_fitness = min(1.0, current + self.fitness_boost)
            self.conn.execute(
                "UPDATE immune_patterns SET fitness_score = ?, "
                "times_effective = times_effective + 1 WHERE id = ?",
                (new_fitness, pattern_id),
            )
        else:
            new_fitness = max(0.0, current - self.fitness_penalty)
            self.conn.execute(
                "UPDATE immune_patterns SET fitness_score = ? WHERE id = ?",
                (new_fitness, pattern_id),
            )
        return new_fitness

    def select_and_prune(self, min_fitness: float = 0.2) -> dict:
        """Run selection cycle: amplify high-fitness, prune low-fitness."""
        # Count before
        total = self.conn.execute("SELECT COUNT(*) as c FROM immune_patterns").fetchone()["c"]

        # Prune low-fitness patterns (only those with enough observations)
        pruned = self.conn.execute(
            "DELETE FROM immune_patterns WHERE fitness_score < ? AND times_detected >= 5",
            (min_fitness,),
        ).rowcount

        # Identify high-fitness patterns
        amplified = self.conn.execute(
            "SELECT COUNT(*) as c FROM immune_patterns WHERE fitness_score >= 0.8"
        ).fetchone()["c"]

        return {
            "total_before": total,
            "pruned": pruned,
            "amplified": amplified,
            "total_after": total - pruned,
        }
