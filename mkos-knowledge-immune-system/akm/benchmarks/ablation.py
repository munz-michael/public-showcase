"""Ablation study for MKOS Knowledge Immune System.

Tests which components contribute to detection performance by
systematically enabling/disabling detectors and system features.

Configurations:
- Full AIS: All 4 detectors + immune memory + clonal selection
- Innate-only: Just the holistic classifier, no adaptive detectors
- Leave-one-out: Remove each detector individually
- Single detector: Only one detector enabled at a time
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

from akm.benchmarks.datasets import BenchmarkItem, seed_benchmark_db
from akm.benchmarks.kqab import KQABResult, KQABTask
from akm.benchmarks.metrics import per_class_f1
from akm.immune.system import KnowledgeImmuneSystem
from akm.llm.client import ClaudeClient


ALL_DETECTORS = {"hallucination", "staleness", "bias", "contradiction"}


@dataclass
class AblationConfig:
    """Configuration for one ablation run."""
    name: str
    enabled_detectors: set[str] | None  # None = all, empty set = innate only
    description: str = ""


def default_ablation_configs() -> list[AblationConfig]:
    """Generate standard ablation configurations."""
    configs = [
        AblationConfig(
            name="full_ais",
            enabled_detectors=None,
            description="Full AIS: innate + all adaptive detectors",
        ),
        AblationConfig(
            name="innate_only",
            enabled_detectors=set(),
            description="Innate classifier only, no adaptive detectors",
        ),
    ]

    # Leave-one-out
    for det in sorted(ALL_DETECTORS):
        remaining = ALL_DETECTORS - {det}
        configs.append(AblationConfig(
            name=f"without_{det}",
            enabled_detectors=remaining,
            description=f"AIS without {det} detector",
        ))

    # Single detector
    for det in sorted(ALL_DETECTORS):
        configs.append(AblationConfig(
            name=f"only_{det}",
            enabled_detectors={det},
            description=f"Only {det} detector enabled",
        ))

    return configs


def run_ablation_t1(
    task: KQABTask,
    conn: sqlite3.Connection,
    llm: ClaudeClient,
    configs: list[AblationConfig] | None = None,
) -> dict[str, dict]:
    """Run ablation study on T1 (Threat Detection).

    Args:
        task: T1 KQABTask with items.
        conn: SQLite connection.
        llm: LLM client (ideally cached).
        configs: Ablation configurations. Defaults to standard set.

    Returns:
        Dict mapping config name to results dict.
    """
    if configs is None:
        configs = default_ablation_configs()

    # Seed database once
    chunk_ids = seed_benchmark_db(conn, task.items)
    ground_truth = [item.labels[0] for item in task.items]

    # Embed chunks once
    try:
        from akm.search.embeddings import embed_all_chunks
        embed_all_chunks(conn)
    except (ImportError, Exception):
        pass

    results = {}

    for config in configs:
        t0 = time.time()

        # Clear immune memory between runs
        conn.execute("DELETE FROM immune_patterns")
        conn.execute("DELETE FROM immune_scan_results")
        conn.commit()

        # Build AIS with specific detector configuration
        if config.enabled_detectors is not None and len(config.enabled_detectors) == 0:
            # Innate-only mode: use AIS but with no detectors
            immune = KnowledgeImmuneSystem(conn, llm, enabled_detectors=set())
        else:
            immune = KnowledgeImmuneSystem(conn, llm, enabled_detectors=config.enabled_detectors)

        predictions = []
        for cid in chunk_ids:
            try:
                scan_result = immune.scan_chunk(cid)
                if scan_result.threats_found:
                    top_threat = max(scan_result.threats_found, key=lambda t: t.confidence)
                    predictions.append(top_threat.threat_type.value)
                else:
                    predictions.append("healthy")
            except (ValueError, Exception):
                predictions.append("healthy")

        duration = time.time() - t0

        # Compute metrics
        kqab_result = KQABResult(
            task_id="T1",
            system_name=config.name,
            predictions=predictions,
            ground_truth=ground_truth,
            duration_seconds=duration,
        )

        results[config.name] = {
            "config": config.name,
            "description": config.description,
            "enabled_detectors": sorted(config.enabled_detectors) if config.enabled_detectors is not None else "all",
            "macro_f1": round(kqab_result.macro_f1, 4),
            "per_class": kqab_result.per_class_metrics,
            "duration_seconds": round(duration, 2),
            "n_items": len(predictions),
        }

    return results
