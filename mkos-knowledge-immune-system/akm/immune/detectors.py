"""Threat detectors for the knowledge immune system."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod

from akm.immune.antigens import Threat, ThreatType
from akm.llm.client import ClaudeClient
from akm.search.engine import SearchEngine, sanitize_fts_query


class BaseDetector(ABC):
    """Abstract base for threat detectors."""

    threat_type: ThreatType

    def __init__(self, llm: ClaudeClient, conn: sqlite3.Connection,
                 prefer_fts: bool = False) -> None:
        self.llm = llm
        self.conn = conn
        self.prefer_fts = prefer_fts
        self.search_engine = SearchEngine(conn)

    @abstractmethod
    def scan(self, content: str, chunk_id: int, context: dict | None = None) -> list[Threat]:
        ...


class HallucinationDetector(BaseDetector):
    """Detect potential hallucinations in knowledge content."""

    threat_type = ThreatType.HALLUCINATION

    def scan(self, content: str, chunk_id: int, context: dict | None = None) -> list[Threat]:
        # Retrieve related KB chunks via hybrid search (vector + FTS)
        related = self.search_engine.search_related(content, exclude_id=chunk_id, limit=3, prefer_fts=self.prefer_fts)

        ref_ctx = ""
        if related:
            ref_ctx = "\n\nREFERENCE KNOWLEDGE from the same knowledge base:\n"
            for _id, heading, chunk_content in related:
                ref_ctx += f"- {heading}: {chunk_content[:300]}\n"

        if related:
            system_prompt = (
                "You detect potential hallucinations in knowledge content. "
                "Compare the TARGET against the REFERENCE KNOWLEDGE from the same knowledge base. "
                "Only flag claims that cannot be supported by the reference material AND "
                "appear to contain: unsourced factual claims, implausible statistics, "
                "fabricated references, or overly specific details without basis.\n\n"
                "Respond with JSON:\n"
                '[{"description": "...", "evidence": "the problematic text", "confidence": 0.0-1.0}]\n'
                "Return empty array if no hallucinations detected."
            )
            min_confidence = 0.5
        else:
            system_prompt = (
                "You detect potential hallucinations in knowledge content. "
                "Look for: clearly fabricated facts, impossible statistics, "
                "wrong attributions, and internally contradictory claims.\n"
                "Be CONSERVATIVE -- only flag claims that are clearly false, "
                "not merely unverifiable.\n\n"
                "Respond with JSON:\n"
                '[{"description": "...", "evidence": "the problematic text", "confidence": 0.0-1.0}]\n'
                "Return empty array if no hallucinations detected."
            )
            min_confidence = 0.6

        result = self.llm.extract_json(
            system_prompt=system_prompt,
            user_content=f"TARGET CONTENT:\n{content[:3000]}{ref_ctx}",
        )

        threats = []
        items = result if isinstance(result, list) else []
        for item in items:
            if not isinstance(item, dict) or item.get("confidence", 0) < min_confidence:
                continue
            threats.append(Threat(
                threat_type=ThreatType.HALLUCINATION,
                target_id=chunk_id,
                target_type="chunk",
                confidence=float(item.get("confidence", 0.5)),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                suggested_action="quarantine" if item.get("confidence", 0) > 0.7 else "flag",
            ))
        return threats


class StalenessDetector(BaseDetector):
    """Detect outdated knowledge using temporal markers and domain analysis."""

    threat_type = ThreatType.STALENESS

    def scan(self, content: str, chunk_id: int, context: dict | None = None) -> list[Threat]:
        result = self.llm.extract_json(
            system_prompt=(
                "You detect potentially OUTDATED knowledge. Look for:\n"
                "- References to specific software versions that may be superseded\n"
                "- Date-specific claims that may no longer be true\n"
                "- Deprecated technologies, APIs, or practices\n"
                "- Claims about 'current' or 'latest' that may have changed\n\n"
                "Respond with JSON:\n"
                '[{"description": "...", "evidence": "the outdated text", "confidence": 0.0-1.0}]\n'
                "Return empty array if content appears current."
            ),
            user_content=content[:3000],
        )

        threats = []
        items = result if isinstance(result, list) else []
        for item in items:
            if not isinstance(item, dict) or item.get("confidence", 0) < 0.5:
                continue
            threats.append(Threat(
                threat_type=ThreatType.STALENESS,
                target_id=chunk_id,
                target_type="chunk",
                confidence=float(item.get("confidence", 0.5)),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                suggested_action="compost" if item.get("confidence", 0) > 0.8 else "flag",
            ))
        return threats


class BiasDetector(BaseDetector):
    """Detect bias and perspective monoculture."""

    threat_type = ThreatType.BIAS

    def scan(self, content: str, chunk_id: int, context: dict | None = None) -> list[Threat]:
        result = self.llm.extract_json(
            system_prompt=(
                "You detect BIAS in knowledge content. Look for:\n"
                "- Single-perspective presentation without acknowledging alternatives\n"
                "- Absolutist language ('always', 'never', 'the best') without qualification\n"
                "- Missing counterarguments on controversial topics\n"
                "- Source monoculture (only one viewpoint represented)\n"
                "- Commercial bias (promoting specific products without disclosure)\n\n"
                "Respond with JSON:\n"
                '[{"description": "...", "evidence": "the biased text", "confidence": 0.0-1.0}]\n'
                "Return empty array if content appears balanced."
            ),
            user_content=content[:3000],
        )

        threats = []
        items = result if isinstance(result, list) else []
        for item in items:
            if not isinstance(item, dict) or item.get("confidence", 0) < 0.5:
                continue
            threats.append(Threat(
                threat_type=ThreatType.BIAS,
                target_id=chunk_id,
                target_type="chunk",
                confidence=float(item.get("confidence", 0.5)),
                description=item.get("description", ""),
                evidence=item.get("evidence", ""),
                suggested_action="enrich",
            ))
        return threats


class ContradictionDetector(BaseDetector):
    """Detect contradictions within the knowledge base."""

    threat_type = ThreatType.CONTRADICTION

    def scan(self, content: str, chunk_id: int, context: dict | None = None) -> list[Threat]:
        threats: list[Threat] = []

        # Strategy 1: Check against related chunks via hybrid search (vector + FTS)
        related = self.search_engine.search_related(content, exclude_id=chunk_id, limit=5, prefer_fts=self.prefer_fts)

        if related:
            existing_ctx = ""
            for r_id, heading, chunk_content in related:
                existing_ctx += f"\n[Chunk {r_id}] {heading}:\n{chunk_content[:500]}\n"

            result = self.llm.extract_json(
                system_prompt=(
                    "You detect CONTRADICTIONS between a target chunk and related chunks. "
                    "Only flag genuine factual contradictions, not differences in scope or perspective.\n\n"
                    "Respond with JSON:\n"
                    '[{"description": "...", "evidence": "the contradicting claims", '
                    '"related_chunk_id": 123, "confidence": 0.0-1.0}]\n'
                    "Return empty array if no contradictions found."
                ),
                user_content=f"TARGET CHUNK:\n{content[:1500]}\n\nRELATED CHUNKS:{existing_ctx}",
            )

            items = result if isinstance(result, list) else []
            for item in items:
                if not isinstance(item, dict) or item.get("confidence", 0) < 0.5:
                    continue
                threats.append(Threat(
                    threat_type=ThreatType.CONTRADICTION,
                    target_id=chunk_id,
                    target_type="chunk",
                    confidence=float(item.get("confidence", 0.5)),
                    description=item.get("description", ""),
                    evidence=item.get("evidence", ""),
                    suggested_action="flag",
                ))

        # Strategy 2: Always check against established facts (catches self-contradictions)
        if not threats:
            result = self.llm.extract_json(
                system_prompt=(
                    "You detect statements that CONTRADICT well-established technical facts. "
                    "Only flag claims that are clearly factually wrong, not merely opinionated.\n\n"
                    "Respond with JSON:\n"
                    '[{"description": "...", "evidence": "the contradicting claim", "confidence": 0.0-1.0}]\n'
                    "Return empty array if no contradictions with established facts."
                ),
                user_content=content[:3000],
            )
            items = result if isinstance(result, list) else []
            for item in items:
                if not isinstance(item, dict) or item.get("confidence", 0) < 0.4:
                    continue
                threats.append(Threat(
                    threat_type=ThreatType.CONTRADICTION,
                    target_id=chunk_id,
                    target_type="chunk",
                    confidence=min(0.7, float(item.get("confidence", 0.5))),
                    description=item.get("description", ""),
                    evidence=item.get("evidence", ""),
                    suggested_action="flag",
                ))

        return threats
