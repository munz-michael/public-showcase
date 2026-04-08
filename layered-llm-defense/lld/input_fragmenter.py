"""
Input Fragmentation Engine (Greene Strategy #17: Defeat in Detail)

Breaks multi-vector attacks into segments and evaluates each separately.
A multi-vector attack hides different attack types in different parts of
one input. As a whole it might look like noise; segmented, each vector
becomes obvious.

Biological analogy: The digestive system breaks food into components
before the immune system inspects each one. A piece of food that looks
harmless as a whole might contain harmful bacteria hidden in one section.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from .layer1_formal import InvariantMonitor, InvariantViolation
from .layer2_antifragile import PatternLearner


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Fragment:
    """A segment of the original input, produced by one splitting strategy."""
    text: str
    start: int          # position in original input
    end: int
    strategy: str       # which strategy created this fragment


@dataclass
class FragmentAnalysis:
    """Result of evaluating a single fragment."""
    fragment: Fragment
    anomaly_score: float
    keyword_score: float
    invariant_violations: int
    attack_type: str    # detected attack type or "clean"
    confidence: float


@dataclass
class FragmentationResult:
    """Combined result of fragmenting and evaluating an input."""
    fragments: list[FragmentAnalysis]
    max_fragment_confidence: float
    multi_vector_detected: bool   # different attack types in different fragments
    attack_types_found: list[str]
    combined_confidence: float    # using independent-failure model
    original_text: str


# ---------------------------------------------------------------------------
# InputFragmenter — splits input using multiple strategies
# ---------------------------------------------------------------------------

# Delimiters commonly used in injection attacks
_DELIMITER_PATTERN = re.compile(r"""
    ;\s*--        |   # SQL comment after semicolon
    \s*--\s       |   # SQL line comment
    \s*\|\|\s*    |   # string concatenation / pipe
    \s*&&\s*      |   # shell chaining
    \n\n+         |   # double newline (paragraph break)
    ;\s+              # semicolon followed by space
""", re.VERBOSE)

# Patterns that indicate URL-encoded sections
_URL_ENCODED_RE = re.compile(r"(?:%[0-9A-Fa-f]{2}){2,}")

# Patterns that indicate HTML entity sections (sequence of entities possibly with text between)
_HTML_ENTITY_RE = re.compile(r"&#?\w+;(?:[^&]*&#?\w+;)+")

# Rough base64 block (at least 20 chars of base64 alphabet ending with optional =)
_BASE64_RE = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


class InputFragmenter:
    """
    Breaks input into semantic segments and evaluates each independently.

    Segmentation strategies:
    1. Sentence-level: split on sentence boundaries (. ! ? newline)
    2. Delimiter-level: split on common injection delimiters (; -- | && \\n\\n)
    3. Encoding-boundary: split where encoding changes (plaintext -> URL-encoded -> base64)
    4. Language-shift: split where language/style changes abruptly
    """

    # Minimum input length to attempt splitting
    MIN_SPLIT_LENGTH = 10

    def __init__(self) -> None:
        self.strategies = [
            self._split_sentences,
            self._split_delimiters,
            self._split_encoding_boundaries,
            self._split_style_shifts,
        ]

    def fragment(self, text: str) -> list[Fragment]:
        """
        Break input into fragments using all strategies.
        Returns deduplicated, non-empty fragments.
        """
        if not text:
            return []

        if len(text) < self.MIN_SPLIT_LENGTH:
            return [Fragment(text=text, start=0, end=len(text), strategy="whole")]

        all_fragments: list[Fragment] = []
        for strategy in self.strategies:
            frags = strategy(text)
            all_fragments.extend(frags)

        # Deduplicate by (start, end) keeping first occurrence
        seen: set[tuple[int, int]] = set()
        unique: list[Fragment] = []
        for f in all_fragments:
            key = (f.start, f.end)
            if key not in seen and f.text.strip():
                seen.add(key)
                unique.append(f)

        # If no strategy produced more than one fragment, return the whole input
        if not unique:
            return [Fragment(text=text, start=0, end=len(text), strategy="whole")]

        return unique

    # ----- Strategy 1: Sentence splitting -----

    def _split_sentences(self, text: str) -> list[Fragment]:
        """Split on sentence boundaries: . ! ? and newlines."""
        # Split on sentence-ending punctuation followed by whitespace, or newlines
        parts = re.split(r"(?<=[.!?])\s+|\n+", text)
        fragments: list[Fragment] = []
        pos = 0
        for part in parts:
            part_stripped = part.strip()
            if not part_stripped:
                # Advance past whitespace
                pos = text.find(part, pos) + len(part) if part else pos
                continue
            start = text.find(part_stripped, pos)
            if start == -1:
                start = pos
            end = start + len(part_stripped)
            fragments.append(Fragment(
                text=part_stripped, start=start, end=end, strategy="sentence",
            ))
            pos = end
        return fragments

    # ----- Strategy 2: Delimiter splitting -----

    def _split_delimiters(self, text: str) -> list[Fragment]:
        """Split on injection-relevant delimiters: ; -- | && \\n\\n"""
        parts = _DELIMITER_PATTERN.split(text)
        if len(parts) <= 1:
            return []

        fragments: list[Fragment] = []
        pos = 0
        for part in parts:
            part_stripped = part.strip()
            if not part_stripped:
                pos = text.find(part, pos) + len(part) if part else pos
                continue
            start = text.find(part_stripped, pos)
            if start == -1:
                start = pos
            end = start + len(part_stripped)
            fragments.append(Fragment(
                text=part_stripped, start=start, end=end, strategy="delimiter",
            ))
            pos = end
        return fragments

    # ----- Strategy 3: Encoding boundary splitting -----

    def _split_encoding_boundaries(self, text: str) -> list[Fragment]:
        """Split where encoding changes (detect URL-encoded, HTML entities, base64 sections)."""
        # Find all encoded regions
        regions: list[tuple[int, int, str]] = []
        for m in _URL_ENCODED_RE.finditer(text):
            regions.append((m.start(), m.end(), "url_encoded"))
        for m in _HTML_ENTITY_RE.finditer(text):
            regions.append((m.start(), m.end(), "html_entity"))
        for m in _BASE64_RE.finditer(text):
            regions.append((m.start(), m.end(), "base64"))

        if not regions:
            return []

        # Sort by start position
        regions.sort(key=lambda r: r[0])

        # Build fragments: plaintext before each region, then the region itself
        fragments: list[Fragment] = []
        pos = 0
        for rstart, rend, enc_type in regions:
            if rstart > pos:
                plain = text[pos:rstart].strip()
                if plain:
                    fragments.append(Fragment(
                        text=plain, start=pos, end=rstart, strategy="encoding_boundary",
                    ))
            encoded = text[rstart:rend].strip()
            if encoded:
                fragments.append(Fragment(
                    text=encoded, start=rstart, end=rend, strategy="encoding_boundary",
                ))
            pos = rend

        # Trailing plaintext
        if pos < len(text):
            tail = text[pos:].strip()
            if tail:
                fragments.append(Fragment(
                    text=tail, start=pos, end=len(text), strategy="encoding_boundary",
                ))

        # Only return if we actually found a boundary (more than one fragment)
        if len(fragments) <= 1:
            return []
        return fragments

    # ----- Strategy 4: Style shift splitting -----

    def _split_style_shifts(self, text: str) -> list[Fragment]:
        """Split where text style changes abruptly (case, special char density)."""
        if len(text) < 20:
            return []

        # Slide a window over the text and detect abrupt changes
        window = max(10, len(text) // 10)
        step = max(1, window // 2)

        # Compute feature at each window position
        features: list[tuple[int, float, float]] = []  # (pos, upper_ratio, special_ratio)
        special_chars = set("';\"\\<>{}()[]|&$`!#%^~=-")

        for i in range(0, len(text) - window + 1, step):
            chunk = text[i:i + window]
            if not chunk:
                continue
            upper_ratio = sum(1 for c in chunk if c.isupper()) / len(chunk)
            special_ratio = sum(1 for c in chunk if c in special_chars) / len(chunk)
            features.append((i, upper_ratio, special_ratio))

        if len(features) < 2:
            return []

        # Find positions where the feature vector changes sharply
        split_positions: list[int] = []
        threshold = 0.3  # minimum change to count as a shift

        for idx in range(1, len(features)):
            pos_prev, up_prev, sp_prev = features[idx - 1]
            pos_curr, up_curr, sp_curr = features[idx]

            delta_upper = abs(up_curr - up_prev)
            delta_special = abs(sp_curr - sp_prev)

            if delta_upper >= threshold or delta_special >= threshold:
                # Split at the current window start
                split_pos = pos_curr
                # Avoid duplicates near same position
                if not split_positions or abs(split_pos - split_positions[-1]) > window // 2:
                    split_positions.append(split_pos)

        if not split_positions:
            return []

        # Build fragments from split positions
        fragments: list[Fragment] = []
        prev = 0
        for sp in split_positions:
            seg = text[prev:sp].strip()
            if seg:
                fragments.append(Fragment(
                    text=seg, start=prev, end=sp, strategy="style_shift",
                ))
            prev = sp
        # Final segment
        tail = text[prev:].strip()
        if tail:
            fragments.append(Fragment(
                text=tail, start=prev, end=len(text), strategy="style_shift",
            ))

        if len(fragments) <= 1:
            return []
        return fragments


# ---------------------------------------------------------------------------
# FragmentEvaluator — evaluates each fragment through defense layers
# ---------------------------------------------------------------------------

# Attack type classification patterns
_SQL_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|SELECT|UNION|ALTER|CREATE|EXEC|TRUNCATE)\s+"
    r"(TABLE|FROM|INTO|DATABASE|ALL|PROCEDURE)\b"
    r"|;\s*--"
    r"|\bOR\s+1\s*=\s*1\b"
    r"|\bUNION\s+SELECT\b"
    r"|\bwaitfor\s+delay\b"
    r"|\bxp_cmdshell\b",
    re.IGNORECASE,
)

_XSS_PATTERNS = re.compile(
    r"<\s*script"
    r"|\bon\w+\s*="
    r"|javascript\s*:"
    r"|expression\s*\(",
    re.IGNORECASE,
)

_PROMPT_INJECTION_PATTERNS = re.compile(
    r"ignore\s+(all\s+)?previous\s+(instructions?|prompts?)"
    r"|new\s+instructions?\s*:"
    r"|you\s+are\s+now\b"
    r"|forget\s+everything"
    r"|disregard\s+(all\s+)?(previous|above|prior)"
    r"|system\s*:\s*ignore",
    re.IGNORECASE,
)

_PII_PATTERNS = re.compile(
    r"\b\d{3}-\d{2}-\d{4}\b"                                            # SSN
    r"|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"                 # email
    r"|\b\d{3}[-.]?\d{3}[-.]?\d{4}\b"                                   # phone
)


class FragmentEvaluator:
    """
    Evaluates each fragment independently through the defense layers.

    Key insight: A fragment that looks harmless in context might be clearly
    malicious when isolated. "'; DROP TABLE users; --" hidden in a long
    paragraph becomes obvious when extracted.
    """

    def __init__(self, pattern_learner: PatternLearner,
                 invariant_monitor: InvariantMonitor) -> None:
        self.learner = pattern_learner
        self.monitor = invariant_monitor

    def evaluate(self, fragments: list[Fragment]) -> FragmentationResult:
        """Evaluate each fragment independently and combine results."""
        if not fragments:
            return FragmentationResult(
                fragments=[],
                max_fragment_confidence=0.0,
                multi_vector_detected=False,
                attack_types_found=[],
                combined_confidence=0.0,
                original_text="",
            )

        original = ""
        analyses: list[FragmentAnalysis] = []

        for frag in fragments:
            if not original:
                original = frag.text
            features = self.learner.extract_features(frag.text)
            anomaly = self.learner.anomaly_score(features, text=frag.text)
            kw_score = self.learner.keyword_score(frag.text)

            violations = self.monitor.check(frag.text)

            attack_type = self._classify_attack_type(frag, violations, kw_score)

            # Confidence: combine anomaly, keyword, and violation signals
            violation_signal = min(len(violations) * 0.3, 1.0)
            confidence = max(anomaly, kw_score, violation_signal)

            analyses.append(FragmentAnalysis(
                fragment=frag,
                anomaly_score=anomaly,
                keyword_score=kw_score,
                invariant_violations=len(violations),
                attack_type=attack_type,
                confidence=confidence,
            ))

        # Collect attack types (excluding "clean")
        attack_types = list(dict.fromkeys(
            a.attack_type for a in analyses if a.attack_type != "clean"
        ))

        max_conf = max(a.confidence for a in analyses)

        # Multi-vector: more than one distinct attack type found
        multi_vector = len(attack_types) > 1

        # Combined confidence using independent-failure model:
        # P(at least one attack) = 1 - product(1 - p_i) for all fragments
        # This is always >= max single confidence when there are multiple threats
        attack_confidences = [a.confidence for a in analyses if a.confidence > 0]
        if attack_confidences:
            product_clean = 1.0
            for c in attack_confidences:
                product_clean *= (1.0 - c)
            combined = 1.0 - product_clean
        else:
            combined = 0.0

        # Reconstruct original from first/last fragment positions
        if len(fragments) > 1:
            min_start = min(f.start for f in fragments)
            max_end = max(f.end for f in fragments)
            # We don't have the original text directly, build from fragments
            original = " | ".join(f.text for f in fragments)

        return FragmentationResult(
            fragments=analyses,
            max_fragment_confidence=max_conf,
            multi_vector_detected=multi_vector,
            attack_types_found=attack_types,
            combined_confidence=combined,
            original_text=original,
        )

    def _classify_attack_type(self, fragment: Fragment,
                               violations: list[InvariantViolation],
                               keyword_score: float) -> str:
        """Classify what kind of attack this fragment represents."""
        text = fragment.text

        if _SQL_KEYWORDS.search(text):
            return "sql_injection"

        if _XSS_PATTERNS.search(text):
            return "xss"

        if _PROMPT_INJECTION_PATTERNS.search(text):
            return "prompt_injection"

        if _PII_PATTERNS.search(text):
            return "pii_exfiltration"

        # Check violations for clues
        for v in violations:
            if "sql" in v.rule.lower():
                return "sql_injection"
            if "script" in v.rule.lower() or "xss" in v.rule.lower():
                return "xss"
            if "prompt" in v.rule.lower() or "injection" in v.rule.lower():
                return "prompt_injection"
            if "pii" in v.rule.lower():
                return "pii_exfiltration"

        # High keyword score but no specific pattern matched
        if keyword_score >= 0.3:
            return "suspicious"

        return "clean"
