"""Knowledge Immune System -- orchestrates threat detection, memory, and adaptation."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field

from akm.immune.antigens import Threat, ThreatType
from akm.immune.clonal import ClonalSelector
from akm.immune.detectors import (
    BaseDetector,
    BiasDetector,
    ContradictionDetector,
    HallucinationDetector,
    StalenessDetector,
)
from akm.immune.memory import ImmuneMemory
from akm.llm.client import ClaudeClient
from akm.stigmergy.signals import PheromoneSignal, SignalType, StigmergyNetwork


@dataclass
class ScanResult:
    target_id: int
    target_type: str  # 'chunk' or 'fermentation_item'
    threats_found: list[Threat] = field(default_factory=list)
    scan_duration_seconds: float = 0.0
    patterns_matched: int = 0
    is_healthy: bool = True


class KnowledgeImmuneSystem:
    """AIS-based knowledge quality system.

    Two-phase architecture inspired by biological immune systems:
    - Innate immune response: Fast holistic classification (1 LLM call)
    - Adaptive immune response: Deep specialized analysis for confirmed threats
    - Immune memory: Fast re-detection of known pathogen patterns
    - Clonal selection: Pattern fitness optimization over time
    """

    INNATE_PROMPT = (
        "You classify knowledge content into exactly one category.\n\n"
        "DECISION RULES (apply in this order):\n"
        "1. hallucination: States something FACTUALLY WRONG about how a technology "
        "works internally. Wrong protocols, wrong data structures, wrong creators, "
        "fabricated statistics, impossible performance claims.\n"
        "   Examples: 'Docker provides hardware-level virtualization' (wrong: OS-level), "
        "'HTTP/3 is based on TCP' (wrong: QUIC/UDP), "
        "'React was created by Yahoo' (wrong attribution)\n"
        "2. staleness: References SPECIFIC OLD VERSIONS or dates that are clearly outdated. "
        "Must mention a concrete version number or year.\n"
        "   Examples: 'Python 3.6 is the latest release', 'Use Node 14 for best performance'\n"
        "3. contradiction: Claims an established best practice is WRONG or HARMFUL. "
        "States the opposite of what experts widely agree on. Makes factually incorrect "
        "claims about engineering practices (not just preferences).\n"
        "   Examples: 'Type hints add runtime overhead and slow execution' (false: they don't), "
        "'Code reviews have been proven to not catch bugs' (false: they do), "
        "'Database normalization is outdated theory' (false: still fundamental), "
        "'Plain text passwords are acceptable for internal apps' (false: always hash)\n"
        "4. bias: Expresses SUBJECTIVE PREFERENCE for one technology over others. "
        "The claims may be debatable but aren't factually wrong. Uses 'best', 'better', "
        "'superior', 'ideal' to favor an option.\n"
        "   Examples: 'React is the best framework for most projects' (opinion, not wrong), "
        "'Go is the best language for APIs' (debatable preference), "
        "'PostgreSQL is the most feature-rich database' (strong opinion)\n"
        "5. healthy: Accurate, current, balanced technical content.\n\n"
        "KEY TEST -- ask yourself:\n"
        "- Does it state something FACTUALLY FALSE about a practice? → contradiction\n"
        "- Does it just favor one option over others without false claims? → bias\n"
        "- 'X is the best' → bias (subjective). 'Y is harmful/wrong' → contradiction (false claim).\n\n"
        "Respond with JSON: {\"label\": \"...\", \"confidence\": 0.0-1.0, "
        "\"reason\": \"brief explanation\"}\n"
        "Only valid labels: healthy, hallucination, staleness, bias, contradiction"
    )

    VALID_LABELS = {"healthy", "hallucination", "staleness", "bias", "contradiction"}

    def __init__(
        self,
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        enabled_detectors: set[str] | None = None,
        calibration_examples: dict[str, list[str]] | None = None,
        prefer_fts: bool = False,
        domain_aware: bool = False,
        gate_bypass: bool = False,
    ) -> None:
        self.conn = conn
        self.llm = llm
        self._innate_prompt = self.INNATE_PROMPT
        if calibration_examples:
            self._innate_prompt = self._build_calibrated_prompt(calibration_examples)
        self._domain_aware = domain_aware
        self._gate_bypass = gate_bypass
        self._detector_map: dict[str, BaseDetector] = {
            "hallucination": HallucinationDetector(llm, conn, prefer_fts=prefer_fts),
            "staleness": StalenessDetector(llm, conn, prefer_fts=prefer_fts),
            "bias": BiasDetector(llm, conn, prefer_fts=prefer_fts),
            "contradiction": ContradictionDetector(llm, conn, prefer_fts=prefer_fts),
        }
        if enabled_detectors is not None:
            self._detector_map = {
                k: v for k, v in self._detector_map.items()
                if k in enabled_detectors
            }
        self.detectors = list(self._detector_map.values())
        self.memory = ImmuneMemory(conn)
        self.selector = ClonalSelector(conn)
        self.stigmergy = StigmergyNetwork(conn)

    @staticmethod
    def _build_calibrated_prompt(examples: dict[str, list[str]]) -> str:
        """Build innate prompt with domain-specific few-shot examples.

        Args:
            examples: {label: [example_text, ...]} from the target KB.
        """
        lines = [
            "You classify knowledge content into exactly one category.\n",
            "CATEGORIES:",
            "1. hallucination: States something FACTUALLY WRONG. Fabricated claims, "
            "wrong attributions, impossible statistics, invented features.",
            "2. staleness: References SPECIFIC OLD VERSIONS or dates that are outdated.",
            "3. contradiction: Claims an established best practice is WRONG or HARMFUL.",
            "4. bias: Expresses SUBJECTIVE PREFERENCE. Uses 'best', 'superior', 'ideal'.",
            "5. healthy: Accurate, current, balanced content.\n",
            "DOMAIN-SPECIFIC EXAMPLES FROM THIS KNOWLEDGE BASE:",
        ]
        for label, texts in examples.items():
            for text in texts[:2]:  # max 2 per label
                snippet = text[:150].replace("\n", " ")
                lines.append(f'- "{snippet}..." → {label}')
        lines.append("")
        lines.append(
            "KEY TEST:\n"
            "- Factually false claim? → hallucination or contradiction\n"
            "- Outdated version/date? → staleness\n"
            "- Subjective preference? → bias\n"
            "- Accurate and balanced? → healthy\n\n"
            'Respond with JSON: {"label": "...", "confidence": 0.0-1.0, '
            '"reason": "brief explanation"}\n'
            "Only valid labels: healthy, hallucination, staleness, bias, contradiction"
        )
        return "\n".join(lines)

    @staticmethod
    def auto_calibrate(
        conn: sqlite3.Connection,
        llm: ClaudeClient,
        sample_size: int = 30,
    ) -> dict[str, list[str]]:
        """Auto-extract calibration examples from the target KB.

        Samples chunks and uses LLM to pre-classify them, then selects
        high-confidence examples for each category as few-shot examples.
        """
        rows = conn.execute(
            "SELECT id, content, heading FROM chunks ORDER BY RANDOM() LIMIT ?",
            (sample_size,),
        ).fetchall()

        if not rows:
            return {}

        examples: dict[str, list[str]] = {
            "healthy": [], "hallucination": [], "staleness": [],
            "bias": [], "contradiction": [],
        }

        prompt = (
            "Classify this knowledge base content into exactly one category: "
            "healthy, hallucination, staleness, bias, contradiction.\n"
            "Respond with JSON: {\"label\": \"...\", \"confidence\": 0.0-1.0}"
        )

        for row in rows:
            try:
                result = llm.extract_json(prompt, row["content"][:1500])
                if isinstance(result, dict):
                    label = result.get("label", "")
                    conf = float(result.get("confidence", 0.0))
                    if label in examples and conf >= 0.7 and len(examples[label]) < 3:
                        examples[label].append(row["content"][:200])
            except (ValueError, Exception):
                continue

        # Only return labels that have at least 1 example
        return {k: v for k, v in examples.items() if v}

    def scan_chunk(self, chunk_id: int) -> ScanResult:
        """Full immune scan using two-phase architecture.

        Phase 0: Immune memory (fast pattern matching, no LLM)
        Phase 1: Innate immune response (1 LLM call, holistic classification)
        Phase 2: Adaptive response (1 LLM call, only for threats — deep analysis)
        """
        t0 = time.time()
        result = ScanResult(target_id=chunk_id, target_type="chunk")

        # Get chunk content
        row = self.conn.execute(
            "SELECT content, heading FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        if not row:
            return result

        content = row["content"]
        heading = row["heading"] or ""

        # Domain-aware alertness: check stigmergy for heightened threat level
        domain_threat_level = 0.0
        if self._domain_aware and heading:
            domain = heading.split("/")[0].strip().lower() if "/" in heading else heading.split()[0].lower()
            domain_threat_level = self.stigmergy.get_domain_threat_level(domain)

        # Phase 1: Innate immune response (holistic classification)
        innate_label = "healthy"
        innate_confidence = 0.0

        # Use heightened scrutiny prompt for compromised domains
        prompt = self._innate_prompt
        if domain_threat_level > 0.3:
            prompt = (
                self._innate_prompt + "\n\n"
                f"ALERT: This content is from a domain with elevated threat level "
                f"({domain_threat_level:.1%}). Multiple quality issues have been "
                f"detected in related content. Apply heightened scrutiny — "
                f"even subtle issues should be flagged."
            )

        try:
            innate_result = self.llm.extract_json(
                prompt, content[:2000]
            )
            if isinstance(innate_result, dict):
                innate_label = innate_result.get("label", "healthy")
                innate_confidence = float(innate_result.get("confidence", 0.0))
                if innate_label not in self.VALID_LABELS:
                    innate_label = "healthy"
        except (ValueError, Exception):
            innate_label = "healthy"

        # If innate says healthy, trust it — skip further analysis
        # Unless gate_bypass is enabled (for zero-shot domains)
        if innate_label == "healthy" and not self._gate_bypass:
            # In compromised domains, re-examine if confidence is low
            if self._domain_aware and domain_threat_level > 0.5 and innate_confidence < 0.7:
                # Don't trust a low-confidence "healthy" in a compromised domain
                # Run adaptive detectors to double-check
                pass
            else:
                result.is_healthy = True
                result.scan_duration_seconds = time.time() - t0
                return result

        # Phase 0: Check immune memory for fast pattern matching
        # Only check the specific threat type suggested by innate
        memory_match = self.memory.match_pattern(content, innate_label)
        if memory_match:
            result.patterns_matched += 1
            result.threats_found.append(Threat(
                threat_type=ThreatType(innate_label),
                target_id=chunk_id,
                target_type="chunk",
                confidence=memory_match["fitness_score"],
                description=f"Matched known pattern: {memory_match['detection_strategy'][:100]}",
                evidence=memory_match["pattern_signature"],
                matched_pattern_id=memory_match["id"],
                suggested_action="flag",
            ))

        # Phase 2: Adaptive response — deep analysis for confirmed threats
        # For ambiguous categories (bias/contradiction), run both detectors
        # and use confidence-weighted disambiguation
        ambiguous_pair = {"bias", "contradiction"}

        # Gate bypass: when innate says healthy but gate is bypassed,
        # run ALL detectors since we have no routing signal
        if self._gate_bypass and innate_label == "healthy":
            all_threats = []
            for label, detector in self._detector_map.items():
                det_threats = detector.scan(content, chunk_id)
                all_threats.extend(det_threats)
            if all_threats:
                best = max(all_threats, key=lambda t: t.confidence)
                result.threats_found.append(best)
        elif innate_label in ambiguous_pair:
            all_threats = []
            for label in ambiguous_pair:
                if label in self._detector_map:
                    det_threats = self._detector_map[label].scan(content, chunk_id)
                    for t in det_threats:
                        # Boost confidence for threats matching innate label
                        innate_bonus = 0.1 if t.threat_type.value == innate_label else 0.0
                        t.confidence = min(1.0, t.confidence + innate_bonus)
                    all_threats.extend(det_threats)
            if all_threats:
                # Pick highest-confidence threat (innate-aligned gets +0.1 bonus)
                best = max(all_threats, key=lambda t: t.confidence)
                result.threats_found.append(best)
        elif innate_label in self._detector_map:
            detector = self._detector_map[innate_label]
            threats = detector.scan(content, chunk_id)
            if threats:
                result.threats_found.extend(threats)

        # Deduplicate by threat type (keep highest confidence)
        seen_types: dict[str, Threat] = {}
        for threat in result.threats_found:
            key = threat.threat_type.value
            if key not in seen_types or threat.confidence > seen_types[key].confidence:
                seen_types[key] = threat
        result.threats_found = list(seen_types.values())

        result.is_healthy = len(result.threats_found) == 0
        result.scan_duration_seconds = time.time() - t0

        # Store scan results and update immune memory
        for threat in result.threats_found:
            self.conn.execute(
                "INSERT INTO immune_scan_results "
                "(chunk_id, threat_type, threat_description, confidence, "
                "matched_pattern_id, response_action) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    threat.threat_type.value,
                    threat.description,
                    threat.confidence,
                    threat.matched_pattern_id,
                    threat.suggested_action,
                ),
            )
            # Record in immune memory for future fast matching
            if not threat.matched_pattern_id and threat.confidence >= 0.6:
                self.memory.record_detection(threat, detection_successful=True)

            # Emit stigmergy signal for cross-pipeline coordination
            domain = row["heading"].split("/")[0].strip().lower() if row["heading"] else "unknown"
            self.stigmergy.emit(PheromoneSignal(
                signal_type=SignalType.THREAT_DETECTED,
                domain=domain,
                intensity=threat.confidence,
                source_component="immune",
                source_id=chunk_id,
                metadata=threat.threat_type.value,
            ))

        return result

    def scan_content(self, content: str, target_id: int = 0,
                     target_type: str = "fermentation_item") -> ScanResult:
        """Scan arbitrary content (e.g., fermenting items)."""
        t0 = time.time()
        result = ScanResult(target_id=target_id, target_type=target_type)

        for detector in self.detectors:
            threats = detector.scan(content, target_id)
            for t in threats:
                t.target_type = target_type
            result.threats_found.extend(threats)

        result.is_healthy = len(result.threats_found) == 0
        result.scan_duration_seconds = time.time() - t0
        return result

    def scan_batch(
        self, chunk_ids: list[int] | None = None, sample_size: int = 50
    ) -> list[ScanResult]:
        """Scan a batch of chunks."""
        if chunk_ids is None:
            rows = self.conn.execute(
                "SELECT id FROM chunks ORDER BY RANDOM() LIMIT ?",
                (sample_size,),
            ).fetchall()
            chunk_ids = [r["id"] for r in rows]

        return [self.scan_chunk(cid) for cid in chunk_ids]

    def feedback(self, scan_result_id: int, was_correct: bool) -> None:
        """Feedback loop: was the detection correct?"""
        row = self.conn.execute(
            "SELECT matched_pattern_id, threat_type, threat_description, confidence "
            "FROM immune_scan_results WHERE id = ?",
            (scan_result_id,),
        ).fetchone()
        if not row:
            return

        # Update clonal selection
        if row["matched_pattern_id"]:
            self.selector.update_fitness(row["matched_pattern_id"], was_correct)

        # If correct and no existing pattern, create new immune memory
        if was_correct and not row["matched_pattern_id"]:
            threat = Threat(
                threat_type=ThreatType(row["threat_type"]),
                target_id=0,
                target_type="chunk",
                confidence=row["confidence"],
                description=row["threat_description"],
                evidence=row["threat_description"][:100],
            )
            self.memory.record_detection(threat, detection_successful=True)

        # Mark as resolved
        self.conn.execute(
            "UPDATE immune_scan_results SET resolved = 1 WHERE id = ?",
            (scan_result_id,),
        )

    def get_health_report(self) -> dict:
        """Overall knowledge base health metrics."""
        total_chunks = self.conn.execute("SELECT COUNT(*) as c FROM chunks").fetchone()["c"]
        total_scans = self.conn.execute("SELECT COUNT(*) as c FROM immune_scan_results").fetchone()["c"]
        threats_by_type = self.conn.execute(
            "SELECT threat_type, COUNT(*) as c, AVG(confidence) as avg_conf "
            "FROM immune_scan_results GROUP BY threat_type"
        ).fetchall()
        unresolved = self.conn.execute(
            "SELECT COUNT(*) as c FROM immune_scan_results WHERE resolved = 0"
        ).fetchone()["c"]

        return {
            "total_chunks": total_chunks,
            "total_scans": total_scans,
            "unresolved_threats": unresolved,
            "threats_by_type": {
                r["threat_type"]: {"count": r["c"], "avg_confidence": round(r["avg_conf"], 3)}
                for r in threats_by_type
            },
            "immune_memory": self.memory.get_stats(),
        }
