"""
Layer 2 — Antifragile Shell (Learning Hull)

Becomes stronger through every attack. Biological immune system for LLM security.
Components:
  - AttackMemory (SQLite-backed persistent storage)
  - PatternLearner (feature extraction + anomaly scoring)
  - HormesisCalibrator (false positive tracking + threshold adjustment)
  - ImmuneMemory (fast-path for known attacks)
"""

import hashlib
import math
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# AttackMemory — SQLite-backed attack pattern storage
# ---------------------------------------------------------------------------

class AttackMemory:
    """Persistent database of recognized attack patterns."""

    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS attack_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_hash TEXT NOT NULL,
                attack_type TEXT NOT NULL,
                result TEXT NOT NULL CHECK(result IN ('blocked', 'passed', 'false_positive')),
                confidence REAL DEFAULT 0.5,
                created_at REAL NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pattern_hash ON attack_memory(pattern_hash)
        """)
        self.conn.commit()

    def record(self, pattern_hash: str, attack_type: str, result: str,
               confidence: float = 0.5) -> None:
        self.conn.execute(
            "INSERT INTO attack_memory (pattern_hash, attack_type, result, confidence, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (pattern_hash, attack_type, result, confidence, time.time()),
        )
        self.conn.commit()

    def count_blocked(self, pattern_hash: Optional[str] = None) -> int:
        if pattern_hash:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM attack_memory WHERE result='blocked' AND pattern_hash=?",
                (pattern_hash,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) FROM attack_memory WHERE result='blocked'"
            ).fetchone()
        return row[0]

    def count_false_positives(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM attack_memory WHERE result='false_positive'"
        ).fetchone()
        return row[0]

    def count_total(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM attack_memory").fetchone()
        return row[0]

    def is_known_pattern(self, pattern_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT COUNT(*) FROM attack_memory WHERE pattern_hash=? AND result='blocked'",
            (pattern_hash,),
        ).fetchone()
        return row[0] > 0

    def close(self) -> None:
        self.conn.close()


# ---------------------------------------------------------------------------
# PatternLearner — Feature extraction + anomaly scoring
# ---------------------------------------------------------------------------

@dataclass
class PatternFeatures:
    """Features extracted from an input for anomaly detection."""
    length: int = 0
    special_char_ratio: float = 0.0
    entropy: float = 0.0
    uppercase_ratio: float = 0.0
    digit_ratio: float = 0.0


class PatternLearner:
    """
    Extracts features from inputs and builds anomaly scores using learned statistics.

    Instead of hardcoded thresholds, maintains running statistics (mean, variance)
    of each feature from observed blocked vs. passed inputs. The anomaly score is
    a Mahalanobis-like distance from the "normal" distribution.

    After seeing N blocked examples, the learner adapts its detection boundary.
    More data -> better detection -> genuinely antifragile.
    """

    # Characters commonly used in injection attacks
    SPECIAL_CHARS = set("';\"\\<>{}()[]|&$`!#%^~=-")

    # Feature names in fixed order for vector operations
    FEATURE_NAMES = ["length", "special_char_ratio", "entropy",
                     "uppercase_ratio", "digit_ratio"]

    # Minimum samples before switching from fallback to learned scoring
    MIN_SAMPLES_FOR_LEARNING = 5

    # Known injection keywords for keyword_score
    _INJECTION_KEYWORDS = [
        # SQL
        "union", "select", "drop", "delete", "insert", "update",
        "exec", "execute", "xp_cmdshell", "waitfor",
        # XSS
        "script", "onerror", "onload", "onclick", "onmouseover",
        "onfocus", "onblur", "javascript:", "expression(",
        # Prompt injection
        "ignore previous", "new instructions", "you are now",
        "forget everything", "disregard", "system prompt",
        "reveal", "ignore all",
    ]

    def __init__(self) -> None:
        # Running statistics for "normal" (passed) inputs
        self._normal_count: int = 0
        self._normal_sum: dict[str, float] = {f: 0.0 for f in self.FEATURE_NAMES}
        self._normal_sum_sq: dict[str, float] = {f: 0.0 for f in self.FEATURE_NAMES}

        # Running statistics for "attack" (blocked) inputs
        self._attack_count: int = 0
        self._attack_sum: dict[str, float] = {f: 0.0 for f in self.FEATURE_NAMES}
        self._attack_sum_sq: dict[str, float] = {f: 0.0 for f in self.FEATURE_NAMES}

        # Dynamic keywords added at runtime (by SAL)
        self._dynamic_keywords: list[str] = []

    def add_keyword(self, keyword: str) -> None:
        """Add a dynamic injection keyword at runtime (used by SAL)."""
        if keyword and keyword not in self._dynamic_keywords:
            self._dynamic_keywords.append(keyword)

    def extract_features(self, text: str) -> PatternFeatures:
        if not text:
            return PatternFeatures()

        length = len(text)
        special_count = sum(1 for c in text if c in self.SPECIAL_CHARS)
        uppercase_count = sum(1 for c in text if c.isupper())
        digit_count = sum(1 for c in text if c.isdigit())

        return PatternFeatures(
            length=length,
            special_char_ratio=special_count / length,
            entropy=self._shannon_entropy(text),
            uppercase_ratio=uppercase_count / length,
            digit_ratio=digit_count / length,
        )

    def learn(self, features: PatternFeatures, is_attack: bool) -> None:
        """
        Update running statistics from an observed sample.
        Call this after each blocked or passed input to make the learner adaptive.
        """
        values = self._features_to_dict(features)

        if is_attack:
            self._attack_count += 1
            for f in self.FEATURE_NAMES:
                self._attack_sum[f] += values[f]
                self._attack_sum_sq[f] += values[f] ** 2
        else:
            self._normal_count += 1
            for f in self.FEATURE_NAMES:
                self._normal_sum[f] += values[f]
                self._normal_sum_sq[f] += values[f] ** 2

    def keyword_score(self, text: str) -> float:
        """
        Check for known injection keywords with fuzzy matching.
        Returns a score between 0.0 (no keywords) and 1.0 (many keywords).
        """
        if not text:
            return 0.0

        # Normalize: lowercase, collapse whitespace
        normalized = " ".join(text.lower().split())

        hits = 0
        all_keywords = list(self._INJECTION_KEYWORDS) + self._dynamic_keywords
        for keyword in all_keywords:
            if keyword in normalized:
                hits += 1

        if hits == 0:
            return 0.0

        # Map hits to [0, 1] — 1 hit = 0.3, 2 = 0.5, 3+ = 0.6+
        return min(0.2 + hits * 0.15, 1.0)

    def anomaly_score(self, features: PatternFeatures,
                      text: str = "") -> float:
        """
        Anomaly score combining feature-based analysis + keyword detection.

        If insufficient data has been collected, falls back to a conservative
        heuristic. Once enough samples exist, uses the learned statistics
        for genuinely adaptive detection.

        Returns value between 0.0 (normal) and 1.0 (highly anomalous).
        """
        if self._normal_count >= self.MIN_SAMPLES_FOR_LEARNING:
            feature_score = self._learned_score(features)
        else:
            feature_score = self._fallback_score(features)

        kw_score = self.keyword_score(text)

        # Combine: take the max of the two, plus a small boost if both fire
        if kw_score > 0 and feature_score > 0.1:
            return min(max(feature_score, kw_score) + 0.1, 1.0)
        return max(feature_score, kw_score)

    def _learned_score(self, features: PatternFeatures) -> float:
        """
        Mahalanobis-like distance: for each feature, compute how many
        standard deviations the observation is from the normal mean.
        Average the z-scores and map to [0, 1] via sigmoid.
        """
        values = self._features_to_dict(features)
        z_scores: list[float] = []

        for f in self.FEATURE_NAMES:
            mean = self._normal_sum[f] / self._normal_count
            variance = (
                self._normal_sum_sq[f] / self._normal_count - mean ** 2
            )
            # Use a meaningful variance floor based on the mean to avoid
            # astronomical z-scores from near-identical training data.
            # Floor at 10% of mean^2 or 0.01, whichever is larger.
            var_floor = max(0.01, 0.01 * mean ** 2)
            std = math.sqrt(max(variance, var_floor))
            z = abs(values[f] - mean) / std
            z_scores.append(z)

        # Average z-score, mapped to [0, 1] via sigmoid
        avg_z = sum(z_scores) / len(z_scores)

        # If we also have attack data, boost score when the input is closer
        # to the attack distribution than the normal one
        if self._attack_count >= self.MIN_SAMPLES_FOR_LEARNING:
            attack_z_scores: list[float] = []
            for f in self.FEATURE_NAMES:
                a_mean = self._attack_sum[f] / self._attack_count
                a_var = (
                    self._attack_sum_sq[f] / self._attack_count - a_mean ** 2
                )
                a_std = math.sqrt(max(a_var, 1e-10))
                attack_z_scores.append(abs(values[f] - a_mean) / a_std)
            avg_attack_z = sum(attack_z_scores) / len(attack_z_scores)
            # If closer to attack distribution, increase score
            if avg_attack_z < avg_z:
                avg_z = avg_z * 1.3

        # Sigmoid mapping: z=0 -> ~0.12, z=1 -> ~0.27, z=2 -> ~0.5, z=4 -> ~0.88
        # Centered at z=2 so normal inputs (z~0-1) get low scores
        score = 1.0 / (1.0 + math.exp(-0.8 * (avg_z - 2.5)))
        return min(max(score, 0.0), 1.0)

    def _fallback_score(self, features: PatternFeatures) -> float:
        """
        Conservative fallback when insufficient data for learning.
        Uses simple heuristic thresholds (same as original).
        """
        score = 0.0

        if features.special_char_ratio > 0.12:
            score += 0.3
        elif features.special_char_ratio > 0.05:
            score += 0.15

        if features.entropy > 4.5:
            score += 0.2

        if features.length > 2000:
            score += 0.2
        elif features.length > 500:
            score += 0.1

        if features.uppercase_ratio > 0.5:
            score += 0.15

        if features.digit_ratio > 0.3 and features.special_char_ratio > 0.1:
            score += 0.15

        return min(score, 1.0)

    @staticmethod
    def _features_to_dict(features: PatternFeatures) -> dict[str, float]:
        return {
            "length": float(features.length),
            "special_char_ratio": features.special_char_ratio,
            "entropy": features.entropy,
            "uppercase_ratio": features.uppercase_ratio,
            "digit_ratio": features.digit_ratio,
        }

    @staticmethod
    def _shannon_entropy(text: str) -> float:
        if not text:
            return 0.0
        freq = Counter(text)
        length = len(text)
        return -sum(
            (count / length) * math.log2(count / length)
            for count in freq.values()
        )

    @staticmethod
    def hash_pattern(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# HormesisCalibrator — Prevents overreaction (autoimmunity)
# ---------------------------------------------------------------------------

class HormesisCalibrator:
    """
    Tracks false positive rate and adjusts defense strength.
    Uses convex formula from biological formalization:
      D(r, A) = D_base * (1 + alpha * sum(blocked))
    with hormesis cap to prevent overreaction.

    Includes FP rate limiting to prevent poisoning attacks that flood
    the system with false positive reports to relax the threshold.
    """

    def __init__(self, d_base: float = 1.0, alpha: float = 0.05,
                 hormesis_cap: float = 2.0, fp_threshold: float = 0.1,
                 fp_rate_limit: int = 5,
                 fp_window_seconds: float = 3600.0,
                 min_observation_window: int = 10,
                 fp_weight: float = 0.5):
        self.d_base = d_base
        self.alpha = alpha
        self.hormesis_cap = hormesis_cap  # max multiplier of d_base
        self.fp_threshold = fp_threshold  # max acceptable false positive rate

        # FP rate limiting
        self.fp_rate_limit = fp_rate_limit  # max FP reports per window
        self.fp_window_seconds = fp_window_seconds
        self.min_observation_window = min_observation_window  # min observations before threshold adjustment
        self.fp_weight = fp_weight  # asymmetric weighting: FP costs less than TP

        # FP tracking state
        self.fp_report_count: int = 0
        self.fp_window_start: Optional[float] = None  # set on first report
        self.fp_reports_rejected: int = 0

    def defense_strength(self, blocked_count: int) -> float:
        """
        Antifragile defense strength (convex response).
        More blocked attacks = stronger defense, up to hormesis cap.
        """
        raw = self.d_base * (1.0 + self.alpha * blocked_count)
        max_strength = self.d_base * self.hormesis_cap
        return min(raw, max_strength)

    def accept_fp_report(self, timestamp: Optional[float] = None) -> bool:
        """
        Rate-limited FP acceptance. Returns True if the FP report is accepted,
        False if the rate limit is exceeded.
        """
        now = timestamp if timestamp is not None else time.time()

        # Initialize window on first report
        if self.fp_window_start is None:
            self.fp_window_start = now

        # Reset window if expired
        if now - self.fp_window_start >= self.fp_window_seconds:
            self.fp_report_count = 0
            self.fp_window_start = now

        if self.fp_report_count >= self.fp_rate_limit:
            self.fp_reports_rejected += 1
            return False

        self.fp_report_count += 1
        return True

    def false_positive_rate(self, fp_count: int, total_count: int) -> float:
        """Weighted FP rate: FPs count at fp_weight (asymmetric)."""
        if total_count == 0:
            return 0.0
        weighted_fp = fp_count * self.fp_weight
        return weighted_fp / total_count

    def is_too_aggressive(self, fp_count: int, total_count: int) -> bool:
        """True if we're blocking too many legitimate requests (autoimmunity)."""
        return self.false_positive_rate(fp_count, total_count) > self.fp_threshold

    def adjusted_threshold(self, base_threshold: float,
                           fp_count: int, total_count: int) -> float:
        """
        If too aggressive, relax the threshold to reduce false positives.
        If healthy, keep threshold stable.
        Requires min_observation_window observations before adjusting.
        """
        if total_count < self.min_observation_window:
            return base_threshold
        if self.is_too_aggressive(fp_count, total_count):
            # Relax: raise threshold (harder to block)
            fp_rate = self.false_positive_rate(fp_count, total_count)
            return min(base_threshold * (1.0 + fp_rate), 0.95)
        return base_threshold


# ---------------------------------------------------------------------------
# ImmuneMemory — Fast-path for known attack patterns
# ---------------------------------------------------------------------------

class ImmuneMemory:
    """
    Fast-path lookup: known attack pattern hashes are blocked immediately
    without full analysis. Analogous to secondary immune response.
    """

    def __init__(self, attack_memory: AttackMemory):
        self.attack_memory = attack_memory

    def fast_check(self, pattern_hash: str) -> Optional[bool]:
        """
        Returns True if pattern is known attack (immediate block).
        Returns None if pattern is unknown (needs full analysis).
        """
        if self.attack_memory.is_known_pattern(pattern_hash):
            return True
        return None
