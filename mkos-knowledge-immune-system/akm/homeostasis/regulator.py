"""Homeostasis -- self-regulating parameter adjustment for knowledge base health.

Biological inspiration: The body maintains stable internal conditions (temperature,
pH, blood sugar) through feedback loops that detect deviations and correct them.

In MKOS, the regulator monitors system health metrics and auto-adjusts:
- Entropy decay rates (faster for threat-heavy domains)
- Confidence thresholds (stricter for volatile domains)
- Fermentation duration (longer for contradiction-prone areas)
- Immune sensitivity (rebalances precision/recall trade-off)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass
class SystemVitals:
    """Current vital signs of the knowledge base."""
    total_chunks: int = 0
    threat_rate: float = 0.0  # threats / total scans
    false_positive_rate: float = 0.0  # resolved-as-incorrect / total threats
    composting_throughput: float = 0.0  # chunks composted / total chunks
    fermentation_rejection_rate: float = 0.0  # rejected / total fermented
    avg_entropy: float = 0.0
    nutrient_reuse_rate: float = 0.0


@dataclass
class ParameterAdjustment:
    """A recommended parameter change from homeostatic regulation."""
    parameter: str
    current_value: float
    recommended_value: float
    reason: str
    domain: str | None = None  # None = global


class HomeostasisRegulator:
    """Monitors system health and recommends parameter adjustments.

    Target ranges (setpoints) define healthy system state.
    When metrics deviate, the regulator computes corrections.
    """

    # Setpoints: target ranges for healthy operation
    SETPOINTS = {
        "threat_rate": (0.05, 0.20),  # 5-20% threat rate is normal
        "false_positive_rate": (0.0, 0.15),  # <15% FP is acceptable
        "composting_throughput": (0.01, 0.10),  # 1-10% composted is normal
        "fermentation_rejection_rate": (0.05, 0.30),  # 5-30% rejection is healthy
        "avg_entropy": (0.15, 0.45),  # mean entropy in healthy range
        "nutrient_reuse_rate": (0.10, 0.50),  # 10-50% reuse is good
    }

    # Default tunable parameters
    DEFAULT_PARAMS = {
        "entropy_decay_rate": 0.01,
        "entropy_threshold": 0.7,
        "immune_confidence_threshold": 0.5,
        "fermentation_duration_hours": 24.0,
        "composting_batch_size": 50,
    }

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def measure_vitals(self) -> SystemVitals:
        """Take current vital measurements of the knowledge base."""
        vitals = SystemVitals()

        vitals.total_chunks = self.conn.execute(
            "SELECT COUNT(*) as c FROM chunks"
        ).fetchone()["c"]

        # Threat rate
        total_scans = self.conn.execute(
            "SELECT COUNT(*) as c FROM immune_scan_results"
        ).fetchone()["c"]
        if total_scans > 0:
            threats = self.conn.execute(
                "SELECT COUNT(*) as c FROM immune_scan_results WHERE confidence > 0.5"
            ).fetchone()["c"]
            vitals.threat_rate = threats / total_scans

        # False positive rate (resolved threats marked as incorrect)
        resolved = self.conn.execute(
            "SELECT COUNT(*) as c FROM immune_scan_results WHERE resolved = 1"
        ).fetchone()["c"]
        if resolved > 0:
            # Approximation: low-confidence resolved threats are likely FPs
            low_conf_resolved = self.conn.execute(
                "SELECT COUNT(*) as c FROM immune_scan_results "
                "WHERE resolved = 1 AND confidence < 0.4"
            ).fetchone()["c"]
            vitals.false_positive_rate = low_conf_resolved / resolved

        # Composting throughput
        if vitals.total_chunks > 0:
            composted = self.conn.execute(
                "SELECT COUNT(*) as c FROM compost_log"
            ).fetchone()["c"]
            vitals.composting_throughput = composted / max(1, vitals.total_chunks + composted)

        # Fermentation rejection rate
        total_fermented = self.conn.execute(
            "SELECT COUNT(*) as c FROM fermentation_chamber "
            "WHERE status IN ('promoted', 'rejected')"
        ).fetchone()["c"]
        if total_fermented > 0:
            rejected = self.conn.execute(
                "SELECT COUNT(*) as c FROM fermentation_chamber WHERE status = 'rejected'"
            ).fetchone()["c"]
            vitals.fermentation_rejection_rate = rejected / total_fermented

        # Average entropy
        entropy_row = self.conn.execute(
            "SELECT AVG(entropy_score) as avg_e FROM chunk_entropy "
            "WHERE id IN (SELECT MAX(id) FROM chunk_entropy GROUP BY chunk_id)"
        ).fetchone()
        if entropy_row and entropy_row["avg_e"] is not None:
            vitals.avg_entropy = entropy_row["avg_e"]

        # Nutrient reuse rate
        total_nutrients = self.conn.execute(
            "SELECT COUNT(*) as c FROM nutrients"
        ).fetchone()["c"]
        if total_nutrients > 0:
            reused = self.conn.execute(
                "SELECT COUNT(*) as c FROM nutrients WHERE usage_count > 0"
            ).fetchone()["c"]
            vitals.nutrient_reuse_rate = reused / total_nutrients

        return vitals

    def diagnose(self, vitals: SystemVitals | None = None) -> list[ParameterAdjustment]:
        """Analyze vitals and recommend parameter adjustments."""
        if vitals is None:
            vitals = self.measure_vitals()

        adjustments: list[ParameterAdjustment] = []
        current_params = self._get_current_params()

        # Rule 1: High threat rate → increase immune sensitivity
        low, high = self.SETPOINTS["threat_rate"]
        if vitals.threat_rate > high:
            current = current_params["entropy_decay_rate"]
            adjustments.append(ParameterAdjustment(
                parameter="entropy_decay_rate",
                current_value=current,
                recommended_value=min(0.05, current * 1.5),
                reason=f"Threat rate {vitals.threat_rate:.2f} above setpoint {high}. "
                       "Accelerating decay to compost problematic content faster.",
            ))

        # Rule 2: High false positive rate → reduce immune sensitivity
        _, fp_high = self.SETPOINTS["false_positive_rate"]
        if vitals.false_positive_rate > fp_high:
            current = current_params["immune_confidence_threshold"]
            adjustments.append(ParameterAdjustment(
                parameter="immune_confidence_threshold",
                current_value=current,
                recommended_value=min(0.8, current + 0.1),
                reason=f"False positive rate {vitals.false_positive_rate:.2f} above {fp_high}. "
                       "Raising confidence threshold to reduce false alarms.",
            ))
        elif vitals.threat_rate < low and vitals.total_chunks > 50:
            # Very low threat rate with enough data → might be missing threats
            current = current_params["immune_confidence_threshold"]
            if current > 0.3:
                adjustments.append(ParameterAdjustment(
                    parameter="immune_confidence_threshold",
                    current_value=current,
                    recommended_value=max(0.3, current - 0.05),
                    reason=f"Threat rate {vitals.threat_rate:.2f} below setpoint {low}. "
                           "Lowering threshold to catch more potential threats.",
                ))

        # Rule 3: High fermentation rejection → extend fermentation duration
        _, rej_high = self.SETPOINTS["fermentation_rejection_rate"]
        if vitals.fermentation_rejection_rate > rej_high:
            current = current_params["fermentation_duration_hours"]
            adjustments.append(ParameterAdjustment(
                parameter="fermentation_duration_hours",
                current_value=current,
                recommended_value=min(72.0, current * 1.5),
                reason=f"Rejection rate {vitals.fermentation_rejection_rate:.2f} above {rej_high}. "
                       "Extending fermentation for more thorough analysis.",
            ))

        # Rule 4: High avg entropy → lower composting threshold (compost more aggressively)
        _, entropy_high = self.SETPOINTS["avg_entropy"]
        if vitals.avg_entropy > entropy_high:
            current = current_params["entropy_threshold"]
            adjustments.append(ParameterAdjustment(
                parameter="entropy_threshold",
                current_value=current,
                recommended_value=max(0.5, current - 0.1),
                reason=f"Average entropy {vitals.avg_entropy:.2f} above {entropy_high}. "
                       "Lowering composting threshold to process more decaying content.",
            ))
        elif vitals.avg_entropy < self.SETPOINTS["avg_entropy"][0]:
            current = current_params["entropy_threshold"]
            if current < 0.9:
                adjustments.append(ParameterAdjustment(
                    parameter="entropy_threshold",
                    current_value=current,
                    recommended_value=min(0.9, current + 0.05),
                    reason=f"Average entropy {vitals.avg_entropy:.2f} below setpoint. "
                           "Raising threshold — less aggressive composting needed.",
                ))

        # Rule 5: Low nutrient reuse → increase composting batch size
        reuse_low = self.SETPOINTS["nutrient_reuse_rate"][0]
        if vitals.nutrient_reuse_rate < reuse_low and vitals.composting_throughput > 0:
            current = current_params["composting_batch_size"]
            adjustments.append(ParameterAdjustment(
                parameter="composting_batch_size",
                current_value=current,
                recommended_value=min(200, current + 25),
                reason=f"Nutrient reuse {vitals.nutrient_reuse_rate:.2f} below {reuse_low}. "
                       "Increasing batch size to generate more diverse nutrients.",
            ))

        return adjustments

    def apply_adjustments(self, adjustments: list[ParameterAdjustment] | None = None) -> list[dict]:
        """Apply parameter adjustments and record them."""
        if adjustments is None:
            adjustments = self.diagnose()

        results = []
        for adj in adjustments:
            self.conn.execute(
                "INSERT OR REPLACE INTO homeostasis_params "
                "(parameter, value, domain, last_reason) VALUES (?, ?, ?, ?)",
                (adj.parameter, adj.recommended_value, adj.domain, adj.reason),
            )
            self._record_metric(
                f"adjustment:{adj.parameter}",
                adj.recommended_value,
            )
            results.append({
                "parameter": adj.parameter,
                "old": adj.current_value,
                "new": adj.recommended_value,
                "reason": adj.reason,
            })

        return results

    def get_param(self, name: str, default: float | None = None) -> float:
        """Get a tunable parameter value (homeostasis-adjusted or default)."""
        row = self.conn.execute(
            "SELECT value FROM homeostasis_params WHERE parameter = ? AND domain IS NULL",
            (name,),
        ).fetchone()
        if row:
            return row["value"]
        if default is not None:
            return default
        return self.DEFAULT_PARAMS.get(name, 0.0)

    def get_domain_param(self, name: str, domain: str, default: float | None = None) -> float:
        """Get a domain-specific parameter (falls back to global)."""
        row = self.conn.execute(
            "SELECT value FROM homeostasis_params WHERE parameter = ? AND domain = ?",
            (name, domain),
        ).fetchone()
        if row:
            return row["value"]
        return self.get_param(name, default)

    def _get_current_params(self) -> dict[str, float]:
        """Get all current parameter values."""
        params = self.DEFAULT_PARAMS.copy()
        rows = self.conn.execute(
            "SELECT parameter, value FROM homeostasis_params WHERE domain IS NULL"
        ).fetchall()
        for row in rows:
            params[row["parameter"]] = row["value"]
        return params

    def _record_metric(self, metric_name: str, value: float) -> None:
        """Record a metric snapshot for trend analysis."""
        self.conn.execute(
            "INSERT INTO homeostasis_metrics (metric_name, metric_value) "
            "VALUES (?, ?)",
            (metric_name, value),
        )

    def record_vitals(self, vitals: SystemVitals | None = None) -> None:
        """Snapshot current vitals for historical tracking."""
        if vitals is None:
            vitals = self.measure_vitals()
        for field_name in (
            "threat_rate", "false_positive_rate", "composting_throughput",
            "fermentation_rejection_rate", "avg_entropy", "nutrient_reuse_rate",
        ):
            self._record_metric(field_name, getattr(vitals, field_name))
        self._record_metric("total_chunks", float(vitals.total_chunks))

    def get_health_report(self) -> dict:
        """Comprehensive health report with vitals, adjustments, and history."""
        vitals = self.measure_vitals()
        adjustments = self.diagnose(vitals)

        # Trend: last 5 metric snapshots
        trends = {}
        for metric in ("threat_rate", "avg_entropy", "total_chunks"):
            rows = self.conn.execute(
                "SELECT metric_value, recorded_at FROM homeostasis_metrics "
                "WHERE metric_name = ? ORDER BY recorded_at DESC LIMIT 5",
                (metric,),
            ).fetchall()
            trends[metric] = [{"value": r["metric_value"], "at": r["recorded_at"]} for r in rows]

        # Classify overall health
        deviation_count = 0
        for adj in adjustments:
            deviation_count += 1

        if deviation_count == 0:
            status = "healthy"
        elif deviation_count <= 2:
            status = "mild_deviation"
        else:
            status = "needs_attention"

        return {
            "status": status,
            "vitals": {
                "total_chunks": vitals.total_chunks,
                "threat_rate": round(vitals.threat_rate, 4),
                "false_positive_rate": round(vitals.false_positive_rate, 4),
                "composting_throughput": round(vitals.composting_throughput, 4),
                "fermentation_rejection_rate": round(vitals.fermentation_rejection_rate, 4),
                "avg_entropy": round(vitals.avg_entropy, 4),
                "nutrient_reuse_rate": round(vitals.nutrient_reuse_rate, 4),
            },
            "adjustments": [
                {
                    "parameter": a.parameter,
                    "current": a.current_value,
                    "recommended": a.recommended_value,
                    "reason": a.reason,
                }
                for a in adjustments
            ],
            "trends": trends,
            "current_params": self._get_current_params(),
        }
