"""Benchmark runner for MKOS components."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from akm.benchmarks.baselines import (
    ArchiveOnlyBaseline,
    LLMFewShotBaseline,
    NoImmuneBaseline,
    SimpleHeuristicBaseline,
)
from akm.benchmarks.datasets import (
    composting_dataset,
    fermentation_dataset,
    immune_dataset,
    seed_benchmark_db,
)
from akm.benchmarks.metrics import (
    consistency_score,
    detection_f1,
    groundedness_score,
    knowledge_density,
    latency_percentiles,
    per_class_f1,
    retrieval_quality,
)
from akm.search.engine import SearchEngine, sanitize_fts_query
from akm.llm.client import ClaudeClient


class BenchmarkRunner:
    """Orchestrates and reports on MKOS benchmark suite."""

    def __init__(self, conn: sqlite3.Connection, llm: ClaudeClient, use_cache: bool = False,
                 dataset_type: str = "synthetic") -> None:
        self.conn = conn
        self.dataset_type = dataset_type  # "synthetic" or "real_world"
        if use_cache:
            from akm.llm.cache import CachedClaudeClient
            self.llm = CachedClaudeClient(llm)
        else:
            self.llm = llm

    def run(self, component: str = "all") -> dict:
        """Run benchmark suite. Returns structured report."""
        t0 = time.time()
        results = {}
        benchmarks_run = 0

        if component in ("composting", "all"):
            results["composting"] = self._benchmark_composting()
            benchmarks_run += 1

        if component in ("fermentation", "all"):
            results["fermentation"] = self._benchmark_fermentation()
            benchmarks_run += 1

        if component in ("immune", "all"):
            results["immune"] = self._benchmark_immune()
            benchmarks_run += 1

        total_duration = time.time() - t0

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_benchmarks": benchmarks_run,
            "total_duration_seconds": round(total_duration, 2),
            "total_cost_usd": round(self.llm.total_cost_usd, 4),
            "llm_stats": self.llm.stats(),
            "results": results,
        }

        # Persist to benchmark_runs table
        self._save_report(report)

        return report

    def run_multiple(self, component: str = "all", n_runs: int = 3) -> dict:
        """Run benchmark suite n times and aggregate with statistics."""
        from akm.benchmarks.statistics import aggregate_nested_metrics

        t0 = time.time()
        all_results = []

        for i in range(n_runs):
            # Clean benchmark data between runs
            self.conn.execute("DELETE FROM chunks WHERE document_id IN "
                              "(SELECT id FROM documents WHERE file_path = '/benchmark/data.md')")
            self.conn.execute("DELETE FROM nutrients")
            self.conn.execute("DELETE FROM fermentation_chamber")
            self.conn.execute("DELETE FROM chunk_entropy")
            self.conn.commit()

            result = self.run(component=component)
            all_results.append(result)

        total_duration = time.time() - t0

        # Aggregate metrics across runs
        aggregated_results = {}
        for comp_name in all_results[0].get("results", {}):
            run_metrics = [r["results"][comp_name]["metrics"]
                           for r in all_results if comp_name in r.get("results", {})]
            aggregated_results[comp_name] = {
                "dataset_size": all_results[0]["results"][comp_name]["dataset_size"],
                "metrics": aggregate_nested_metrics(run_metrics),
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_benchmarks": all_results[0]["total_benchmarks"],
            "n_runs": n_runs,
            "total_duration_seconds": round(total_duration, 2),
            "total_cost_usd": round(self.llm.total_cost_usd, 4),
            "llm_stats": self.llm.stats(),
            "results": aggregated_results,
        }

    def _benchmark_composting(self) -> dict:
        """Composting: Compare composting vs archive-only."""
        from akm.composting.composter import KnowledgeComposter

        t0 = time.time()
        dataset = composting_dataset()

        # Seed database with the dataset
        chunk_ids = seed_benchmark_db(self.conn, dataset)

        # Identify outdated chunks (second half of dataset)
        half = len(dataset) // 2
        outdated_ids = chunk_ids[half:]

        # --- Baseline: Archive Only ---
        archive_baseline = ArchiveOnlyBaseline()
        baseline_result = archive_baseline.process(self.conn, list(outdated_ids))

        # Re-seed for composting variant
        chunk_ids = seed_benchmark_db(self.conn, dataset)
        outdated_ids = chunk_ids[half:]

        # --- MKOS: Composting ---
        composter = KnowledgeComposter(
            self.conn, self.llm, entropy_threshold=0.3, archive_after_composting=True
        )

        # Manually mark outdated chunks as high entropy
        for cid in outdated_ids:
            self.conn.execute(
                "INSERT INTO chunk_entropy (chunk_id, entropy_score, validation_source) "
                "VALUES (?, 0.9, 'benchmark')",
                (cid,),
            )
        self.conn.commit()

        composting_result = composter.run(dry_run=False)

        # Phase 2: Enrich surviving chunks with extracted nutrients
        enrichment_count = 0
        surviving = self.conn.execute(
            "SELECT id, content FROM chunks"
        ).fetchall()
        for row in surviving:
            enriched = composter.enrich_with_nutrients(row["content"])
            if enriched != row["content"]:
                enrichment_count += 1

        # Compute metrics
        from akm.composting.nutrient_store import NutrientStore
        store = NutrientStore(self.conn)
        nutrient_stats = store.get_stats()

        total_chunks = self.conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
        density_metrics = knowledge_density(
            total_chunks=len(dataset),
            unique_nutrients=nutrient_stats["total"],
            nutrient_reuse_count=sum(
                item.get("usage_count", 0) for item in nutrient_stats.get("top_used", [])
            ),
        )

        duration = time.time() - t0
        return {
            "duration_seconds": round(duration, 2),
            "dataset_size": len(dataset),
            "metrics": {
                "baseline_archive_only": baseline_result,
                "mkos_composting": {
                    "chunks_composted": composting_result.chunks_composted,
                    "nutrients_extracted": composting_result.nutrients_extracted,
                    "enrichments_applied": enrichment_count,
                    "cost_usd": round(composting_result.cost_usd, 4),
                },
                **density_metrics,
            },
        }

    def _benchmark_fermentation(self) -> dict:
        """Fermentation: Compare immediate vs fermented integration."""
        from akm.fermentation.fermenter import Fermenter

        t0 = time.time()
        base_items, new_items = fermentation_dataset()

        # Seed base items
        seed_benchmark_db(self.conn, base_items)

        fermenter = Fermenter(self.conn, self.llm, duration_hours=0)

        # --- Variant A: Immediate Integration (baseline) ---
        immediate_contradictions = 0
        for item in new_items:
            fermenter.immediate_integrate(item.content, title=item.title)

        # --- Variant B: Fermented Integration ---
        fermented_contradictions = 0
        fermented_cross_refs = 0
        for item in new_items:
            result = fermenter.ingest_and_ferment(item.content, title=item.title)
            fermented_contradictions += result.contradictions_found
            fermented_cross_refs += result.cross_refs_found

        # Ground truth: items with contradicts relationship
        true_contradictions = sum(
            1 for item in new_items
            if item.metadata.get("relationship") == "contradicts"
        )

        consistency = consistency_score(
            contradictions_detected=fermented_contradictions,
            total_pairs_checked=len(new_items),
            true_contradictions=true_contradictions,
        )

        duration = time.time() - t0
        return {
            "duration_seconds": round(duration, 2),
            "dataset_size": len(base_items) + len(new_items),
            "metrics": {
                "immediate_integration": {
                    "contradictions_detected": immediate_contradictions,
                    "cross_refs_found": 0,
                },
                "fermented_integration": {
                    "contradictions_detected": fermented_contradictions,
                    "cross_refs_found": fermented_cross_refs,
                },
                **consistency,
            },
        }

    def _get_immune_dataset(self):
        """Get immune dataset based on configured type."""
        if self.dataset_type == "real_world":
            from akm.benchmarks.real_world_dataset import load_dataset
            import os
            path = os.path.expanduser("~/.akm/real_world_dataset.json")
            if os.path.exists(path):
                return load_dataset(path)
        return immune_dataset()

    def _benchmark_immune(self) -> dict:
        """Immune: Compare AIS vs heuristic vs no-immune."""
        from akm.immune.system import KnowledgeImmuneSystem

        t0 = time.time()
        dataset = self._get_immune_dataset()

        # Seed database
        chunk_ids = seed_benchmark_db(self.conn, dataset)

        # Ground truth labels
        ground_truth = [item.labels[0] for item in dataset]

        # --- Baseline 1: No Immune ---
        no_immune = NoImmuneBaseline()
        no_immune_result = no_immune.scan(self.conn, chunk_ids)
        no_immune_f1 = detection_f1(no_immune_result["predictions"], ground_truth)

        # --- Baseline 2: Simple Heuristic ---
        heuristic = SimpleHeuristicBaseline()
        heuristic_result = heuristic.scan(self.conn, chunk_ids)
        heuristic_f1 = detection_f1(heuristic_result["predictions"], ground_truth)
        heuristic_per_class = per_class_f1(heuristic_result["predictions"], ground_truth)

        # --- Baseline 3: LLM Few-Shot (same LLM, no architecture) ---
        few_shot = LLMFewShotBaseline()
        few_shot_result = few_shot.scan(self.conn, chunk_ids, self.llm)
        few_shot_f1 = detection_f1(few_shot_result["predictions"], ground_truth)
        few_shot_per_class = per_class_f1(few_shot_result["predictions"], ground_truth)

        # --- MKOS: Full AIS (with latency + groundedness tracking) ---
        # Clear immune memory from previous runs to avoid contamination
        self.conn.execute("DELETE FROM immune_patterns")
        self.conn.execute("DELETE FROM immune_scan_results")
        self.conn.commit()

        # Embed all chunks for hybrid search (vector + FTS)
        try:
            from akm.search.embeddings import embed_all_chunks
            embedded = embed_all_chunks(self.conn)
        except (ImportError, Exception):
            embedded = 0

        immune = KnowledgeImmuneSystem(self.conn, self.llm)
        ais_predictions = []
        chunk_durations = []
        all_threats = []  # (evidence, chunk_content) for groundedness

        errors = 0
        for i, cid in enumerate(chunk_ids):
            t_chunk = time.time()
            try:
                scan_result = immune.scan_chunk(cid)
                chunk_durations.append(time.time() - t_chunk)
                if scan_result.threats_found:
                    top_threat = max(scan_result.threats_found, key=lambda t: t.confidence)
                    ais_predictions.append(top_threat.threat_type.value)
                    # Collect evidence for groundedness evaluation
                    chunk_content = dataset[i].content
                    for threat in scan_result.threats_found:
                        if threat.evidence:
                            all_threats.append((threat.evidence, chunk_content))
                else:
                    ais_predictions.append("healthy")
            except (ValueError, Exception):
                chunk_durations.append(time.time() - t_chunk)
                ais_predictions.append("healthy")
                errors += 1

        ais_f1 = detection_f1(ais_predictions, ground_truth)
        ais_per_class = per_class_f1(ais_predictions, ground_truth)

        # --- Bootstrap CI for all systems ---
        from akm.benchmarks.statistics import bootstrap_classification_ci

        ais_bootstrap = bootstrap_classification_ci(ais_predictions, ground_truth)
        few_shot_bootstrap = bootstrap_classification_ci(
            few_shot_result["predictions"], ground_truth
        )

        # --- Retrieval Quality: hybrid search pair test on contradiction counterparts ---
        search_engine = SearchEngine(self.conn)
        contra_map = {}  # pair_id -> dataset index
        counter_map = {}  # pair_id -> dataset index
        for idx, item in enumerate(dataset):
            pid = item.metadata.get("pair_id")
            if pid is not None:
                if item.labels[0] == "contradiction":
                    contra_map[pid] = idx
                elif item.metadata.get("is_counterpart"):
                    counter_map[pid] = idx

        retrieval_hits = 0
        retrieval_mrr_sum = 0.0
        total_pairs = 0

        for pid in contra_map:
            if pid not in counter_map:
                continue
            contra_idx = contra_map[pid]
            counter_idx = counter_map[pid]
            total_pairs += 1

            # Use hybrid search (vector + FTS) via search_related
            try:
                related = search_engine.search_related(
                    dataset[contra_idx].content[:500],
                    exclude_id=chunk_ids[contra_idx],
                    limit=5,
                )
            except Exception:
                continue

            result_ids = [r[0] for r in related]  # (id, heading, content)
            target_id = chunk_ids[counter_idx]
            if target_id in result_ids:
                retrieval_hits += 1
                rank = result_ids.index(target_id) + 1
                retrieval_mrr_sum += 1.0 / rank

        retrieval_metrics = retrieval_quality(retrieval_hits, total_pairs, retrieval_mrr_sum)

        # --- Groundedness: evaluate evidence quality ---
        evidence_grounded = 0
        overlap_sum = 0.0
        for evidence, content in all_threats:
            content_lower = content.lower()
            evidence_lower = evidence.lower()
            # Substring check (citation accuracy)
            if evidence_lower in content_lower:
                evidence_grounded += 1
            # Word-level Jaccard overlap
            ev_words = set(evidence_lower.split())
            ct_words = set(content_lower.split())
            if ev_words:
                overlap_sum += len(ev_words & ct_words) / len(ev_words | ct_words)

        avg_overlap = overlap_sum / len(all_threats) if all_threats else 0.0
        grounded_metrics = groundedness_score(evidence_grounded, len(all_threats), avg_overlap)

        # --- Latency stats ---
        latency_metrics = latency_percentiles(chunk_durations)

        duration = time.time() - t0
        return {
            "duration_seconds": round(duration, 2),
            "dataset_size": len(dataset),
            "metrics": {
                "no_immune": {
                    **no_immune_f1.to_dict(),
                    "strategy": "no_immune",
                },
                "simple_heuristic": {
                    **heuristic_f1.to_dict(),
                    "per_class": heuristic_per_class,
                    "strategy": "simple_heuristic",
                },
                "llm_few_shot": {
                    **few_shot_f1.to_dict(),
                    "per_class": few_shot_per_class,
                    "strategy": "llm_few_shot",
                },
                "mkos_ais": {
                    **ais_f1.to_dict(),
                    "per_class": ais_per_class,
                    "strategy": "mkos_ais",
                    "parse_errors": errors,
                    "bootstrap_ci": ais_bootstrap.to_dict(),
                },
                "llm_few_shot_bootstrap_ci": few_shot_bootstrap.to_dict(),
                "retrieval_quality": retrieval_metrics,
                "groundedness": grounded_metrics,
                "latency": latency_metrics,
            },
        }

    def _scan_with_system(self, immune, chunk_ids):
        """Run immune scan on all chunks, return predictions and error count."""
        predictions = []
        errors = 0
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
                errors += 1
        return predictions, errors

    def run_ablation(self) -> dict:
        """Run immune system ablation study: each detector alone + leave-one-out."""
        from akm.immune.system import KnowledgeImmuneSystem

        t0 = time.time()
        dataset = immune_dataset()
        chunk_ids = seed_benchmark_db(self.conn, dataset)
        ground_truth = [item.labels[0] for item in dataset]

        detector_names = {"hallucination", "staleness", "bias", "contradiction"}
        ablation_results = {}

        # Full system
        immune = KnowledgeImmuneSystem(self.conn, self.llm)
        preds, errs = self._scan_with_system(immune, chunk_ids)
        ablation_results["full"] = {
            **detection_f1(preds, ground_truth).to_dict(),
            "per_class": per_class_f1(preds, ground_truth),
            "detectors": list(detector_names),
        }

        # Single detector
        for det in detector_names:
            immune = KnowledgeImmuneSystem(self.conn, self.llm, enabled_detectors={det})
            preds, _ = self._scan_with_system(immune, chunk_ids)
            ablation_results[f"only_{det}"] = {
                **detection_f1(preds, ground_truth).to_dict(),
                "detectors": [det],
            }

        # Leave-one-out
        for det in detector_names:
            remaining = detector_names - {det}
            immune = KnowledgeImmuneSystem(self.conn, self.llm, enabled_detectors=remaining)
            preds, _ = self._scan_with_system(immune, chunk_ids)
            ablation_results[f"without_{det}"] = {
                **detection_f1(preds, ground_truth).to_dict(),
                "detectors": list(remaining),
            }

        return {
            "duration_seconds": round(time.time() - t0, 2),
            "dataset_size": len(dataset),
            "ablation": ablation_results,
        }

    def _save_report(self, report: dict) -> None:
        """Persist benchmark report to database."""
        for component, result in report.get("results", {}).items():
            self.conn.execute(
                "INSERT INTO benchmark_runs "
                "(benchmark_name, component, variant, metrics_json, run_duration_seconds) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    f"benchmark_{component}",
                    component,
                    "full_suite",
                    json.dumps(result.get("metrics", {}), ensure_ascii=False),
                    result.get("duration_seconds", 0),
                ),
            )
        self.conn.commit()
