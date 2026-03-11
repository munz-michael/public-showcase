"""Orchestrates the full knowledge fermentation pipeline."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from akm.fermentation.chamber import FermentationChamber
from akm.fermentation.contradiction import Contradiction, ContradictionDetector
from akm.fermentation.cross_ref import CrossReferencer
from akm.llm.client import ClaudeClient
from akm.stigmergy.signals import PheromoneSignal, SignalType, StigmergyNetwork


@dataclass
class FermentationResult:
    fermentation_id: int = 0
    status: str = "fermenting"
    cross_refs_found: int = 0
    contradictions_found: int = 0
    contradictions: list[Contradiction] = field(default_factory=list)
    final_confidence: float = 0.0


class Fermenter:
    """Pipeline: ingest → cross-reference → contradiction detection → promote/reject."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        duration_hours: float = 24.0,
        confidence_threshold: float = 0.6,
        max_contradictions: int = 2,
    ) -> None:
        self.conn = conn
        self.llm = llm
        self.chamber = FermentationChamber(conn, duration_hours)
        self.cross_ref = CrossReferencer(conn, llm)
        self.contradiction_detector = ContradictionDetector(llm)
        self.confidence_threshold = confidence_threshold
        self.max_contradictions = max_contradictions
        self.stigmergy = StigmergyNetwork(conn)

    def ingest_and_ferment(
        self,
        content: str,
        title: str = "",
        source_path: str = "",
        duration_hours: float | None = None,
    ) -> FermentationResult:
        """Full cycle: ingest → cross-ref → contradictions → confidence score."""
        result = FermentationResult()

        # 1. Ingest into chamber
        fid = self.chamber.ingest(content, title, source_path, duration_hours)
        result.fermentation_id = fid

        # 2. Cross-reference with existing knowledge
        refs = self.cross_ref.find_references(fid)
        result.cross_refs_found = len(refs)

        # 3. Detect contradictions
        if refs:
            contradicting_chunks = [
                r for r in refs if r["relationship"] == "contradicts"
            ]
            if contradicting_chunks:
                # Get full chunk content for contradiction analysis
                chunk_ids = [r["chunk_id"] for r in contradicting_chunks]
                placeholders = ",".join("?" * len(chunk_ids))
                chunks = self.conn.execute(
                    f"SELECT id, heading, content FROM chunks WHERE id IN ({placeholders})",
                    chunk_ids,
                ).fetchall()
                chunks_data = [dict(c) for c in chunks]
                result.contradictions = self.contradiction_detector.detect(
                    content, chunks_data
                )
            result.contradictions_found = len(result.contradictions)

        # 4. Compute confidence (stigmergy-adjusted)
        confidence = self._compute_confidence(result)

        # Check stigmergy: if domain has high threat level, apply caution penalty
        domain = title.split("/")[0].strip().lower() if title else "unknown"
        threat_level = self.stigmergy.get_domain_threat_level(domain)
        if threat_level > 0.3:
            confidence *= (1.0 - threat_level * 0.3)  # up to 30% penalty

        result.final_confidence = confidence
        result.status = "fermenting"

        # Update chamber
        notes = self._build_notes(result)
        self.chamber.update_confidence(fid, confidence, notes)

        return result

    def process_ready(self) -> list[FermentationResult]:
        """Process all items whose fermentation duration has elapsed."""
        ready_items = self.chamber.get_ready()
        results = []

        for item in ready_items:
            result = FermentationResult(
                fermentation_id=item.id,
                cross_refs_found=item.cross_ref_count,
                contradictions_found=item.contradiction_count,
                final_confidence=item.confidence_score,
            )

            # Promotion logic
            critical_contradictions = item.contradiction_count
            if (item.confidence_score >= self.confidence_threshold
                    and critical_contradictions <= self.max_contradictions):
                self.chamber.promote(item.id)
                result.status = "promoted"
            elif critical_contradictions > self.max_contradictions:
                self.chamber.reject(item.id, "Too many contradictions")
                result.status = "rejected"
                # Emit stigmergy signal for rejected fermentation
                domain = item.title.split("/")[0].strip().lower() if item.title else "unknown"
                self.stigmergy.emit(PheromoneSignal(
                    signal_type=SignalType.FERMENTATION_REJECTED,
                    domain=domain,
                    intensity=0.6,
                    source_component="fermentation",
                    source_id=item.id,
                ))
            else:
                result.status = "fermenting"  # needs more time

            results.append(result)

        return results

    def immediate_integrate(
        self,
        content: str,
        title: str = "",
        source_path: str = "",
    ) -> FermentationResult:
        """Baseline: skip fermentation, integrate immediately.
        Used for A/B comparison benchmarks."""
        fid = self.chamber.ingest(content, title, source_path, duration_hours=0)
        self.chamber.promote(fid)
        return FermentationResult(
            fermentation_id=fid,
            status="promoted",
            final_confidence=1.0,  # No analysis performed
        )

    def _compute_confidence(self, result: FermentationResult) -> float:
        """Confidence based on cross-references and contradictions."""
        base = 0.5

        # More supporting refs = higher confidence
        supporting = result.cross_refs_found - result.contradictions_found
        if supporting > 0:
            base += min(0.3, supporting * 0.1)

        # Contradictions reduce confidence
        for c in result.contradictions:
            if c.severity == "critical":
                base -= 0.3
            elif c.severity == "major":
                base -= 0.15
            else:
                base -= 0.05

        return max(0.0, min(1.0, base))

    def _build_notes(self, result: FermentationResult) -> str:
        parts = [f"Cross-refs: {result.cross_refs_found}"]
        if result.contradictions:
            parts.append(f"Contradictions: {result.contradictions_found}")
            for c in result.contradictions:
                parts.append(f"  [{c.severity}] {c.explanation[:100]}")
        parts.append(f"Confidence: {result.final_confidence:.2f}")
        return "\n".join(parts)
