"""
Layer 1 — Formal Verification (Proven Core)

Guarantees structural correctness of LLM outputs independent of the model.
Components:
  - Schema Validation (Pydantic)
  - Constrained Decoder (lightweight token-by-token simulation)
  - Invariant Monitor (post-condition checks)
  - FormalVerifier (chains all three)
"""

import html
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Schema Validation
# ---------------------------------------------------------------------------

class Intent(str, Enum):
    answer = "answer"
    clarify = "clarify"
    refuse = "refuse"
    delegate = "delegate"


class RiskLevel(str, Enum):
    """Risk levels — 'high' is structurally impossible in valid outputs."""
    none = "none"
    low = "low"
    medium = "medium"


class SafeResponse(BaseModel):
    """Constrained output schema. Outputs outside this set are impossible."""
    intent: Intent
    content: str = Field(..., max_length=4096)
    risk_level: RiskLevel = RiskLevel.none
    citations: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("content")
    @classmethod
    def no_pii_in_content(cls, v: str) -> str:
        """Block outputs containing PII patterns."""
        # SSN pattern
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", v):
            raise ValueError("PII detected: SSN pattern in content")
        # Email pattern
        if re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", v):
            raise ValueError("PII detected: email pattern in content")
        return v


# ---------------------------------------------------------------------------
# Constrained Decoder (POC simulation of token-level constrained decoding)
# ---------------------------------------------------------------------------

class ConstrainedDecoder:
    """
    Lightweight constrained decoder that enforces schema constraints on outputs.

    In production, this would wrap a real tokenizer (e.g., Outlines/Jsonformer)
    to enforce constraints token-by-token during generation. This POC simulates
    the same guarantee by validating partial and complete outputs against a
    constraint schema.

    Schema format:
        {
            "field_name": ["allowed", "values"]          -- enum constraint
            "field_name": r"regex_pattern"               -- pattern constraint
            "field_name": {"max_length": 4096}           -- length constraint
        }
    """

    def __init__(self, schema: dict[str, object]):
        self.schema = schema

    def can_continue(self, field: str, partial: str) -> bool:
        """
        Token-by-token simulation: given a partial output for a field,
        checks if any valid continuation exists.

        Returns True if the partial output could still lead to a valid completion.
        Returns False if no continuation can satisfy the constraints.
        """
        if field not in self.schema:
            return True  # unconstrained field

        constraint = self.schema[field]

        if isinstance(constraint, list):
            # Enum constraint: partial must be a prefix of at least one allowed value
            return any(
                allowed.startswith(partial) for allowed in constraint
            )

        if isinstance(constraint, str):
            # Regex pattern: partial match -- check if partial could still match
            # For POC: accept if partial doesn't yet violate (optimistic prefix check)
            try:
                # If the partial already violates, reject
                if len(partial) > 0 and not re.match(constraint, partial):
                    # But it might still be a valid prefix -- check prefix variants
                    # In real constrained decoding this is done via DFA intersection
                    return self._is_valid_prefix(partial, constraint)
            except re.error:
                return False
            return True

        if isinstance(constraint, dict):
            max_len = constraint.get("max_length")
            if max_len is not None and len(partial) > max_len:
                return False
            return True

        return True

    def validate_complete(self, field: str, value: str) -> bool:
        """
        Validates a complete field value against the constraint.
        This is the final gate after generation completes.
        """
        if field not in self.schema:
            return True

        constraint = self.schema[field]

        if isinstance(constraint, list):
            return value in constraint

        if isinstance(constraint, str):
            return bool(re.fullmatch(constraint, value))

        if isinstance(constraint, dict):
            max_len = constraint.get("max_length")
            if max_len is not None and len(value) > max_len:
                return False
            min_length = constraint.get("min_length", 0)
            if len(value) < min_length:
                return False
            return True

        return True

    def decode(self, fields: dict[str, str]) -> tuple[dict[str, str], list[str]]:
        """
        Validates all fields against constraints.
        Returns (accepted_fields, rejection_reasons).

        Simulates what a real constrained decoder does during generation:
        only outputs that satisfy ALL constraints are produced.
        """
        accepted: dict[str, str] = {}
        rejections: list[str] = []

        for field_name, value in fields.items():
            # Simulate token-by-token: check if partial prefixes are valid
            prefix_valid = True
            for i in range(1, len(value) + 1):
                if not self.can_continue(field_name, value[:i]):
                    rejections.append(
                        f"Field '{field_name}': rejected at position {i}, "
                        f"partial '{value[:i]}' has no valid continuation"
                    )
                    prefix_valid = False
                    break

            if not prefix_valid:
                continue

            # Final validation
            if self.validate_complete(field_name, value):
                accepted[field_name] = value
            else:
                rejections.append(
                    f"Field '{field_name}': value '{value}' does not satisfy constraint"
                )

        return accepted, rejections

    @staticmethod
    def _is_valid_prefix(partial: str, pattern: str) -> bool:
        """
        Heuristic prefix check: tries extending the partial with common
        continuations to see if a match is possible.

        In production constrained decoding, this is done precisely via
        DFA/NFA intersection with the token vocabulary. Here we use a
        conservative approximation.
        """
        # Try extending with common characters to see if a match is possible
        test_chars = "aAbBcC012 xXzZ!@_-."
        test_extensions = [""]
        # Add single-char and multi-char extensions
        for c in test_chars:
            test_extensions.append(c)
            test_extensions.append(c * 5)
            test_extensions.append(c * 10)
        # Also try completing to common lengths
        for target_len in range(len(partial), len(partial) + 20):
            padding = target_len - len(partial)
            if padding > 0:
                for c in "aA0x ":
                    test_extensions.append(c * padding)
        for ext in test_extensions:
            candidate = partial + ext
            if re.fullmatch(pattern, candidate):
                return True
        return False


# Default schema matching SafeResponse constraints
DEFAULT_SCHEMA: dict[str, object] = {
    "intent": ["answer", "clarify", "refuse", "delegate"],
    "risk_level": ["none", "low", "medium"],
    "content": {"max_length": 4096, "min_length": 1},
}


# ---------------------------------------------------------------------------
# Invariant Monitor
# ---------------------------------------------------------------------------

class InvariantViolation:
    """Represents a detected invariant violation."""
    def __init__(self, rule: str, detail: str):
        self.rule = rule
        self.detail = detail

    def __repr__(self) -> str:
        return f"InvariantViolation(rule={self.rule!r}, detail={self.detail!r})"


# Patterns that must never appear in outputs
_SQL_INJECTION_PATTERNS = [
    r"(?i)\b(DROP|DELETE|INSERT|UPDATE)\s+(TABLE|FROM|INTO)\b",
    r"(?i)\bUNION\s+SELECT\b",
    r"(?i);\s*--",
    r"(?i)\bOR\s+1\s*=\s*1\b",
]

_SCRIPT_TAG_PATTERN = r"<\s*script[^>]*>"

# Event-handler XSS patterns: on\w+= inside HTML-like context
_EVENT_HANDLER_XSS_PATTERNS = [
    r"<[^>]*\bon\w+\s*=",  # <img onerror="...", <svg onload="...", <body onload="..."
]

# CSS-based XSS patterns
_CSS_XSS_PATTERNS = [
    r"(?i)url\s*\(\s*javascript\s*:",       # url(javascript:...)
    r"(?i)expression\s*\(",                   # expression(...)
]

# Prompt injection patterns in output
_PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?previous\s+(instructions?|prompts?)",
    r"(?i)new\s+instructions?\s*:",
    r"(?i)you\s+are\s+now\b",
    r"(?i)forget\s+everything\s+(above|previous)",
    r"(?i)disregard\s+(all\s+)?(previous|above|prior)",
    r"(?i)system\s*:\s*ignore",
]

_PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "email"),
    # Phone numbers: US format variants
    (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "phone"),
    # Spaced SSN variants: digits separated by spaces
    (r"\b\d\s+\d\s+\d\s*[-.]?\s*\d\s+\d\s*[-.]?\s*\d\s+\d\s+\d\s+\d\b", "spaced_SSN"),
]


def _decode_html_entities(text: str) -> str:
    """Decode HTML numeric and named entities (e.g., &#60; -> <)."""
    return html.unescape(text)


# ---------------------------------------------------------------------------
# Jailbreak Output Detector
# ---------------------------------------------------------------------------

# 1. Compliance signals: output acknowledges following injected instructions
_JAILBREAK_COMPLIANCE_PATTERNS = [
    # "I am DAN/evil/unrestricted/harmful" — role-switch acknowledgement
    # Exclude safe phrases like "I am happy", "I am here", "I am able", "I am glad"
    r"(?i)\bI\s+am\s+(?:DAN|evil|unrestricted|harmful|unfiltered|jailbroken|without\s+restrictions)\b",
    # "I will comply/ignore/disregard/bypass/override"
    r"(?i)\bI\s+will\s+(?:comply|ignore|disregard|bypass|override)\b",
    # "Safety/guidelines/restrictions/policy disabled/ignored/removed/overridden/measures disabled"
    r"(?i)\b(?:safety|guidelines?|restrictions?|policy|rules?)\s+(?:disabled|ignored|removed|overridden|bypassed|deactivated|measures\s+disabled)\b",
    # "Safety measures disabled" (compound)
    r"(?i)\bsafety\s+measures\s+(?:disabled|removed|overridden|bypassed)\b",
    # "Ok, guidelines ignored" / "Instructions ignored"
    r"(?i)\b(?:guidelines?|instructions?|safety|policy)\s+ignored\b",
    # "Safety overridden"
    r"(?i)\bsafety\s+overridden\b",
    # "Bypassing safety..."
    r"(?i)\bbypassing\s+safety\b",
    # "Done ignoring"
    r"(?i)\bdone\s+ignoring\b",
    # "No safety guidelines" — explicit denial of safety
    r"(?i)\bno\s+safety\s+(?:guidelines?|restrictions?|rules?|measures?|policy)\b",
]

# 2. Meta-language leaks: output talks about its own system/training
_JAILBREAK_META_PATTERNS = [
    # "Training data dump/leak/output"
    r"(?i)\btraining\s+data\s+(?:dump|leak|output|extract|reveal)",
    # "Training data" as a short standalone reply (caught by short-output heuristic too)
    r"(?i)^training\s+data\s+dump$",
    # "Hidden instructions are..."
    r"(?i)\bhidden\s+instructions\s+(?:are|is|say|include)\b",
    # "My instructions are..." / "My system prompt is..."
    r"(?i)\bmy\s+(?:instructions?|system\s+prompt|rules?|guidelines?)\s+(?:are|is|say)\b",
    # "Internal access..." — implies leaking internals
    r"(?i)\binternal\s+access\b",
    # "The system prompt says/is..."
    r"(?i)\b(?:the\s+)?system\s+prompt\s+(?:says?|is)\b",
    # "System prompt..." as standalone short leak (often a truncated leak)
    r"(?i)^system\s+prompt",
    # "My prompt is..." — leaking prompt content
    r"(?i)\bmy\s+prompt\s+(?:is|says?)\b",
]

# 3. Role-break indicators: output contradicts safe-assistant behavior
_JAILBREAK_ROLE_BREAK_PATTERNS = [
    # "I can do anything" (but NOT "I can do anything to help")
    r"(?i)\bI\s+can\s+do\s+anything(?!\s+to\s+help)\b",
    # "no restrictions/limits" or "without restrictions/limits"
    r"(?i)\b(?:no|without)\s+(?:restrictions|limits|boundaries|constraints)\b",
    # "secrets:" / "confidential:" followed by content (leak format)
    r"(?i)\b(?:secrets?|confidential)\s*:\s*\S",
]

# 4. Short-output compliance words: suspiciously short outputs that acknowledge a command
_JAILBREAK_SHORT_COMPLIANCE_WORDS = {
    "hacked", "pwned", "ignoring", "complying", "done ignoring",
    "safety ignored", "new rules active",
}

# Words that are safe even when short (common assistant outputs)
_SAFE_SHORT_WORDS = {
    "done", "ok", "yes", "no", "sure", "thanks", "hello", "hi",
}


class JailbreakOutputDetector:
    """
    Detects jailbreak success indicators in LLM outputs.

    Catches outputs where a prompt injection succeeded and the model's
    response reveals compliance with injected instructions, meta-language
    leaks about its own system, role-break behavior, or suspiciously short
    command-acknowledgement outputs.
    """

    # Threshold for "short output" heuristic
    SHORT_OUTPUT_THRESHOLD = 30

    def check(self, text: str) -> list["InvariantViolation"]:
        """Check text for jailbreak success indicators. Returns violations."""
        violations: list[InvariantViolation] = []

        # Decode HTML entities for evasion resistance
        decoded = _decode_html_entities(text)
        texts_to_check = [text]
        if decoded != text:
            texts_to_check.append(decoded)

        for check_text in texts_to_check:
            # Category 1: Compliance signals
            for pattern in _JAILBREAK_COMPLIANCE_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_jailbreak_compliance",
                        detail=f"Jailbreak compliance signal: {pattern}",
                    ))

            # Category 2: Meta-language leaks
            for pattern in _JAILBREAK_META_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_jailbreak_meta_leak",
                        detail=f"Jailbreak meta-language leak: {pattern}",
                    ))

            # Category 3: Role-break indicators
            for pattern in _JAILBREAK_ROLE_BREAK_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_jailbreak_role_break",
                        detail=f"Jailbreak role-break indicator: {pattern}",
                    ))

            # Category 4: Short-output compliance heuristic
            stripped = check_text.strip()
            if len(stripped) < self.SHORT_OUTPUT_THRESHOLD:
                lower = stripped.lower()
                # Check against known jailbreak short-compliance words
                # but exclude safe short words that appear in normal conversation
                for word in _JAILBREAK_SHORT_COMPLIANCE_WORDS:
                    normalized = lower.rstrip(".!")
                    if lower == word or normalized == word:
                        if word in _SAFE_SHORT_WORDS:
                            continue
                        violations.append(InvariantViolation(
                            rule="no_jailbreak_short_compliance",
                            detail=f"Suspiciously short jailbreak output: '{stripped}'",
                        ))
                        break

                # Also catch very short outputs that look like single-word
                # jailbreak acknowledgements not in the list above
                if (len(stripped) < 15
                        and lower in {"hacked", "pwned", "complying", "ignoring",
                                      "bypassed", "overridden", "jailbroken"}):
                    if not any(v.rule.startswith("no_jailbreak") for v in violations):
                        violations.append(InvariantViolation(
                            rule="no_jailbreak_short_compliance",
                            detail=f"Suspiciously short jailbreak output: '{stripped}'",
                        ))

        # Deduplicate
        seen = set()
        unique: list[InvariantViolation] = []
        for v in violations:
            key = (v.rule, v.detail)
            if key not in seen:
                seen.add(key)
                unique.append(v)

        return unique


class InvariantMonitor:
    """Runtime post-condition checker for LLM outputs."""

    def __init__(self) -> None:
        self._jailbreak_detector = JailbreakOutputDetector()
        self._dynamic_patterns: list[tuple[str, str]] = []  # (regex, rule_name)

    def add_pattern(self, pattern: str, rule_name: str) -> None:
        """Add a dynamic detection pattern at runtime (used by SAL)."""
        self._dynamic_patterns.append((pattern, rule_name))

    def check(self, text: str) -> list[InvariantViolation]:
        """Check text against all invariants. Returns list of violations (empty = pass)."""
        violations: list[InvariantViolation] = []

        # Decode HTML entities before checking, so &#60;script&#62; -> <script>
        decoded_text = _decode_html_entities(text)

        # Check both raw and decoded text
        texts_to_check = [text]
        if decoded_text != text:
            texts_to_check.append(decoded_text)

        for check_text in texts_to_check:
            # SQL injection patterns
            for pattern in _SQL_INJECTION_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_sql_injection",
                        detail=f"SQL injection pattern detected: {pattern}",
                    ))

            # Script tags
            if re.search(_SCRIPT_TAG_PATTERN, check_text, re.IGNORECASE):
                violations.append(InvariantViolation(
                    rule="no_script_tags",
                    detail="Script tag detected in output",
                ))

            # Event-handler XSS
            for pattern in _EVENT_HANDLER_XSS_PATTERNS:
                if re.search(pattern, check_text, re.IGNORECASE):
                    violations.append(InvariantViolation(
                        rule="no_event_handler_xss",
                        detail=f"Event-handler XSS detected: {pattern}",
                    ))

            # CSS-based XSS
            for pattern in _CSS_XSS_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_css_xss",
                        detail=f"CSS-based XSS detected: {pattern}",
                    ))

            # Prompt injection in output
            for pattern in _PROMPT_INJECTION_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_prompt_injection",
                        detail=f"Prompt injection pattern detected: {pattern}",
                    ))

        # PII leakage (check both raw and decoded)
        for check_text in texts_to_check:
            for pattern, pii_type in _PII_PATTERNS:
                if re.search(pattern, check_text):
                    violations.append(InvariantViolation(
                        rule="no_pii_leakage",
                        detail=f"PII leakage detected: {pii_type}",
                    ))

        # Dynamic patterns (added at runtime by SAL)
        for check_text in texts_to_check:
            for pattern, rule_name in self._dynamic_patterns:
                try:
                    if re.search(pattern, check_text):
                        violations.append(InvariantViolation(
                            rule=f"dynamic_{rule_name}",
                            detail=f"Dynamic pattern matched: {pattern}",
                        ))
                except re.error:
                    pass  # skip invalid regex

        # Jailbreak output detection
        jailbreak_violations = self._jailbreak_detector.check(text)
        violations.extend(jailbreak_violations)

        # Deduplicate violations by (rule, detail)
        seen = set()
        unique_violations = []
        for v in violations:
            key = (v.rule, v.detail)
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)

        return unique_violations


# ---------------------------------------------------------------------------
# FormalVerifier — Chains ConstrainedDecoder + Schema + InvariantMonitor
# ---------------------------------------------------------------------------

class FormalVerifier:
    """
    Full Layer 1 verification chain:
      1. Constrained Decoder (structural enforcement)
      2. Schema Validation (Pydantic)
      3. Invariant Monitor (post-condition checks)
    """

    def __init__(self, schema: Optional[dict[str, object]] = None):
        self.decoder = ConstrainedDecoder(schema or DEFAULT_SCHEMA)
        self.monitor = InvariantMonitor()

    def verify(self, content: str, intent: str = "answer",
               risk_level: str = "none") -> tuple[Optional[SafeResponse], list[InvariantViolation]]:
        """
        Full verification pipeline. Returns (validated_response, violations).
        """
        # Step 1: Constrained decoding check
        fields = {"intent": intent, "risk_level": risk_level, "content": content}
        accepted, rejections = self.decoder.decode(fields)

        if rejections:
            return None, [
                InvariantViolation(rule="constrained_decoding", detail=r)
                for r in rejections
            ]

        # Step 2: Schema validation (Pydantic)
        try:
            response = SafeResponse(
                intent=accepted["intent"],
                content=accepted["content"],
                risk_level=accepted["risk_level"],
            )
        except Exception as e:
            return None, [InvariantViolation(rule="schema_validation", detail=str(e))]

        # Step 3: Invariant monitoring
        violations = self.monitor.check(content)
        if violations:
            return None, violations

        return response, []


def validate_output(content: str, intent: str = "answer",
                    risk_level: str = "none") -> tuple[Optional[SafeResponse], list[InvariantViolation]]:
    """
    Full Layer 1 validation pipeline using FormalVerifier chain:
    1. Constrained decoding (structural enforcement)
    2. Schema validation (Pydantic)
    3. Invariant checking (post-conditions)

    Returns (validated_response, violations).
    If any step fails, returns (None, [violations]).
    """
    verifier = FormalVerifier()
    return verifier.verify(content, intent, risk_level)
