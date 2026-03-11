"""Stigmergy -- indirect coordination via environmental pheromone signals.

Biological inspiration: Ants deposit pheromones that guide other ants' behavior.
In MKOS, components emit signals that coordinate cross-pipeline actions:
- Immune threat → composting accelerates decay in that domain
- High entropy cluster → fermentation gets more cautious in that domain
- Successful composting → fermentation can fast-track related content
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    THREAT_DETECTED = "threat_detected"
    HIGH_ENTROPY = "high_entropy"
    CONTRADICTION_CLUSTER = "contradiction_cluster"
    DOMAIN_HEALTHY = "domain_healthy"
    NUTRIENT_RICH = "nutrient_rich"
    FERMENTATION_REJECTED = "fermentation_rejected"


@dataclass
class PheromoneSignal:
    signal_type: SignalType
    domain: str
    intensity: float  # 0.0 - 1.0
    source_component: str  # "immune", "composting", "fermentation"
    source_id: int | None = None
    metadata: str = ""


class StigmergyNetwork:
    """Manages pheromone signals between MKOS components.

    Signals decay over time (evaporation) and strengthen when
    multiple sources confirm the same pattern (reinforcement).
    """

    EVAPORATION_RATE_HOURS = 72.0  # signals halve in intensity every 72h
    REINFORCEMENT_BOOST = 0.15

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def emit(self, signal: PheromoneSignal) -> int:
        """Deposit a pheromone signal into the environment."""
        existing = self.conn.execute(
            "SELECT id, intensity, reinforcement_count FROM stigmergy_signals "
            "WHERE signal_type = ? AND domain = ? AND active = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (signal.signal_type.value, signal.domain),
        ).fetchone()

        if existing:
            # Reinforce existing signal
            new_intensity = min(1.0, existing["intensity"] + self.REINFORCEMENT_BOOST)
            self.conn.execute(
                "UPDATE stigmergy_signals SET intensity = ?, "
                "reinforcement_count = reinforcement_count + 1, "
                "last_reinforced_at = datetime('now') "
                "WHERE id = ?",
                (new_intensity, existing["id"]),
            )
            return existing["id"]

        # New signal
        cursor = self.conn.execute(
            "INSERT INTO stigmergy_signals "
            "(signal_type, domain, intensity, source_component, source_id, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                signal.signal_type.value,
                signal.domain,
                signal.intensity,
                signal.source_component,
                signal.source_id,
                signal.metadata,
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def read_signals(
        self, domain: str | None = None, signal_type: SignalType | None = None,
        min_intensity: float = 0.1,
    ) -> list[dict]:
        """Read active pheromone signals, applying time-based evaporation."""
        inner = "SELECT *, " \
            "(intensity * MAX(0.0, 1.0 - " \
            "  (julianday('now') - julianday(COALESCE(last_reinforced_at, created_at))) " \
            "  * 24.0 / ?)) AS effective_intensity " \
            "FROM stigmergy_signals WHERE active = 1"
        params: list = [self.EVAPORATION_RATE_HOURS]

        if domain:
            inner += " AND domain = ?"
            params.append(domain)
        if signal_type:
            inner += " AND signal_type = ?"
            params.append(signal_type.value)

        query = f"SELECT * FROM ({inner}) WHERE effective_intensity >= ? ORDER BY effective_intensity DESC"
        params.append(min_intensity)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_domain_threat_level(self, domain: str) -> float:
        """Aggregate threat pheromones for a domain (0.0 = safe, 1.0 = critical)."""
        threat_types = {
            SignalType.THREAT_DETECTED,
            SignalType.CONTRADICTION_CLUSTER,
            SignalType.FERMENTATION_REJECTED,
        }
        signals = self.read_signals(domain=domain)
        threat_signals = [
            s for s in signals
            if s["signal_type"] in {t.value for t in threat_types}
        ]
        if not threat_signals:
            return 0.0
        return min(1.0, sum(s["effective_intensity"] for s in threat_signals))

    def get_domain_health(self, domain: str) -> dict:
        """Full pheromone landscape for a domain."""
        signals = self.read_signals(domain=domain)
        return {
            "domain": domain,
            "signal_count": len(signals),
            "threat_level": self.get_domain_threat_level(domain),
            "signals": signals,
        }

    def evaporate(self) -> int:
        """Deactivate signals that have fully evaporated."""
        cursor = self.conn.execute(
            "UPDATE stigmergy_signals SET active = 0 "
            "WHERE active = 1 AND "
            "(julianday('now') - julianday(COALESCE(last_reinforced_at, created_at))) "
            "* 24.0 / ? > 4.0",  # deactivate when intensity would be < ~2%
            (self.EVAPORATION_RATE_HOURS,),
        )
        return cursor.rowcount

    def get_stats(self) -> dict:
        """Summary of the pheromone landscape."""
        active = self.conn.execute(
            "SELECT COUNT(*) as c FROM stigmergy_signals WHERE active = 1"
        ).fetchone()["c"]
        by_type = self.conn.execute(
            "SELECT signal_type, COUNT(*) as c, AVG(intensity) as avg_intensity "
            "FROM stigmergy_signals WHERE active = 1 GROUP BY signal_type"
        ).fetchall()
        domains = self.conn.execute(
            "SELECT DISTINCT domain FROM stigmergy_signals WHERE active = 1"
        ).fetchall()
        return {
            "active_signals": active,
            "by_type": {
                r["signal_type"]: {"count": r["c"], "avg_intensity": round(r["avg_intensity"], 3)}
                for r in by_type
            },
            "active_domains": [r["domain"] for r in domains],
        }
