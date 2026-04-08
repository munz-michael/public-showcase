"""
Multi-Vector Correlation Engine — Parallel Signal Combination

Addresses the sub-additive CMF problem (2.3x measured vs. 6.2x expected)
from experiment_cost_multiplication.py. Root cause: layers share blind spots
because they evaluate independently and the first detection wins.

This engine collects signals from ALL 4 layers in parallel and correlates
them using the independent-failure model:

    combined_confidence = 1 - product(1 - ci for ci in layer_confidences)

Key insight: Two low-confidence signals from independent layers produce a
higher combined confidence than either alone. If L1 has 0.3 and L2 has 0.3:
    combined = 1 - (0.7 * 0.7) = 0.51
Both alone are under a 0.5 threshold, but combined they clear it.

Multi-vector bonus: If different layers detect different attack types, this
indicates a sophisticated multi-pronged attack deserving extra suspicion.

Implements Greene Strategy #19 (Envelop): surround the input with evaluations
from all angles simultaneously rather than relying on a single-file gauntlet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# LayerSignal — One layer's assessment of a request
# ---------------------------------------------------------------------------

@dataclass
class LayerSignal:
    """Detection signal from a single defense layer."""
    layer: int              # 1-4
    layer_name: str         # "formal", "antifragile", "infosec", "mtd"
    confidence: float       # 0.0 - 1.0 (how suspicious)
    attack_type: str        # what kind of attack suspected
    detail: str             # human-readable detail


# ---------------------------------------------------------------------------
# CorrelationResult — Combined assessment across all layers
# ---------------------------------------------------------------------------

@dataclass
class CorrelationResult:
    """Result of correlating signals from multiple defense layers."""
    combined_confidence: float
    max_single_confidence: float
    correlation_boost: float        # combined - max_single
    contributing_layers: list[int]   # layers with confidence > 0.1
    redundancy: int                  # how many layers contributed
    is_multi_vector: bool            # different attack_types from 2+ layers
    recommended_action: str          # "pass", "monitor", "sandbox", "block", "terminate"


# ---------------------------------------------------------------------------
# CorrelationEngine — Independent-Failure Correlation
# ---------------------------------------------------------------------------

class CorrelationEngine:
    """
    Combines detection signals from all 4 layers in parallel.

    Instead of sequential processing where the first detection wins,
    ALL layers evaluate every request and their signals are correlated.

    Correlation formula (independent-failure model):
        combined_confidence = 1 - product(1 - ci for ci in layer_confidences)

    Multi-vector boost: If 2+ layers report different attack_types, add +0.1
    to the combined confidence (capped at 1.0). This reflects that a
    multi-pronged attack is more suspicious than a single-vector one.

    Action mapping:
        <0.2  : "pass"
        0.2-0.4: "monitor"   (TOLERATE)
        0.4-0.6: "sandbox"   (SANDBOX)
        0.6-0.8: "block"     (INFLAME)
        >0.8  : "terminate"  (TERMINATE)
    """

    # Minimum confidence for a layer to count as "contributing"
    CONTRIBUTION_THRESHOLD = 0.1

    # Multi-vector bonus when different attack types detected from 2+ layers
    MULTI_VECTOR_BONUS = 0.1

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def correlate(self, signals: list[LayerSignal]) -> CorrelationResult:
        """
        Take signals from all layers and produce a correlated assessment.

        Steps:
        1. Collect confidences (even zero / sub-threshold ones participate)
        2. Apply independent-failure formula
        3. Check multi-vector condition and apply bonus
        4. Map combined confidence to recommended action
        """
        if not signals:
            return CorrelationResult(
                combined_confidence=0.0,
                max_single_confidence=0.0,
                correlation_boost=0.0,
                contributing_layers=[],
                redundancy=0,
                is_multi_vector=False,
                recommended_action="pass",
            )

        # Step 1: Extract confidences
        confidences = [s.confidence for s in signals]
        max_single = max(confidences) if confidences else 0.0

        # Step 2: Independent-failure formula
        # combined = 1 - product(1 - ci)
        product_of_complements = 1.0
        for c in confidences:
            clamped = max(0.0, min(1.0, c))
            product_of_complements *= (1.0 - clamped)
        combined = 1.0 - product_of_complements

        # Step 3: Contributing layers and multi-vector check
        contributing = [
            s.layer for s in signals
            if s.confidence > self.CONTRIBUTION_THRESHOLD
        ]
        redundancy = len(contributing)

        # Multi-vector: 2+ contributing layers with different attack types
        contributing_attack_types = set()
        for s in signals:
            if s.confidence > self.CONTRIBUTION_THRESHOLD and s.attack_type:
                contributing_attack_types.add(s.attack_type)
        is_multi_vector = len(contributing_attack_types) >= 2

        if is_multi_vector:
            combined = min(combined + self.MULTI_VECTOR_BONUS, 1.0)

        # Step 4: Map to action
        action = self._confidence_to_action(combined)

        correlation_boost = combined - max_single

        return CorrelationResult(
            combined_confidence=combined,
            max_single_confidence=max_single,
            correlation_boost=correlation_boost,
            contributing_layers=contributing,
            redundancy=redundancy,
            is_multi_vector=is_multi_vector,
            recommended_action=action,
        )

    @staticmethod
    def _confidence_to_action(confidence: float) -> str:
        """Map combined confidence to a recommended action."""
        if confidence < 0.2:
            return "pass"
        elif confidence < 0.4:
            return "monitor"
        elif confidence < 0.6:
            return "sandbox"
        elif confidence < 0.8:
            return "block"
        else:
            return "terminate"
