"""Quorum Sensing -- collective decision-making based on threat density.

Biological inspiration: Bacteria coordinate behavior when population density
exceeds a threshold (e.g., biofilm formation, bioluminescence).

In MKOS, when multiple chunks in a domain show the same threat type,
a quorum is reached and collective actions are triggered:
- Domain-wide quarantine
- Batch re-scan with higher scrutiny
- Cascading composting of related content
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import Enum


class QuorumAction(Enum):
    DOMAIN_QUARANTINE = "domain_quarantine"
    BATCH_RESCAN = "batch_rescan"
    CASCADE_COMPOST = "cascade_compost"
    RAISE_SCRUTINY = "raise_scrutiny"
    DOMAIN_ALERT = "domain_alert"


@dataclass
class QuorumEvent:
    domain: str
    threat_type: str
    chunk_count: int
    avg_confidence: float
    action: QuorumAction
    affected_chunk_ids: list[int] = field(default_factory=list)


class QuorumSensor:
    """Detects when threat density reaches quorum thresholds.

    Configurable thresholds per threat type. When quorum is reached,
    returns recommended collective actions.
    """

    DEFAULT_THRESHOLDS = {
        "hallucination": 3,
        "staleness": 5,
        "bias": 4,
        "contradiction": 3,
    }

    ACTION_MAP = {
        "hallucination": QuorumAction.DOMAIN_QUARANTINE,
        "staleness": QuorumAction.CASCADE_COMPOST,
        "bias": QuorumAction.RAISE_SCRUTINY,
        "contradiction": QuorumAction.BATCH_RESCAN,
    }

    def __init__(
        self,
        conn: sqlite3.Connection,
        thresholds: dict[str, int] | None = None,
    ) -> None:
        self.conn = conn
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS.copy()

    def _extract_domain(self, heading: str) -> str:
        """Extract domain from chunk heading (first meaningful segment)."""
        if not heading:
            return "unknown"
        # Use the first heading segment as domain proxy
        parts = heading.split("/")
        domain = parts[0].strip().lower()
        # Remove common prefixes
        for prefix in ("chapter", "section", "part"):
            if domain.startswith(prefix):
                domain = domain[len(prefix):].strip(" :-")
        return domain or "unknown"

    def check_quorum(self, domain: str | None = None) -> list[QuorumEvent]:
        """Check if any domain has reached quorum for any threat type.

        Examines unresolved immune scan results grouped by domain and threat type.
        """
        # Get unresolved threats with chunk headings for domain extraction
        query = (
            "SELECT isr.chunk_id, isr.threat_type, isr.confidence, c.heading "
            "FROM immune_scan_results isr "
            "JOIN chunks c ON c.id = isr.chunk_id "
            "WHERE isr.resolved = 0"
        )
        params: list = []
        if domain:
            # Filter by heading prefix
            query += " AND LOWER(c.heading) LIKE ?"
            params.append(f"{domain.lower()}%")

        rows = self.conn.execute(query, params).fetchall()

        # Group by (domain, threat_type)
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            d = self._extract_domain(row["heading"])
            key = (d, row["threat_type"])
            if key not in groups:
                groups[key] = []
            groups[key].append({
                "chunk_id": row["chunk_id"],
                "confidence": row["confidence"],
            })

        events = []
        for (dom, threat_type), items in groups.items():
            threshold = self.thresholds.get(threat_type, 3)
            if len(items) >= threshold:
                avg_conf = sum(i["confidence"] for i in items) / len(items)
                action = self.ACTION_MAP.get(threat_type, QuorumAction.DOMAIN_ALERT)
                events.append(QuorumEvent(
                    domain=dom,
                    threat_type=threat_type,
                    chunk_count=len(items),
                    avg_confidence=avg_conf,
                    action=action,
                    affected_chunk_ids=[i["chunk_id"] for i in items],
                ))

        return events

    def record_event(self, event: QuorumEvent) -> int:
        """Persist a quorum event for tracking and audit."""
        import json
        cursor = self.conn.execute(
            "INSERT INTO quorum_events "
            "(domain, threat_type, chunk_count, avg_confidence, "
            "recommended_action, affected_chunk_ids) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                event.domain,
                event.threat_type,
                event.chunk_count,
                event.avg_confidence,
                event.action.value,
                json.dumps(event.affected_chunk_ids),
            ),
        )
        return cursor.lastrowid  # type: ignore[return-value]

    def execute_action(self, event: QuorumEvent) -> dict:
        """Execute the recommended quorum action.

        Returns a summary of what was done.
        """
        result = {
            "action": event.action.value,
            "domain": event.domain,
            "threat_type": event.threat_type,
            "chunks_affected": len(event.affected_chunk_ids),
        }

        if event.action == QuorumAction.DOMAIN_QUARANTINE:
            # Mark all affected chunks with a quarantine flag in scan results
            for cid in event.affected_chunk_ids:
                self.conn.execute(
                    "UPDATE immune_scan_results SET response_action = 'quarantine' "
                    "WHERE chunk_id = ? AND resolved = 0",
                    (cid,),
                )
            result["detail"] = "Quarantined all affected chunks"

        elif event.action == QuorumAction.CASCADE_COMPOST:
            # Mark affected chunks for priority composting via high entropy
            for cid in event.affected_chunk_ids:
                self.conn.execute(
                    "INSERT OR REPLACE INTO chunk_entropy "
                    "(chunk_id, entropy_score, validation_source) "
                    "VALUES (?, 0.95, 'quorum_cascade')",
                    (cid,),
                )
            result["detail"] = "Set entropy to 0.95 for cascade composting"

        elif event.action == QuorumAction.RAISE_SCRUTINY:
            # Record that this domain needs higher scrutiny
            # (Homeostasis module can read this to adjust thresholds)
            result["detail"] = "Domain flagged for raised scrutiny"

        elif event.action == QuorumAction.BATCH_RESCAN:
            result["detail"] = "Batch rescan recommended"
            result["rescan_chunk_ids"] = event.affected_chunk_ids

        else:
            result["detail"] = "Alert generated"

        self.record_event(event)
        return result

    def get_active_quorums(self) -> list[dict]:
        """Get all quorum events that haven't been resolved."""
        rows = self.conn.execute(
            "SELECT * FROM quorum_events WHERE resolved = 0 "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def resolve_quorum(self, event_id: int) -> None:
        """Mark a quorum event as resolved."""
        self.conn.execute(
            "UPDATE quorum_events SET resolved = 1, "
            "resolved_at = datetime('now') WHERE id = ?",
            (event_id,),
        )

    def get_stats(self) -> dict:
        """Quorum sensing statistics."""
        total = self.conn.execute(
            "SELECT COUNT(*) as c FROM quorum_events"
        ).fetchone()["c"]
        active = self.conn.execute(
            "SELECT COUNT(*) as c FROM quorum_events WHERE resolved = 0"
        ).fetchone()["c"]
        by_action = self.conn.execute(
            "SELECT recommended_action, COUNT(*) as c "
            "FROM quorum_events GROUP BY recommended_action"
        ).fetchall()
        return {
            "total_events": total,
            "active_events": active,
            "by_action": {r["recommended_action"]: r["c"] for r in by_action},
        }
