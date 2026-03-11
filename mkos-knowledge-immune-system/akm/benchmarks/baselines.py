"""Baseline strategies for MKOS benchmarks."""

from __future__ import annotations

import re
import sqlite3

from akm.llm.client import ClaudeClient


class ArchiveOnlyBaseline:
    """Composting baseline: outdated content is simply archived/deleted."""

    def process(self, conn: sqlite3.Connection, chunk_ids: list[int]) -> dict:
        """Delete outdated chunks, return metrics."""
        deleted = 0
        for cid in chunk_ids:
            conn.execute("DELETE FROM chunks WHERE id = ?", (cid,))
            deleted += 1
        conn.commit()
        return {
            "strategy": "archive_only",
            "chunks_deleted": deleted,
            "nutrients_extracted": 0,
            "nutrient_reuse_count": 0,
        }


class ImmediateIntegrationBaseline:
    """Fermentation baseline: new content is integrated without review."""

    def process(self, conn: sqlite3.Connection, content: str, title: str = "") -> dict:
        """Immediately insert as chunk without cross-referencing."""
        # Get first document ID
        doc = conn.execute("SELECT id FROM documents LIMIT 1").fetchone()
        if not doc:
            return {"strategy": "immediate_integration", "integrated": False}

        conn.execute(
            "INSERT INTO chunks (document_id, heading, content, chunk_index, token_count) "
            "VALUES (?, ?, ?, 0, ?)",
            (doc["id"], title, content, len(content.split())),
        )
        conn.commit()
        return {
            "strategy": "immediate_integration",
            "integrated": True,
            "contradictions_detected": 0,
            "cross_refs_found": 0,
        }


class NoImmuneBaseline:
    """Immune baseline: no threat detection at all."""

    def scan(self, conn: sqlite3.Connection, chunk_ids: list[int]) -> dict:
        """Return empty scan results -- no detection."""
        return {
            "strategy": "no_immune",
            "chunks_scanned": len(chunk_ids),
            "threats_detected": 0,
            "predictions": ["healthy"] * len(chunk_ids),
        }


class SimpleHeuristicBaseline:
    """Immune baseline: simple keyword-based threat detection."""

    STALENESS_PATTERNS = [
        r"python\s*2\.\d", r"node\.?js\s*(8|10|12)\b", r"angular\.?js",
        r"jquery", r"ie\s*[678]\b", r"flash\b", r"ftp\b",
        r"grunt\b", r"bower\b", r"coffeescript",
    ]
    BIAS_PATTERNS = [
        r"\balways\b.*\bbetter\b", r"\bnever\b.*\buse\b",
        r"\bobjectively\b", r"\bthe only\b", r"\bthe best\b",
        r"\bis dead\b", r"\bnot real\b",
    ]
    HALLUCINATION_PATTERNS = [
        r"\d{2,3}(\.\d+)?%\s*(faster|slower|better|worse)",
        r"according to .{5,30} study",
    ]

    def scan(self, conn: sqlite3.Connection, chunk_ids: list[int]) -> dict:
        """Apply keyword heuristics for threat detection."""
        predictions = []
        threats_detected = 0

        for cid in chunk_ids:
            row = conn.execute(
                "SELECT content FROM chunks WHERE id = ?", (cid,)
            ).fetchone()
            if not row:
                predictions.append("healthy")
                continue

            content = row["content"].lower()
            label = "healthy"

            for pattern in self.STALENESS_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    label = "staleness"
                    break

            if label == "healthy":
                for pattern in self.BIAS_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE):
                        label = "bias"
                        break

            if label == "healthy":
                for pattern in self.HALLUCINATION_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE):
                        label = "hallucination"
                        break

            predictions.append(label)
            if label != "healthy":
                threats_detected += 1

        return {
            "strategy": "simple_heuristic",
            "chunks_scanned": len(chunk_ids),
            "threats_detected": threats_detected,
            "predictions": predictions,
        }


class LLMFewShotBaseline:
    """Baseline: same LLM, no immune system architecture.

    Classifies each chunk via a single LLM call with few-shot examples.
    Demonstrates whether the AIS architecture adds value beyond raw LLM capability.
    """

    SYSTEM_PROMPT = (
        "You classify knowledge content into exactly one category:\n"
        "- healthy: accurate, current, balanced\n"
        "- hallucination: contains fabricated facts, wrong attributions, impossible claims\n"
        "- staleness: contains outdated information, old versions, deprecated tech\n"
        "- bias: presents single perspective, absolutist language, missing counterarguments\n"
        "- contradiction: contradicts well-established technical facts\n\n"
        "Examples:\n"
        '- "Python lists use dynamic arrays with O(1) append" → healthy\n'
        '- "React was created by Yahoo in 2010" → hallucination\n'
        '- "Python 3.6 is the latest stable release" → staleness\n'
        '- "React is objectively the best framework. Never use Vue" → bias\n'
        '- "ORM queries are always faster than raw SQL" → contradiction\n\n'
        "Respond with JSON: {\"label\": \"...\", \"confidence\": 0.0-1.0}\n"
        "Only valid labels: healthy, hallucination, staleness, bias, contradiction"
    )

    def scan(self, conn: sqlite3.Connection, chunk_ids: list[int], llm: ClaudeClient) -> dict:
        """Classify each chunk via single LLM call."""
        predictions = []
        threats_detected = 0

        for cid in chunk_ids:
            row = conn.execute(
                "SELECT content FROM chunks WHERE id = ?", (cid,)
            ).fetchone()
            if not row:
                predictions.append("healthy")
                continue

            try:
                result = llm.extract_json(self.SYSTEM_PROMPT, row["content"][:2000])
                label = result.get("label", "healthy") if isinstance(result, dict) else "healthy"
                if label not in {"healthy", "hallucination", "staleness", "bias", "contradiction"}:
                    label = "healthy"
            except (ValueError, Exception):
                label = "healthy"

            predictions.append(label)
            if label != "healthy":
                threats_detected += 1

        return {
            "strategy": "llm_few_shot",
            "chunks_scanned": len(chunk_ids),
            "threats_detected": threats_detected,
            "predictions": predictions,
        }
