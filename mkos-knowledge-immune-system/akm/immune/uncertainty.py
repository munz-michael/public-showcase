"""Self-Consistency Sampling for uncertainty quantification.

Inspired by SelfCheckGPT: run the same classification multiple times
with temperature > 0 and measure agreement. High variance = uncertain.

Provides:
- Calibrated confidence scores (not just LLM self-reported confidence)
- Uncertainty flags for human review prioritization
- Agreement metrics across samples
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from akm.immune.antigens import Threat, ThreatType
from akm.immune.system import KnowledgeImmuneSystem
from akm.llm.client import ClaudeClient


@dataclass
class UncertaintyResult:
    """Result of self-consistency sampling for a single chunk."""
    chunk_id: int
    majority_label: str
    agreement_rate: float  # 0-1, fraction of samples agreeing with majority
    label_distribution: dict[str, int]
    n_samples: int
    is_uncertain: bool  # agreement < threshold
    original_confidence: float  # from single-pass innate
    calibrated_confidence: float  # agreement-weighted

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "majority_label": self.majority_label,
            "agreement_rate": round(self.agreement_rate, 3),
            "label_distribution": self.label_distribution,
            "n_samples": self.n_samples,
            "is_uncertain": self.is_uncertain,
            "original_confidence": round(self.original_confidence, 3),
            "calibrated_confidence": round(self.calibrated_confidence, 3),
        }


class SelfConsistencyScanner:
    """Multi-sample classification with uncertainty quantification.

    Runs the innate classifier N times at temperature > 0 and measures
    label agreement. When samples disagree, the prediction is uncertain.
    """

    VALID_LABELS = {"healthy", "hallucination", "staleness", "bias", "contradiction"}

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        n_samples: int = 5,
        temperature: float = 0.7,
        uncertainty_threshold: float = 0.6,
    ) -> None:
        self.conn = conn
        self.llm = llm
        self.n_samples = n_samples
        self.temperature = temperature
        self.uncertainty_threshold = uncertainty_threshold

    def scan_with_uncertainty(self, chunk_id: int) -> UncertaintyResult:
        """Classify a chunk with self-consistency uncertainty estimation."""
        row = self.conn.execute(
            "SELECT content, heading FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Chunk {chunk_id} not found")

        content = row["content"][:2000]

        # Sample N classifications at temperature > 0
        labels: list[str] = []
        confidences: list[float] = []

        for _ in range(self.n_samples):
            try:
                result = self.llm.extract_json(
                    KnowledgeImmuneSystem.INNATE_PROMPT,
                    content,
                    temperature=self.temperature,
                )
                if isinstance(result, dict):
                    label = result.get("label", "healthy")
                    conf = float(result.get("confidence", 0.5))
                    if label not in self.VALID_LABELS:
                        label = "healthy"
                    labels.append(label)
                    confidences.append(conf)
                else:
                    labels.append("healthy")
                    confidences.append(0.5)
            except Exception:
                labels.append("healthy")
                confidences.append(0.5)

        # Compute agreement
        counter = Counter(labels)
        majority_label, majority_count = counter.most_common(1)[0]
        agreement_rate = majority_count / len(labels)

        # Original confidence (from deterministic single pass)
        original_confidence = sum(confidences) / len(confidences)

        # Calibrated confidence: scale by agreement
        calibrated_confidence = original_confidence * agreement_rate

        is_uncertain = agreement_rate < self.uncertainty_threshold

        return UncertaintyResult(
            chunk_id=chunk_id,
            majority_label=majority_label,
            agreement_rate=agreement_rate,
            label_distribution=dict(counter),
            n_samples=self.n_samples,
            is_uncertain=is_uncertain,
            original_confidence=original_confidence,
            calibrated_confidence=calibrated_confidence,
        )

    def batch_scan(self, chunk_ids: list[int]) -> list[UncertaintyResult]:
        """Scan multiple chunks with uncertainty estimation."""
        return [self.scan_with_uncertainty(cid) for cid in chunk_ids]

    def prioritize_for_review(
        self, chunk_ids: list[int]
    ) -> dict[str, list[UncertaintyResult]]:
        """Scan and partition into certain/uncertain for human review.

        Returns:
            {"certain": [...], "uncertain": [...]}
        """
        results = self.batch_scan(chunk_ids)
        certain = [r for r in results if not r.is_uncertain]
        uncertain = [r for r in results if r.is_uncertain]

        # Sort uncertain by agreement rate (lowest first = most confused)
        uncertain.sort(key=lambda r: r.agreement_rate)

        return {"certain": certain, "uncertain": uncertain}
