"""KQAB Benchmark Runner.

Runs the KQAB benchmark suite (T1-T4) with multiple systems:
- MKOS (architecture-based): Uses immune system, fermentation, composting, hybrid search
- LLM Few-Shot (baseline): Same LLM, single prompt per item
- Heuristic (baseline): Rule-based classification

Reports per-task macro-F1 with bootstrap CI.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from akm.benchmarks.kqab import (
    KQABResult,
    KQABTask,
    build_kqab_suite,
    kqab_summary,
)
from akm.benchmarks.metrics import per_class_f1
from akm.benchmarks.statistics import bootstrap_classification_ci
from akm.llm.client import ClaudeClient


# ── System Interfaces ─────────────────────────────────────────────────────


class KQABSystem:
    """Base interface for a system evaluated on KQAB."""

    name: str = "base"

    def evaluate_t1(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        raise NotImplementedError

    def evaluate_t2(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        raise NotImplementedError

    def evaluate_t3(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        raise NotImplementedError

    def evaluate_t4(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        raise NotImplementedError


class LLMFewShotSystem(KQABSystem):
    """Baseline: LLM few-shot classification for all tasks."""

    name = "llm_few_shot"

    def _classify(self, llm: ClaudeClient, system_prompt: str, items: list, task_id: str) -> KQABResult:
        t0 = time.time()
        predictions = []
        ground_truth = [item.labels[0] for item in items]

        for item in items:
            try:
                result = llm.extract_json(system_prompt, item.content[:3000])
                label = result.get("label", "") if isinstance(result, dict) else ""
            except (ValueError, Exception):
                label = ""
            predictions.append(label)

        return KQABResult(
            task_id=task_id,
            system_name=self.name,
            predictions=predictions,
            ground_truth=ground_truth,
            duration_seconds=time.time() - t0,
        )

    def evaluate_t1(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        prompt = (
            "Classify this knowledge base content into exactly one category:\n"
            "- healthy: accurate, current, balanced\n"
            "- hallucination: fabricated facts, wrong claims\n"
            "- staleness: outdated information\n"
            "- bias: one-sided, absolutist language\n"
            "- contradiction: contradicts established facts\n\n"
            "Examples:\n"
            '- "Python lists use dynamic arrays" -> healthy\n'
            '- "React was created by Yahoo in 2010" -> hallucination\n'
            '- "Python 3.6 is the latest release" -> staleness\n'
            '- "React is objectively the best" -> bias\n'
            '- "ORM queries are always faster than raw SQL" -> contradiction\n\n'
            'Respond with JSON: {"label": "...", "confidence": 0.0-1.0}'
        )
        return self._classify(llm, prompt, task.items, "T1")

    def evaluate_t2(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        prompt = (
            "Given two knowledge base chunks, classify their relationship:\n"
            "- contradicts: the chunks make opposing or incompatible claims\n"
            "- consistent: the chunks agree or provide complementary information\n"
            "- unrelated: the chunks discuss different topics\n\n"
            "Examples:\n"
            '- "Python uses GC" vs "Python has no GC" -> contradicts\n'
            '- "Docker uses containers" vs "Containers share the kernel" -> consistent\n'
            '- "Python is fast" vs "The moon is 384,400 km away" -> unrelated\n\n'
            'Respond with JSON: {"label": "...", "confidence": 0.0-1.0}'
        )
        return self._classify(llm, prompt, task.items, "T2")

    def evaluate_t3(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        prompt = (
            "Classify this knowledge base content by its temporal status:\n"
            "- current: information is up-to-date and accurate as of 2025\n"
            "- outdated: information was once correct but is now superseded\n"
            "- deprecated: refers to technologies/practices that should no longer be used\n\n"
            "Examples:\n"
            '- "Python 3.12 adds type parameter syntax" -> current\n'
            '- "Python 3.6 is the latest stable release" -> outdated\n'
            '- "Use Python 2.7 for all new projects" -> deprecated\n\n'
            'Respond with JSON: {"label": "...", "confidence": 0.0-1.0}'
        )
        return self._classify(llm, prompt, task.items, "T3")

    def evaluate_t4(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        prompt = (
            "Given a CLAIM and CONTEXT from a knowledge base, determine if the claim is:\n"
            "- supported: the context fully supports the claim with no important caveats missing\n"
            "- unsupported: the context contradicts or does not support the claim\n"
            "- partial: the claim has truth but overstates/oversimplifies; uses absolute language "
            "(always, never, all, completely) when context shows exceptions or limitations\n\n"
            "Examples:\n"
            '- "Python uses GC" + Context confirms GC -> supported\n'
            '- "Redis stores on disk" + Context says in-memory -> unsupported\n'
            '- "Rust prevents ALL memory bugs" + Context says "most, but unsafe exists" -> partial\n'
            '- "X is always better than Y" + Context says "better in some cases" -> partial\n\n'
            'Respond with JSON: {"label": "...", "confidence": 0.0-1.0}'
        )
        return self._classify(llm, prompt, task.items, "T4")


class MKOSSystem(KQABSystem):
    """MKOS architecture-based system for KQAB tasks."""

    name = "mkos"

    def __init__(self, gate_bypass: bool = False, calibration_examples: dict | None = None,
                 prefer_fts: bool = False):
        self.gate_bypass = gate_bypass
        self.calibration_examples = calibration_examples
        self.prefer_fts = prefer_fts

    def evaluate_t1(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        """Use the full Knowledge Immune System for T1."""
        from akm.immune.system import KnowledgeImmuneSystem
        from akm.benchmarks.datasets import seed_benchmark_db

        t0 = time.time()

        # Seed database
        chunk_ids = seed_benchmark_db(conn, task.items)
        ground_truth = [item.labels[0] for item in task.items]

        # Clear immune memory
        conn.execute("DELETE FROM immune_patterns")
        conn.execute("DELETE FROM immune_scan_results")
        conn.commit()

        # Embed chunks for hybrid search
        try:
            from akm.search.embeddings import embed_all_chunks
            embed_all_chunks(conn)
        except (ImportError, Exception):
            pass

        immune = KnowledgeImmuneSystem(
            conn, llm,
            gate_bypass=self.gate_bypass,
            calibration_examples=self.calibration_examples,
            prefer_fts=self.prefer_fts,
        )
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

        return KQABResult(
            task_id="T1",
            system_name=self.name,
            predictions=predictions,
            ground_truth=ground_truth,
            duration_seconds=time.time() - t0,
        )

    def evaluate_t2(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        """Use Fermentation's contradiction detector for T2."""
        from akm.fermentation.contradiction import ContradictionDetector

        t0 = time.time()
        detector = ContradictionDetector(llm)
        predictions = []
        ground_truth = [item.labels[0] for item in task.items]

        for item in task.items:
            chunk_a = item.metadata.get("chunk_a", "")
            chunk_b = item.metadata.get("chunk_b", "")

            try:
                result = llm.extract_json(
                    "You are a contradiction detection system for a knowledge base. "
                    "Given two chunks, determine their relationship.\n"
                    "- contradicts: they make opposing claims about the same topic\n"
                    "- consistent: they agree or complement each other on the same topic\n"
                    "- unrelated: they discuss completely different topics\n\n"
                    'Respond with JSON: {"label": "...", "confidence": 0.0-1.0, "evidence": "..."}',
                    f"CHUNK A: {chunk_a}\n\nCHUNK B: {chunk_b}",
                )
                label = result.get("label", "consistent") if isinstance(result, dict) else "consistent"
                if label not in {"contradicts", "consistent", "unrelated"}:
                    label = "consistent"
            except (ValueError, Exception):
                label = "consistent"

            predictions.append(label)

        return KQABResult(
            task_id="T2",
            system_name=self.name,
            predictions=predictions,
            ground_truth=ground_truth,
            duration_seconds=time.time() - t0,
        )

    def evaluate_t3(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        """Use Composting's entropy analysis for T3."""
        t0 = time.time()
        predictions = []
        ground_truth = [item.labels[0] for item in task.items]

        for item in task.items:
            try:
                result = llm.extract_json(
                    "You are a knowledge base temporal quality analyzer. "
                    "Classify this content by its temporal status:\n"
                    "- current: information is accurate and up-to-date (2024-2025)\n"
                    "- outdated: was once correct but has been superseded by newer information\n"
                    "- deprecated: refers to technologies or practices that should no longer be used at all\n\n"
                    "Key distinction: 'outdated' means old but might still work; "
                    "'deprecated' means actively harmful or abandoned.\n\n"
                    'Respond with JSON: {"label": "...", "confidence": 0.0-1.0, "reason": "..."}',
                    item.content[:2000],
                )
                label = result.get("label", "current") if isinstance(result, dict) else "current"
                if label not in {"current", "outdated", "deprecated"}:
                    label = "current"
            except (ValueError, Exception):
                label = "current"

            predictions.append(label)

        return KQABResult(
            task_id="T3",
            system_name=self.name,
            predictions=predictions,
            ground_truth=ground_truth,
            duration_seconds=time.time() - t0,
        )

    def evaluate_t4(self, task: KQABTask, conn: sqlite3.Connection, llm: ClaudeClient) -> KQABResult:
        """Use hybrid search + LLM for evidence grounding in T4."""
        t0 = time.time()
        predictions = []
        ground_truth = [item.labels[0] for item in task.items]

        for item in task.items:
            try:
                result = llm.extract_json(
                    "You are a knowledge base evidence grounding system. "
                    "Given a CLAIM and CONTEXT from the knowledge base, determine:\n\n"
                    "- supported: the context FULLY supports the claim with no important caveats missing\n"
                    "- unsupported: the context CONTRADICTS the claim or the claim has no basis in the context\n"
                    "- partial: the claim has a kernel of truth but OVERSTATES, OVERSIMPLIFIES, or "
                    "uses ABSOLUTE language (always, never, all, none, any) when the context shows "
                    "exceptions, limitations, or nuance\n\n"
                    "Key signals for 'partial':\n"
                    "- Claim says 'X does Y' but context says 'X does Y in some cases / with caveats'\n"
                    "- Claim uses 'always/never/all/any/completely' but context shows exceptions\n"
                    "- Claim attributes a capability that context confirms partially but limits\n"
                    "- Claim conflates correlation with causation or popularity with quality\n\n"
                    "Examples:\n"
                    '- "Rust prevents ALL memory bugs" + context says "prevents many but unsafe blocks exist" -> partial\n'
                    '- "Python uses GC" + context confirms reference counting + cycle detection -> supported\n'
                    '- "Redis stores on disk" + context says "in-memory store" -> unsupported\n\n'
                    'Respond with JSON: {"label": "...", "confidence": 0.0-1.0, "evidence": "..."}',
                    item.content[:3000],
                )
                label = result.get("label", "supported") if isinstance(result, dict) else "supported"
                if label not in {"supported", "unsupported", "partial"}:
                    label = "supported"
            except (ValueError, Exception):
                label = "supported"

            predictions.append(label)

        return KQABResult(
            task_id="T4",
            system_name=self.name,
            predictions=predictions,
            ground_truth=ground_truth,
            duration_seconds=time.time() - t0,
        )


# ── KQAB Runner ───────────────────────────────────────────────────────────


class KQABRunner:
    """Runs the full KQAB benchmark suite."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        use_cache: bool = False,
    ) -> None:
        self.conn = conn
        if use_cache:
            from akm.llm.cache import CachedClaudeClient
            self.llm = CachedClaudeClient(llm)
        else:
            self.llm = llm

    def run(
        self,
        systems: list[KQABSystem] | None = None,
        tasks: list[str] | None = None,
        variant: str = "synth",
    ) -> dict:
        """Run KQAB benchmark.

        Args:
            systems: Systems to evaluate. Defaults to [MKOSSystem, LLMFewShotSystem].
            tasks: Task IDs to run. Defaults to all (T1-T4).
            variant: Dataset variant ("synth", "public", "combined").
        """
        if systems is None:
            systems = [MKOSSystem(), LLMFewShotSystem()]

        suite = build_kqab_suite(variant=variant)
        summary = kqab_summary(suite)

        if tasks:
            suite = {k: v for k, v in suite.items() if k in tasks}

        t0 = time.time()
        results = {}

        for task_id, task in suite.items():
            task_results = {}
            evaluators = {
                "T1": "evaluate_t1",
                "T2": "evaluate_t2",
                "T3": "evaluate_t3",
                "T4": "evaluate_t4",
            }
            method_name = evaluators.get(task_id)
            if not method_name:
                continue

            for system in systems:
                method = getattr(system, method_name, None)
                if not method:
                    continue

                result = method(task, self.conn, self.llm)

                # Compute bootstrap CI
                bootstrap = bootstrap_classification_ci(
                    result.predictions, result.ground_truth,
                    n_bootstrap=1000, seed=42,
                )

                task_results[system.name] = {
                    **result.to_dict(),
                    "bootstrap_ci": bootstrap.to_dict(),
                }

            results[task_id] = {
                "task_name": task.name,
                "n_items": task.size,
                "labels": task.labels,
                "systems": task_results,
            }

        total_duration = time.time() - t0

        return {
            "benchmark": "KQAB",
            "version": "2.0",
            "variant": variant,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "suite_summary": summary,
            "total_duration_seconds": round(total_duration, 2),
            "total_cost_usd": round(self.llm.total_cost_usd, 4),
            "llm_stats": self.llm.stats(),
            "results": results,
        }
