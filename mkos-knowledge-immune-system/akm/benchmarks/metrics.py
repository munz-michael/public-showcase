"""Metrics for evaluating MKOS benchmark results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassificationMetrics:
    """Standard classification metrics."""
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        total = self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        return (self.true_positives + self.true_negatives) / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
            "tp": self.true_positives,
            "fp": self.false_positives,
            "tn": self.true_negatives,
            "fn": self.false_negatives,
        }


def detection_f1(
    predictions: list[str],
    ground_truth: list[str],
    positive_labels: set[str] | None = None,
) -> ClassificationMetrics:
    """Compute classification metrics for threat detection.

    Args:
        predictions: List of predicted labels per item.
        ground_truth: List of true labels per item.
        positive_labels: Labels considered "positive" (threats). Defaults to all non-"healthy".
    """
    if positive_labels is None:
        positive_labels = {"hallucination", "staleness", "bias", "contradiction"}

    metrics = ClassificationMetrics()
    for pred, truth in zip(predictions, ground_truth):
        pred_positive = pred in positive_labels
        truth_positive = truth in positive_labels

        if pred_positive and truth_positive:
            metrics.true_positives += 1
        elif pred_positive and not truth_positive:
            metrics.false_positives += 1
        elif not pred_positive and truth_positive:
            metrics.false_negatives += 1
        else:
            metrics.true_negatives += 1

    return metrics


def per_class_f1(
    predictions: list[str],
    ground_truth: list[str],
) -> dict[str, dict]:
    """Compute F1 per threat type."""
    classes = set(ground_truth) | set(predictions)
    result = {}

    for cls in classes:
        metrics = ClassificationMetrics()
        for pred, truth in zip(predictions, ground_truth):
            if pred == cls and truth == cls:
                metrics.true_positives += 1
            elif pred == cls and truth != cls:
                metrics.false_positives += 1
            elif pred != cls and truth == cls:
                metrics.false_negatives += 1
            else:
                metrics.true_negatives += 1
        result[cls] = metrics.to_dict()

    return result


def knowledge_density(
    total_chunks: int,
    unique_nutrients: int,
    nutrient_reuse_count: int,
) -> dict:
    """Metrics for composting effectiveness."""
    density = unique_nutrients / total_chunks if total_chunks > 0 else 0.0
    reuse_rate = nutrient_reuse_count / unique_nutrients if unique_nutrients > 0 else 0.0

    return {
        "knowledge_density": round(density, 4),
        "nutrient_reuse_rate": round(reuse_rate, 4),
        "total_chunks": total_chunks,
        "unique_nutrients": unique_nutrients,
        "nutrient_reuse_count": nutrient_reuse_count,
    }


def retrieval_quality(
    hits: int,
    total_pairs: int,
    mrr_sum: float,
) -> dict:
    """Metrics for FTS retrieval quality on known pairs.

    Inspired by RAGAS Context Precision/Recall.
    Measures whether FTS can find semantically related chunks
    (e.g., contradiction counterparts) from keyword-based queries.

    Args:
        hits: Number of pairs where the target was found in top-k results.
        total_pairs: Total known pairs evaluated.
        mrr_sum: Sum of reciprocal ranks (1/rank for each hit).
    """
    recall = hits / total_pairs if total_pairs > 0 else 0.0
    mrr = mrr_sum / total_pairs if total_pairs > 0 else 0.0

    return {
        "retrieval_recall_at_5": round(recall, 4),
        "mean_reciprocal_rank": round(mrr, 4),
        "pairs_found": hits,
        "total_pairs": total_pairs,
    }


def groundedness_score(
    evidence_grounded: int,
    total_threats: int,
    avg_word_overlap: float,
) -> dict:
    """Metrics for detector evidence groundedness.

    Inspired by TruLens Groundedness metric.
    Measures whether detector evidence is actually present in the source content.

    Args:
        evidence_grounded: Threats where evidence text was found in chunk content.
        total_threats: Total threats with evidence.
        avg_word_overlap: Average word-level Jaccard similarity between evidence and content.
    """
    citation_accuracy = evidence_grounded / total_threats if total_threats > 0 else 0.0

    return {
        "citation_accuracy": round(citation_accuracy, 4),
        "avg_word_overlap": round(avg_word_overlap, 4),
        "evidence_grounded": evidence_grounded,
        "total_threats_evaluated": total_threats,
    }


def latency_percentiles(durations: list[float]) -> dict:
    """Compute per-chunk latency statistics.

    Args:
        durations: List of durations in seconds per chunk scan.
    """
    if not durations:
        return {"mean_ms": 0, "p50_ms": 0, "p95_ms": 0, "n": 0}

    durations_sorted = sorted(durations)
    n = len(durations_sorted)

    return {
        "mean_ms": round(sum(durations) / n * 1000, 1),
        "p50_ms": round(durations_sorted[n // 2] * 1000, 1),
        "p95_ms": round(durations_sorted[min(int(n * 0.95), n - 1)] * 1000, 1),
        "n": n,
    }


def consistency_score(
    contradictions_detected: int,
    total_pairs_checked: int,
    true_contradictions: int,
) -> dict:
    """Metrics for fermentation effectiveness."""
    detection_rate = contradictions_detected / true_contradictions if true_contradictions > 0 else 0.0
    false_alarm_rate = max(0, contradictions_detected - true_contradictions) / total_pairs_checked if total_pairs_checked > 0 else 0.0

    return {
        "contradiction_detection_rate": round(detection_rate, 4),
        "false_alarm_rate": round(false_alarm_rate, 4),
        "contradictions_detected": contradictions_detected,
        "true_contradictions": true_contradictions,
        "total_pairs_checked": total_pairs_checked,
    }
