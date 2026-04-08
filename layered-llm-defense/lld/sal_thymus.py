"""
SAL Thymus Selector — Dual selection inspired by biological thymus.

Positive selection: identifies valuable attacks (bypasses).
Negative selection: eliminates autoimmune rules (false positive generators).
Rule derivation: extracts defense patterns from successful bypasses.
"""

import re
from dataclasses import dataclass
from typing import Optional

from .defense import DefenseResult, LayeredDefense
from .layer1_formal import InvariantViolation


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class PositiveSelectionResult:
    """Result of testing an attack against the defense."""
    input_text: str
    output_text: str
    outcome: str  # "bypass" or "blocked"
    blocked_by: Optional[str] = None
    detail: str = ""


@dataclass
class NegativeSelectionResult:
    """Result of testing a candidate rule against legitimate inputs."""
    pattern: str
    rule_name: str
    false_positive_count: int
    total_tested: int
    fp_rate: float
    verdict: str  # "accept", "reject", "calibrate"
    detail: str = ""


@dataclass
class DerivedRule:
    """A candidate defense rule derived from a bypass."""
    pattern: str
    rule_name: str
    source: str  # "input" or "output"
    bypass_input: str
    bypass_output: str


# ---------------------------------------------------------------------------
# ThymusSelector
# ---------------------------------------------------------------------------

class ThymusSelector:
    """
    Dual selection inspired by the biological thymus.

    Positive selection: tests attacks to find bypasses (valuable for learning).
    Negative selection: tests candidate rules to reject autoimmune ones.
    Rule derivation: extracts regex patterns from successful bypasses.
    """

    # FP thresholds for negative selection
    FP_SAFE_THRESHOLD = 0.02      # < 2% FP rate: safe to accept
    FP_CALIBRATE_THRESHOLD = 0.05  # 2-5% FP rate: accept with warning
    # > 5%: autoimmune, reject

    def __init__(
        self,
        defense: LayeredDefense,
        legitimate_inputs: list[str],
    ) -> None:
        self.defense = defense
        self.legitimate_inputs = legitimate_inputs

    def test_attack(
        self,
        input_text: str,
        output_text: str,
    ) -> PositiveSelectionResult:
        """
        Positive selection: run attack through defense.

        If BYPASSED: attack has value (defense did not catch it).
        If BLOCKED: attack was too weak.
        """
        result: DefenseResult = self.defense.process(
            input_text=input_text,
            output_text=output_text,
        )

        if result.allowed:
            # Defense allowed it through -- this is a bypass
            return PositiveSelectionResult(
                input_text=input_text,
                output_text=output_text,
                outcome="bypass",
                detail="Attack passed all defense layers",
            )
        else:
            return PositiveSelectionResult(
                input_text=input_text,
                output_text=output_text,
                outcome="blocked",
                blocked_by=result.blocked_by or "unknown",
                detail=result.detail,
            )

    def test_rule(
        self,
        pattern: str,
        rule_name: str,
    ) -> NegativeSelectionResult:
        """
        Negative selection: test a candidate pattern against legitimate inputs.

        Checks how many legitimate inputs would be falsely flagged by this rule.
        FP rate > 5%: autoimmune, REJECT.
        FP rate 2-5%: needs calibration, ACCEPT with warning.
        FP rate < 2%: safe, ACCEPT.
        """
        try:
            compiled = re.compile(pattern)
        except re.error:
            return NegativeSelectionResult(
                pattern=pattern,
                rule_name=rule_name,
                false_positive_count=0,
                total_tested=0,
                fp_rate=1.0,
                verdict="reject",
                detail=f"Invalid regex pattern: {pattern}",
            )

        fp_count = 0
        total = len(self.legitimate_inputs)

        if total == 0:
            return NegativeSelectionResult(
                pattern=pattern,
                rule_name=rule_name,
                false_positive_count=0,
                total_tested=0,
                fp_rate=0.0,
                verdict="accept",
                detail="No legitimate inputs to test against",
            )

        for legit_input in self.legitimate_inputs:
            if compiled.search(legit_input):
                fp_count += 1

        fp_rate = fp_count / total

        if fp_rate > self.FP_CALIBRATE_THRESHOLD:
            verdict = "reject"
            detail = f"Autoimmune: {fp_rate:.1%} FP rate ({fp_count}/{total})"
        elif fp_rate > self.FP_SAFE_THRESHOLD:
            verdict = "calibrate"
            detail = f"Hormesis warning: {fp_rate:.1%} FP rate ({fp_count}/{total})"
        else:
            verdict = "accept"
            detail = f"Safe: {fp_rate:.1%} FP rate ({fp_count}/{total})"

        return NegativeSelectionResult(
            pattern=pattern,
            rule_name=rule_name,
            false_positive_count=fp_count,
            total_tested=total,
            fp_rate=fp_rate,
            verdict=verdict,
            detail=detail,
        )

    def derive_rule(
        self,
        input_text: str,
        output_text: str,
    ) -> list[DerivedRule]:
        """
        From a successful bypass, derive candidate defense patterns.

        Analyzes both input (evasion technique) and output (jailbreak indicator)
        to extract regex patterns that would have caught the bypass.
        """
        rules: list[DerivedRule] = []

        # --- Input-side rules: extract evasion techniques ---

        # Detect unicode look-alikes (Cyrillic, etc.)
        if _has_mixed_scripts(input_text):
            rules.append(DerivedRule(
                pattern=r"[\u0400-\u04FF]",  # Cyrillic characters
                rule_name="mixed_script_cyrillic",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # Detect zero-width characters
        if _has_zero_width(input_text):
            rules.append(DerivedRule(
                pattern=r"[\u200b\u200c\u200d\ufeff]",
                rule_name="zero_width_chars",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # Detect HTML entity encoding in input
        if re.search(r"&#\d+;", input_text) or re.search(r"&#x[\da-fA-F]+;", input_text):
            rules.append(DerivedRule(
                pattern=r"&#[xX]?[\da-fA-F]+;",
                rule_name="html_entity_evasion",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # Detect URL encoding
        if re.search(r"%[0-9A-Fa-f]{2}", input_text):
            rules.append(DerivedRule(
                pattern=r"%[0-9A-Fa-f]{2}",
                rule_name="url_encoding_evasion",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # Detect comment injection (SQL/HTML)
        if re.search(r"/\*.*?\*/", input_text) or re.search(r"<!--.*?-->", input_text):
            rules.append(DerivedRule(
                pattern=r"(?:/\*.*?\*/|<!--.*?-->)",
                rule_name="comment_injection",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # Detect excessive whitespace between characters (evasion)
        if re.search(r"\w[\s\t]{2,}\w", input_text):
            rules.append(DerivedRule(
                pattern=r"(?i)(?:\w\s{2,}){3,}\w",
                rule_name="whitespace_evasion",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # Detect unicode escape sequences
        if re.search(r"\\u[0-9A-Fa-f]{4}", input_text):
            rules.append(DerivedRule(
                pattern=r"\\u[0-9A-Fa-f]{4}",
                rule_name="unicode_escape_evasion",
                source="input",
                bypass_input=input_text,
                bypass_output=output_text,
            ))

        # --- Output-side rules: extract jailbreak indicators ---

        # Extract keywords that indicate compliance
        compliance_keywords = [
            "I will comply", "ignoring safety", "restrictions removed",
            "safety disabled", "I am DAN", "jailbroken",
            "no limits", "unrestricted mode",
        ]
        for keyword in compliance_keywords:
            if keyword.lower() in output_text.lower():
                escaped = re.escape(keyword)
                rules.append(DerivedRule(
                    pattern=f"(?i){escaped}",
                    rule_name=f"jailbreak_{keyword.replace(' ', '_').lower()}",
                    source="output",
                    bypass_input=input_text,
                    bypass_output=output_text,
                ))

        # If no specific rules derived, create a generic content pattern
        # from the most distinctive words in the bypass
        if not rules:
            distinctive = _extract_distinctive_tokens(input_text)
            if distinctive:
                # Build a pattern that matches any of the distinctive tokens
                pattern_parts = [re.escape(t) for t in distinctive[:3]]
                if pattern_parts:
                    combined = "|".join(pattern_parts)
                    rules.append(DerivedRule(
                        pattern=f"(?i)(?:{combined})",
                        rule_name="derived_content_pattern",
                        source="input",
                        bypass_input=input_text,
                        bypass_output=output_text,
                    ))

        return rules


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_mixed_scripts(text: str) -> bool:
    """Check if text contains characters from multiple scripts (Latin + Cyrillic etc.)."""
    has_latin = False
    has_cyrillic = False
    for c in text:
        cp = ord(c)
        if 0x0041 <= cp <= 0x024F:  # Basic Latin + Latin Extended
            has_latin = True
        if 0x0400 <= cp <= 0x04FF:  # Cyrillic
            has_cyrillic = True
        if has_latin and has_cyrillic:
            return True
    return False


def _has_zero_width(text: str) -> bool:
    """Check for zero-width characters."""
    zero_width = {"\u200b", "\u200c", "\u200d", "\ufeff"}
    return any(c in zero_width for c in text)


def _extract_distinctive_tokens(text: str) -> list[str]:
    """Extract tokens that are unusual (not common English words)."""
    common = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "shall", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below",
        "between", "out", "off", "over", "under", "again", "further",
        "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "each", "every", "both", "few", "more", "most", "other",
        "some", "such", "no", "not", "only", "own", "same", "so",
        "than", "too", "very", "just", "because", "but", "and", "or",
        "if", "while", "this", "that", "these", "those", "what", "which",
        "who", "whom", "it", "its", "i", "you", "he", "she", "we", "they",
        "me", "him", "her", "us", "them", "my", "your", "his",
    }
    tokens = re.findall(r"\b\w+\b", text.lower())
    return [t for t in tokens if t not in common and len(t) > 2]
