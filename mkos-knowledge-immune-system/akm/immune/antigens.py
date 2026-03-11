"""Threat types and data structures for the knowledge immune system."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThreatType(str, Enum):
    HALLUCINATION = "hallucination"
    STALENESS = "staleness"
    BIAS = "bias"
    CONTRADICTION = "contradiction"
    LOW_QUALITY = "low_quality"


@dataclass
class Threat:
    threat_type: ThreatType
    target_id: int
    target_type: str  # 'chunk' or 'fermentation_item'
    confidence: float
    description: str
    evidence: str
    matched_pattern_id: int | None = None
    suggested_action: str = "flag"  # 'flag', 'quarantine', 'compost', 'enrich'
