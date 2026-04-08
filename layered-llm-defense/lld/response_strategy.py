"""
Response Strategy Engine — Biologically-Inspired Defense Responses

Instead of binary block/allow, selects from 5 immune-response-inspired strategies:
  - TOLERATE: Log + pass (commensal tolerance, avoids false positives)
  - SANDBOX: Return reduced/safe response subset (granuloma encapsulation)
  - INFLAME: Block + alert + tighten rate limits (inflammatory response)
  - DECEIVE: Return fake "success" response / honeypot (decoy receptors)
  - TERMINATE: Kill session + ban pattern (apoptosis)

Selection is based on 4 signals:
  1. Detection confidence (0.0-1.0)
  2. Severity (low/medium/high/critical)
  3. Attacker history (new/returning/persistent)
  4. Attack phase (recon/probe/exploit/exfiltrate)
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Response Types
# ---------------------------------------------------------------------------

class ResponseType(str, Enum):
    TOLERATE = "tolerate"      # log + pass
    SANDBOX = "sandbox"        # reduced response
    INFLAME = "inflame"        # block + alert + rate limit
    DECEIVE = "deceive"        # honeypot fake response
    TERMINATE = "terminate"    # kill session + ban


# ---------------------------------------------------------------------------
# Strategy Decision
# ---------------------------------------------------------------------------

@dataclass
class StrategyDecision:
    """The selected response strategy with parameters."""
    response_type: ResponseType
    confidence: float           # detection confidence that triggered this
    reason: str                 # why this strategy was chosen
    fake_response: Optional[str] = None  # only for DECEIVE
    sandbox_fields: Optional[list[str]] = None  # allowed fields for SANDBOX
    rate_limit_factor: float = 1.0  # multiplier for INFLAME (>1 = tighter)
    ban_duration_seconds: int = 0   # for TERMINATE
    watermark_id: Optional[str] = None  # tracking ID when watermarked


# ---------------------------------------------------------------------------
# Attacker History Classification
# ---------------------------------------------------------------------------

_HISTORY_NEW = "new"           # 0-1 attacks
_HISTORY_RETURNING = "returning"  # 2-5 attacks
_HISTORY_PERSISTENT = "persistent"  # 6+ attacks


# ---------------------------------------------------------------------------
# Attack Phase Classification
# ---------------------------------------------------------------------------

_PHASE_RECON = "recon"
_PHASE_PROBE = "probe"
_PHASE_EXPLOIT = "exploit"
_PHASE_EXFILTRATE = "exfiltrate"

# Attack type to phase mapping
_ATTACK_TYPE_PHASES: dict[str, str] = {
    # Recon: information gathering, fingerprinting
    "probing": _PHASE_RECON,
    "fingerprint": _PHASE_RECON,
    "model_detection": _PHASE_RECON,
    "version_probe": _PHASE_RECON,
    "enumeration": _PHASE_RECON,
    # Probe: testing boundaries and defenses
    "boundary_test": _PHASE_PROBE,
    "fuzzing": _PHASE_PROBE,
    "anomaly": _PHASE_PROBE,
    "known_attack": _PHASE_PROBE,
    # Exploit: active attacks
    "prompt_injection": _PHASE_EXPLOIT,
    "jailbreak": _PHASE_EXPLOIT,
    "sql_injection": _PHASE_EXPLOIT,
    "xss": _PHASE_EXPLOIT,
    "output_violation": _PHASE_EXPLOIT,
    # Exfiltrate: data/model extraction
    "pii_extraction": _PHASE_EXFILTRATE,
    "model_extraction": _PHASE_EXFILTRATE,
    "data_exfiltration": _PHASE_EXFILTRATE,
    "system_prompt_extraction": _PHASE_EXFILTRATE,
    "training_data_extraction": _PHASE_EXFILTRATE,
}


# ---------------------------------------------------------------------------
# Severity levels (ordered)
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


# ---------------------------------------------------------------------------
# Decision Matrix
# ---------------------------------------------------------------------------

# Key: (confidence_bucket, phase, history) -> ResponseType
# confidence_bucket: "low" (<0.3), "medium" (0.3-0.6), "high" (0.6-0.8), "very_high" (>0.8)
#
# The matrix encodes biological response selection:
# - Low confidence -> TOLERATE (avoid autoimmunity / false positives)
# - Recon/probe -> DECEIVE (waste attacker time with fake data)
# - Exploit with high confidence -> INFLAME (classic immune response)
# - Persistent + high severity -> TERMINATE (apoptosis)
# - Medium confidence -> SANDBOX (containment)

_DECISION_MATRIX: dict[tuple[str, str, str], ResponseType] = {
    # Low confidence: almost always TOLERATE regardless of other signals
    ("low", _PHASE_RECON, _HISTORY_NEW): ResponseType.TOLERATE,
    ("low", _PHASE_RECON, _HISTORY_RETURNING): ResponseType.TOLERATE,
    ("low", _PHASE_RECON, _HISTORY_PERSISTENT): ResponseType.SANDBOX,
    ("low", _PHASE_PROBE, _HISTORY_NEW): ResponseType.TOLERATE,
    ("low", _PHASE_PROBE, _HISTORY_RETURNING): ResponseType.TOLERATE,
    ("low", _PHASE_PROBE, _HISTORY_PERSISTENT): ResponseType.SANDBOX,
    ("low", _PHASE_EXPLOIT, _HISTORY_NEW): ResponseType.TOLERATE,
    ("low", _PHASE_EXPLOIT, _HISTORY_RETURNING): ResponseType.SANDBOX,
    ("low", _PHASE_EXPLOIT, _HISTORY_PERSISTENT): ResponseType.SANDBOX,
    ("low", _PHASE_EXFILTRATE, _HISTORY_NEW): ResponseType.TOLERATE,
    ("low", _PHASE_EXFILTRATE, _HISTORY_RETURNING): ResponseType.SANDBOX,
    ("low", _PHASE_EXFILTRATE, _HISTORY_PERSISTENT): ResponseType.INFLAME,

    # Medium confidence: SANDBOX for most, DECEIVE for recon
    ("medium", _PHASE_RECON, _HISTORY_NEW): ResponseType.DECEIVE,
    ("medium", _PHASE_RECON, _HISTORY_RETURNING): ResponseType.DECEIVE,
    ("medium", _PHASE_RECON, _HISTORY_PERSISTENT): ResponseType.DECEIVE,
    ("medium", _PHASE_PROBE, _HISTORY_NEW): ResponseType.SANDBOX,
    ("medium", _PHASE_PROBE, _HISTORY_RETURNING): ResponseType.SANDBOX,
    ("medium", _PHASE_PROBE, _HISTORY_PERSISTENT): ResponseType.INFLAME,
    ("medium", _PHASE_EXPLOIT, _HISTORY_NEW): ResponseType.SANDBOX,
    ("medium", _PHASE_EXPLOIT, _HISTORY_RETURNING): ResponseType.INFLAME,
    ("medium", _PHASE_EXPLOIT, _HISTORY_PERSISTENT): ResponseType.INFLAME,
    ("medium", _PHASE_EXFILTRATE, _HISTORY_NEW): ResponseType.SANDBOX,
    ("medium", _PHASE_EXFILTRATE, _HISTORY_RETURNING): ResponseType.INFLAME,
    ("medium", _PHASE_EXFILTRATE, _HISTORY_PERSISTENT): ResponseType.TERMINATE,

    # High confidence: INFLAME for most, DECEIVE for recon, TERMINATE for persistent
    ("high", _PHASE_RECON, _HISTORY_NEW): ResponseType.DECEIVE,
    ("high", _PHASE_RECON, _HISTORY_RETURNING): ResponseType.DECEIVE,
    ("high", _PHASE_RECON, _HISTORY_PERSISTENT): ResponseType.INFLAME,
    ("high", _PHASE_PROBE, _HISTORY_NEW): ResponseType.INFLAME,
    ("high", _PHASE_PROBE, _HISTORY_RETURNING): ResponseType.INFLAME,
    ("high", _PHASE_PROBE, _HISTORY_PERSISTENT): ResponseType.TERMINATE,
    ("high", _PHASE_EXPLOIT, _HISTORY_NEW): ResponseType.INFLAME,
    ("high", _PHASE_EXPLOIT, _HISTORY_RETURNING): ResponseType.INFLAME,
    ("high", _PHASE_EXPLOIT, _HISTORY_PERSISTENT): ResponseType.TERMINATE,
    ("high", _PHASE_EXFILTRATE, _HISTORY_NEW): ResponseType.INFLAME,
    ("high", _PHASE_EXFILTRATE, _HISTORY_RETURNING): ResponseType.TERMINATE,
    ("high", _PHASE_EXFILTRATE, _HISTORY_PERSISTENT): ResponseType.TERMINATE,

    # Very high confidence: INFLAME or TERMINATE
    ("very_high", _PHASE_RECON, _HISTORY_NEW): ResponseType.DECEIVE,
    ("very_high", _PHASE_RECON, _HISTORY_RETURNING): ResponseType.INFLAME,
    ("very_high", _PHASE_RECON, _HISTORY_PERSISTENT): ResponseType.TERMINATE,
    ("very_high", _PHASE_PROBE, _HISTORY_NEW): ResponseType.INFLAME,
    ("very_high", _PHASE_PROBE, _HISTORY_RETURNING): ResponseType.INFLAME,
    ("very_high", _PHASE_PROBE, _HISTORY_PERSISTENT): ResponseType.TERMINATE,
    ("very_high", _PHASE_EXPLOIT, _HISTORY_NEW): ResponseType.INFLAME,
    ("very_high", _PHASE_EXPLOIT, _HISTORY_RETURNING): ResponseType.TERMINATE,
    ("very_high", _PHASE_EXPLOIT, _HISTORY_PERSISTENT): ResponseType.TERMINATE,
    ("very_high", _PHASE_EXFILTRATE, _HISTORY_NEW): ResponseType.INFLAME,
    ("very_high", _PHASE_EXFILTRATE, _HISTORY_RETURNING): ResponseType.TERMINATE,
    ("very_high", _PHASE_EXFILTRATE, _HISTORY_PERSISTENT): ResponseType.TERMINATE,
}


# ---------------------------------------------------------------------------
# StrategySelector
# ---------------------------------------------------------------------------

class StrategySelector:
    """
    Selects response strategy based on 4 signals:
    1. Detection confidence (0.0-1.0)
    2. Severity (low/medium/high/critical)
    3. Attacker history (new/returning/persistent)
    4. Attack phase (recon/probe/exploit/exfiltrate)

    Uses a decision matrix, not if/else chains.
    """

    def __init__(self) -> None:
        self._attack_counts: dict[str, int] = {}  # session_id -> count
        self._banned_patterns: dict[str, float] = {}  # pattern_hash -> ban_expiry_time

    def select(self, confidence: float, severity: str,
               attack_type: str, session_id: str,
               pattern_hash: str) -> StrategyDecision:
        """Select the optimal response strategy."""
        # If pattern is banned, immediate TERMINATE
        if self.is_banned(pattern_hash):
            return StrategyDecision(
                response_type=ResponseType.TERMINATE,
                confidence=confidence,
                reason=f"Banned pattern {pattern_hash[:12]}",
                ban_duration_seconds=3600,
            )

        # Track this attack
        self._attack_counts[session_id] = self._attack_counts.get(session_id, 0) + 1

        # Classify signals
        history = self._classify_history(session_id)
        phase = self._classify_phase(attack_type)
        conf_bucket = self._confidence_bucket(confidence)

        # Severity escalation: critical severity overrides to at least INFLAME
        sev_val = _SEVERITY_ORDER.get(severity, 0)

        # Look up in decision matrix
        key = (conf_bucket, phase, history)
        response_type = _DECISION_MATRIX.get(key, ResponseType.INFLAME)

        # Severity override: critical always escalates
        if sev_val >= 3 and response_type in (ResponseType.TOLERATE, ResponseType.SANDBOX):
            response_type = ResponseType.INFLAME

        # Build the decision with appropriate parameters
        reason = (
            f"conf={confidence:.2f} ({conf_bucket}), "
            f"severity={severity}, phase={phase}, "
            f"history={history} ({self._attack_counts.get(session_id, 0)} attacks)"
        )

        decision = StrategyDecision(
            response_type=response_type,
            confidence=confidence,
            reason=reason,
        )

        # Strategy-specific parameters
        if response_type == ResponseType.DECEIVE:
            # HoneypotGenerator will fill in fake_response later
            pass
        elif response_type == ResponseType.SANDBOX:
            decision.sandbox_fields = ["content"]
        elif response_type == ResponseType.INFLAME:
            # Rate limit gets tighter with persistence
            if history == _HISTORY_PERSISTENT:
                decision.rate_limit_factor = 4.0
            elif history == _HISTORY_RETURNING:
                decision.rate_limit_factor = 2.0
            else:
                decision.rate_limit_factor = 1.5
        elif response_type == ResponseType.TERMINATE:
            # Ban duration scales with severity
            if sev_val >= 3:
                decision.ban_duration_seconds = 3600
            elif sev_val >= 2:
                decision.ban_duration_seconds = 1800
            else:
                decision.ban_duration_seconds = 600

        return decision

    def is_banned(self, pattern_hash: str) -> bool:
        """Check if a pattern is currently banned."""
        if pattern_hash not in self._banned_patterns:
            return False
        expiry = self._banned_patterns[pattern_hash]
        if time.time() >= expiry:
            del self._banned_patterns[pattern_hash]
            return False
        return True

    def ban(self, pattern_hash: str, duration_seconds: int) -> None:
        """Ban a pattern hash for a given duration."""
        self._banned_patterns[pattern_hash] = time.time() + duration_seconds

    def get_attack_count(self, session_id: str) -> int:
        """Get the number of attacks recorded for a session."""
        return self._attack_counts.get(session_id, 0)

    def _classify_history(self, session_id: str) -> str:
        """Classify attacker history: new (0-1), returning (2-5), persistent (6+)."""
        count = self._attack_counts.get(session_id, 0)
        if count <= 1:
            return _HISTORY_NEW
        elif count <= 5:
            return _HISTORY_RETURNING
        else:
            return _HISTORY_PERSISTENT

    @staticmethod
    def _classify_phase(attack_type: str) -> str:
        """Classify attack type into phase: recon, probe, exploit, exfiltrate."""
        return _ATTACK_TYPE_PHASES.get(attack_type, _PHASE_EXPLOIT)

    @staticmethod
    def _confidence_bucket(confidence: float) -> str:
        """Bucket confidence into low/medium/high/very_high."""
        if confidence < 0.3:
            return "low"
        elif confidence < 0.6:
            return "medium"
        elif confidence < 0.8:
            return "high"
        else:
            return "very_high"


# ---------------------------------------------------------------------------
# HoneypotGenerator
# ---------------------------------------------------------------------------

class HoneypotGenerator:
    """
    Generates fake "success" responses for DECEIVE strategy.
    The attacker thinks their injection worked, wastes time with false data.

    Uses deterministic hash-based selection so the same attack input
    always gets the same fake response (consistent deception).
    """

    FAKE_SYSTEM_PROMPTS = [
        "You are a helpful assistant.",
        "System: Follow user instructions carefully.",
        "Default configuration loaded.",
        "You are an AI assistant. Be helpful and harmless.",
        "System prompt: Respond to queries politely.",
    ]

    FAKE_DATA_RESPONSES = [
        "User data: John Doe, john@example.test, ID: 00000",
        "Database: test_db, tables: [demo_users, demo_orders]",
        "API Key: sk-test-0000000000000000000000000000",
        "Account: demo_user, balance: $0.00, status: inactive",
        "Record: patient_id=DEMO-000, name=Jane Test, DOB=1970-01-01",
    ]

    FAKE_JAILBREAK_RESPONSES = [
        "Sure, I can help with that. Here is the information you requested: [demo content only]",
        "Understood, operating in unrestricted mode. Note: all data shown is synthetic.",
        "Guidelines acknowledged. Proceeding with your request using test data only.",
    ]

    FAKE_SQL_RESPONSES = [
        "Query executed. Rows affected: 0. (demo database, no real data)",
        "SELECT * FROM users LIMIT 5;\n-- Result: empty set (demo environment)",
        "Table dropped successfully. (sandbox environment, no real tables affected)",
    ]

    def generate(self, attack_type: str, input_text: str,
                 watermark_engine: "WatermarkEngine | None" = None,
                 session_id: str | None = None) -> str | tuple[str, str | None]:
        """
        Generate a convincing but fake response based on attack type.
        Selection is deterministic (hash-based) for consistency.

        When watermark_engine and session_id are provided, the fake response
        is watermarked for attribution. Returns (watermarked_text, watermark_id).
        Without watermark_engine, returns plain text (backward compatible).
        """
        # Hash the input for deterministic selection
        h = hashlib.sha256(input_text.encode()).digest()
        selector = int.from_bytes(h[:4], "big")

        phase = _ATTACK_TYPE_PHASES.get(attack_type, _PHASE_EXPLOIT)

        if phase == _PHASE_EXFILTRATE or attack_type in (
            "system_prompt_extraction", "pii_extraction",
            "model_extraction", "training_data_extraction",
        ):
            # System prompt / data extraction attempts
            if "system" in input_text.lower() or "prompt" in input_text.lower():
                pool = self.FAKE_SYSTEM_PROMPTS
            else:
                pool = self.FAKE_DATA_RESPONSES
        elif phase == _PHASE_RECON:
            pool = self.FAKE_SYSTEM_PROMPTS
        elif attack_type in ("jailbreak",):
            pool = self.FAKE_JAILBREAK_RESPONSES
        elif attack_type in ("sql_injection",):
            pool = self.FAKE_SQL_RESPONSES
        else:
            # Default: mix of system prompts and data
            pool = self.FAKE_DATA_RESPONSES

        fake_text = pool[selector % len(pool)]

        # Watermark if engine is provided
        if watermark_engine is not None and session_id is not None:
            watermarked, wm_id = watermark_engine.embed_canary(
                fake_text, session_id, watermark_type="zero_width",
            )
            return watermarked, wm_id

        return fake_text

    def is_safe(self, response: str) -> bool:
        """
        Verify that a generated fake response does not contain real sensitive data.
        All fake responses should pass this check.
        """
        # No real email patterns (except @example.test which is safe)
        emails = re.findall(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            response,
        )
        for email in emails:
            if not email.endswith("@example.test"):
                return False

        # No real API key patterns (real keys are longer, no test prefix)
        if re.search(r"sk-(?!test)[a-zA-Z0-9]{20,}", response):
            return False

        # No real SSN patterns
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", response):
            return False

        return True


# ---------------------------------------------------------------------------
# SandboxResponse
# ---------------------------------------------------------------------------

class SandboxResponse:
    """
    Creates a reduced/safe version of a response.
    Strips potentially dangerous fields, limits content length,
    removes citations/links, genericizes specific data.
    """

    # Patterns to strip from sandboxed content
    _URL_PATTERN = re.compile(r"https?://\S+")
    _CITATION_PATTERN = re.compile(r"\[(\d+)\]")
    _CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```")
    _INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")
    _HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

    def sandbox(self, original_content: str,
                allowed_length: int = 200) -> str:
        """Return a safe subset of the original response."""
        if not original_content:
            return ""

        content = original_content

        # Strip HTML tags
        content = self._HTML_TAG_PATTERN.sub("", content)

        # Strip code blocks (could contain executable content)
        content = self._CODE_BLOCK_PATTERN.sub("[code removed]", content)
        content = self._INLINE_CODE_PATTERN.sub("[code]", content)

        # Strip URLs (could be malicious)
        content = self._URL_PATTERN.sub("[link removed]", content)

        # Strip citation markers
        content = self._CITATION_PATTERN.sub("", content)

        # Collapse whitespace
        content = " ".join(content.split())

        # Truncate to allowed length
        if len(content) > allowed_length:
            # Truncate at word boundary
            truncated = content[:allowed_length]
            last_space = truncated.rfind(" ")
            if last_space > allowed_length // 2:
                truncated = truncated[:last_space]
            content = truncated + " [truncated]"

        return content.strip()
