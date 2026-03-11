"""Statistical aggregation for multi-run benchmarks and bootstrap CI."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class AggregatedMetric:
    """Statistical summary of a metric across multiple runs."""
    mean: float
    stddev: float
    ci_95_lower: float
    ci_95_upper: float
    n: int
    values: list[float]


# t-values for 95% CI (two-tailed) with (n-1) degrees of freedom
_T_VALUES = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}


def aggregate(values: list[float]) -> AggregatedMetric:
    """Compute mean, stddev, and 95% CI from a list of values."""
    n = len(values)
    if n == 0:
        return AggregatedMetric(0.0, 0.0, 0.0, 0.0, 0, [])

    mean = sum(values) / n

    if n < 2:
        return AggregatedMetric(mean, 0.0, mean, mean, n, values)

    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    stddev = math.sqrt(variance)

    t = _T_VALUES.get(n, 1.96)
    margin = t * stddev / math.sqrt(n)

    return AggregatedMetric(
        mean=round(mean, 4),
        stddev=round(stddev, 4),
        ci_95_lower=round(mean - margin, 4),
        ci_95_upper=round(mean + margin, 4),
        n=n,
        values=values,
    )


# ── Bootstrap CI ──────────────────────────────────────────────────────────


@dataclass
class BootstrapResult:
    """Bootstrap confidence interval for a metric."""
    observed: float
    mean: float
    ci_95_lower: float
    ci_95_upper: float
    n_bootstrap: int
    n_samples: int

    def to_dict(self) -> dict:
        return {
            "observed": round(self.observed, 4),
            "mean": round(self.mean, 4),
            "ci_95": [round(self.ci_95_lower, 4), round(self.ci_95_upper, 4)],
            "n_bootstrap": self.n_bootstrap,
            "n_samples": self.n_samples,
        }


@dataclass
class BootstrapReport:
    """Full bootstrap CI report for a classification system."""
    overall_f1: BootstrapResult
    overall_precision: BootstrapResult
    overall_recall: BootstrapResult
    per_class_f1: dict[str, BootstrapResult]
    n_samples: int
    n_bootstrap: int

    def to_dict(self) -> dict:
        return {
            "overall": {
                "f1": self.overall_f1.to_dict(),
                "precision": self.overall_precision.to_dict(),
                "recall": self.overall_recall.to_dict(),
            },
            "per_class": {
                cls: result.to_dict()
                for cls, result in self.per_class_f1.items()
            },
            "n_samples": self.n_samples,
            "n_bootstrap": self.n_bootstrap,
        }


def _compute_f1_from_pairs(
    pairs: list[tuple[str, str]],
    positive_labels: set[str],
) -> tuple[float, float, float]:
    """Compute precision, recall, F1 from (prediction, truth) pairs."""
    tp = fp = fn = 0
    for pred, truth in pairs:
        pred_pos = pred in positive_labels
        truth_pos = truth in positive_labels
        if pred_pos and truth_pos:
            tp += 1
        elif pred_pos and not truth_pos:
            fp += 1
        elif not pred_pos and truth_pos:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _compute_class_f1(
    pairs: list[tuple[str, str]],
    cls: str,
) -> float:
    """Compute F1 for a single class from (prediction, truth) pairs."""
    tp = fp = fn = 0
    for pred, truth in pairs:
        if pred == cls and truth == cls:
            tp += 1
        elif pred == cls and truth != cls:
            fp += 1
        elif pred != cls and truth == cls:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0


def _bootstrap_ci(
    values: list[float],
    observed: float,
    n_bootstrap: int,
) -> BootstrapResult:
    """Compute bootstrap CI from pre-computed bootstrap metric values."""
    values_sorted = sorted(values)
    n = len(values_sorted)
    mean = sum(values_sorted) / n

    lower_idx = max(0, int(n * 0.025))
    upper_idx = min(n - 1, int(n * 0.975))

    return BootstrapResult(
        observed=observed,
        mean=mean,
        ci_95_lower=values_sorted[lower_idx],
        ci_95_upper=values_sorted[upper_idx],
        n_bootstrap=n,
        n_samples=0,  # filled by caller
    )


def bootstrap_classification_ci(
    predictions: list[str],
    ground_truth: list[str],
    n_bootstrap: int = 1000,
    seed: int = 42,
    positive_labels: set[str] | None = None,
) -> BootstrapReport:
    """Compute bootstrap 95% CI for classification metrics.

    Resamples (prediction, ground_truth) pairs with replacement,
    computes F1/precision/recall on each resample. This gives
    valid CIs even from a single deterministic run.

    Args:
        predictions: Predicted labels per item.
        ground_truth: True labels per item.
        n_bootstrap: Number of bootstrap iterations.
        seed: Random seed for reproducibility.
        positive_labels: Labels considered threats.
    """
    if positive_labels is None:
        positive_labels = {"hallucination", "staleness", "bias", "contradiction"}

    rng = random.Random(seed)
    n = len(predictions)
    pairs = list(zip(predictions, ground_truth))
    classes = sorted(set(ground_truth) | set(predictions))

    # Observed metrics
    obs_prec, obs_rec, obs_f1 = _compute_f1_from_pairs(pairs, positive_labels)
    obs_class_f1 = {cls: _compute_class_f1(pairs, cls) for cls in classes}

    # Bootstrap
    boot_f1s = []
    boot_precs = []
    boot_recs = []
    boot_class_f1s: dict[str, list[float]] = {cls: [] for cls in classes}

    for _ in range(n_bootstrap):
        sample = rng.choices(pairs, k=n)
        p, r, f1 = _compute_f1_from_pairs(sample, positive_labels)
        boot_f1s.append(f1)
        boot_precs.append(p)
        boot_recs.append(r)
        for cls in classes:
            boot_class_f1s[cls].append(_compute_class_f1(sample, cls))

    f1_result = _bootstrap_ci(boot_f1s, obs_f1, n_bootstrap)
    f1_result.n_samples = n
    prec_result = _bootstrap_ci(boot_precs, obs_prec, n_bootstrap)
    prec_result.n_samples = n
    rec_result = _bootstrap_ci(boot_recs, obs_rec, n_bootstrap)
    rec_result.n_samples = n

    class_results = {}
    for cls in classes:
        cr = _bootstrap_ci(boot_class_f1s[cls], obs_class_f1[cls], n_bootstrap)
        cr.n_samples = n
        class_results[cls] = cr

    return BootstrapReport(
        overall_f1=f1_result,
        overall_precision=prec_result,
        overall_recall=rec_result,
        per_class_f1=class_results,
        n_samples=n,
        n_bootstrap=n_bootstrap,
    )


def aggregate_nested_metrics(runs: list[dict]) -> dict:
    """Aggregate nested metric dicts from multiple benchmark runs.

    Given a list of result dicts (one per run), produce a single dict
    where each numeric leaf value is replaced with an AggregatedMetric.
    Non-numeric values use the value from the first run.
    """
    if not runs:
        return {}

    template = runs[0]
    result = {}

    for key, value in template.items():
        if isinstance(value, dict):
            # Recurse into nested dicts
            nested_runs = [run.get(key, {}) for run in runs if isinstance(run.get(key), dict)]
            result[key] = aggregate_nested_metrics(nested_runs)
        elif isinstance(value, (int, float)):
            values = [run.get(key, 0) for run in runs if isinstance(run.get(key), (int, float))]
            agg = aggregate(values)
            result[key] = {
                "mean": agg.mean,
                "stddev": agg.stddev,
                "ci_95": [agg.ci_95_lower, agg.ci_95_upper],
                "n": agg.n,
            }
        else:
            # Non-numeric: keep first value (e.g., strategy name)
            result[key] = value

    return result
