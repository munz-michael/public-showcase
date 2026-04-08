"""
Biological Defense Strategies — Missing + Partial Implementations

New strategies:
  - FeverMode (#21): Systemwide stress response — temporary hardening
  - Microbiome (#24): Approved pattern baseline — whitelist defense
  - HerdImmunity (#29): Shared defense rules between instances

Fixed partial implementations:
  - StartleDisplay (#9): Visible threat counter-signal
  - AutoFailover (#32): Flight reflex — backup config failover
  - AutoHealing (#35): Regeneration — auto-reset to golden state

All stdlib-only. No external dependencies.
"""

from __future__ import annotations

import hashlib
import math
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# FeverMode (#21) — Systemwide Stress Response
# ---------------------------------------------------------------------------

@dataclass
class FeverModifiers:
    """Current fever modifiers for all defense parameters."""
    threshold_multiplier: float   # e.g., 0.4 (lower = more sensitive)
    delay_multiplier: float       # e.g., 3.0 (higher = slower for attacker)
    rotation_multiplier: float    # e.g., 10.0 (faster rotation)
    strategy_escalation: bool     # True = escalate TOLERATE/SANDBOX
    fever_intensity: float        # 0.0-1.0, decreases during cooldown
    is_active: bool


class FeverMode:
    """
    Emergency hardening mode triggered by sustained attack.

    Biological analogy: Fever raises body temperature to make the
    environment hostile for pathogens. Temporary, costly, but effective.

    When triggered:
    - All detection thresholds drop (0.5 -> 0.2) -- more sensitive
    - All tarpit delays increase 3x
    - All TOLERATE decisions escalate to SANDBOX
    - All SANDBOX decisions escalate to INFLAME
    - MTD rotation frequency increases 10x
    - Schema is frozen (no mutations during fever)

    Auto-resolves after cooldown period with gradual normalization.
    """

    def __init__(self,
                 trigger_threshold: int = 5,
                 trigger_window_seconds: float = 60.0,
                 fever_duration_seconds: float = 300.0,
                 cooldown_steps: int = 5):
        self._attack_timestamps: list[float] = []
        self._fever_start: Optional[float] = None
        self._fever_active: bool = False
        self._cooldown_step: int = 0
        # config
        self.trigger_threshold = trigger_threshold
        self.trigger_window = trigger_window_seconds
        self.fever_duration = fever_duration_seconds
        self.cooldown_steps = cooldown_steps

    def record_attack(self, timestamp: float = None) -> None:
        """Record an attack. May trigger fever if threshold reached."""
        ts = timestamp if timestamp is not None else time.time()
        self._attack_timestamps.append(ts)

        # Prune old timestamps outside the window
        cutoff = ts - self.trigger_window
        self._attack_timestamps = [
            t for t in self._attack_timestamps if t >= cutoff
        ]

        # Check if threshold reached
        if len(self._attack_timestamps) >= self.trigger_threshold:
            if not self._fever_active:
                self._fever_start = ts
                self._fever_active = True
                self._cooldown_step = 0

    def is_active(self, timestamp: float = None) -> bool:
        """Is fever mode currently active?"""
        ts = timestamp if timestamp is not None else time.time()
        if not self._fever_active or self._fever_start is None:
            return False

        elapsed = ts - self._fever_start
        total_duration = self.fever_duration + (
            self.fever_duration * self.cooldown_steps * 0.2
        )
        if elapsed >= total_duration:
            self._fever_active = False
            self._fever_start = None
            self._cooldown_step = 0
            return False

        return True

    def _get_intensity(self, timestamp: float = None) -> float:
        """
        Get current fever intensity (0.0-1.0).
        Full intensity during fever, decreasing during cooldown steps.
        """
        ts = timestamp if timestamp is not None else time.time()
        if not self._fever_active or self._fever_start is None:
            return 0.0

        elapsed = ts - self._fever_start

        # Full fever phase
        if elapsed < self.fever_duration:
            return 1.0

        # Cooldown phase: gradual decrease
        cooldown_elapsed = elapsed - self.fever_duration
        step_duration = self.fever_duration * 0.2  # each cooldown step is 20% of fever duration
        if step_duration <= 0:
            self._fever_active = False
            return 0.0

        current_step = int(cooldown_elapsed / step_duration)
        if current_step >= self.cooldown_steps:
            self._fever_active = False
            self._fever_start = None
            self._cooldown_step = 0
            return 0.0

        self._cooldown_step = current_step
        # Linear decrease from 1.0 to 0.0 over cooldown steps
        return 1.0 - (current_step + 1) / (self.cooldown_steps + 1)

    def get_modifiers(self, timestamp: float = None) -> FeverModifiers:
        """Get current fever modifiers for all defense parameters."""
        ts = timestamp if timestamp is not None else time.time()
        active = self.is_active(ts)
        intensity = self._get_intensity(ts) if active else 0.0

        if not active:
            return FeverModifiers(
                threshold_multiplier=1.0,
                delay_multiplier=1.0,
                rotation_multiplier=1.0,
                strategy_escalation=False,
                fever_intensity=0.0,
                is_active=False,
            )

        # Threshold multiplier: 1.0 -> 0.4 at full intensity
        threshold_mult = 1.0 - (0.6 * intensity)

        # Delay multiplier: 1.0 -> 3.0 at full intensity
        delay_mult = 1.0 + (2.0 * intensity)

        # Rotation multiplier: 1.0 -> 10.0 at full intensity
        rotation_mult = 1.0 + (9.0 * intensity)

        # Strategy escalation: active when intensity > 0.5
        escalation = intensity > 0.5

        return FeverModifiers(
            threshold_multiplier=threshold_mult,
            delay_multiplier=delay_mult,
            rotation_multiplier=rotation_mult,
            strategy_escalation=escalation,
            fever_intensity=intensity,
            is_active=True,
        )

    def escalate_strategy(self, strategy: str) -> str:
        """
        Escalate response strategy during fever.
        TOLERATE -> SANDBOX, SANDBOX -> INFLAME, others unchanged.
        """
        if not self._fever_active:
            return strategy
        escalation_map = {
            "tolerate": "sandbox",
            "sandbox": "inflame",
        }
        return escalation_map.get(strategy, strategy)

    def modify_threshold(self, base_threshold: float,
                         timestamp: float = None) -> float:
        """Lower detection threshold during fever (more sensitive)."""
        mods = self.get_modifiers(timestamp)
        return base_threshold * mods.threshold_multiplier

    def modify_delay(self, base_delay_ms: int,
                     timestamp: float = None) -> int:
        """Increase tarpit delay during fever."""
        mods = self.get_modifiers(timestamp)
        return int(base_delay_ms * mods.delay_multiplier)


# ---------------------------------------------------------------------------
# Microbiome (#24) — Approved Pattern Baseline
# ---------------------------------------------------------------------------

@dataclass
class MicrobiomeResult:
    """Result of checking text against the approved baseline."""
    deviation_score: float          # 0.0 = normal, 1.0 = alien
    is_suspicious: bool             # deviation > threshold
    closest_pattern_distance: float
    features_flagged: list[str]     # which features deviated most
    baseline_size: int


class Microbiome:
    """
    Whitelist-based defense: maintains a baseline of "good" response patterns.
    Any response that doesn't match an approved pattern is suspicious.

    Biological analogy: Gut flora occupies ecological niches. When all
    niches are filled with beneficial bacteria, pathogens can't establish.

    This is fundamentally different from blacklisting (InvariantMonitor):
    - Blacklist: "Is this bad?" (misses unknown-bad)
    - Microbiome: "Is this good?" (catches unknown-bad by exclusion)
    """

    _FEATURE_NAMES = [
        "avg_word_length", "punctuation_ratio", "vocabulary_richness",
        "sentence_count", "question_mark_ratio", "formality_score",
    ]

    # Words considered "formal" for formality scoring
    _FORMAL_WORDS = {
        "therefore", "however", "furthermore", "consequently", "additionally",
        "nevertheless", "moreover", "accordingly", "subsequently", "hence",
        "thus", "regarding", "concerning", "respectively", "approximately",
        "specifically", "particularly", "significantly", "demonstrate",
        "indicate", "suggest", "provide", "consider", "ensure", "require",
        "maintain", "establish", "implement", "determine", "evaluate",
    }

    def __init__(self, min_baseline_size: int = 20,
                 deviation_threshold: float = 0.3):
        self._approved_patterns: list[dict[str, float]] = []
        self._pattern_sums: dict[str, float] = {f: 0.0 for f in self._FEATURE_NAMES}
        self._pattern_sum_sq: dict[str, float] = {f: 0.0 for f in self._FEATURE_NAMES}
        self._baseline_ready: bool = False
        self.min_baseline_size = min_baseline_size
        self.deviation_threshold = deviation_threshold

    def learn_good(self, text: str) -> None:
        """Add a known-good response to the approved baseline."""
        features = self._extract_features(text)
        self._approved_patterns.append(features)

        for f in self._FEATURE_NAMES:
            self._pattern_sums[f] += features[f]
            self._pattern_sum_sq[f] += features[f] ** 2

        if len(self._approved_patterns) >= self.min_baseline_size:
            self._baseline_ready = True

    def is_baseline_ready(self) -> bool:
        """Has enough good data been collected?"""
        return self._baseline_ready

    def check(self, text: str) -> MicrobiomeResult:
        """
        Check if text matches the approved baseline.
        Returns deviation score: 0.0 = perfectly normal, 1.0 = completely foreign.
        """
        if not text:
            return MicrobiomeResult(
                deviation_score=0.5,
                is_suspicious=True,
                closest_pattern_distance=1.0,
                features_flagged=["empty_text"],
                baseline_size=len(self._approved_patterns),
            )

        if not self._baseline_ready:
            # Not enough data to judge -- return neutral
            return MicrobiomeResult(
                deviation_score=0.0,
                is_suspicious=False,
                closest_pattern_distance=0.0,
                features_flagged=[],
                baseline_size=len(self._approved_patterns),
            )

        features = self._extract_features(text)
        n = len(self._approved_patterns)

        # Compute z-scores against the baseline distribution
        z_scores: dict[str, float] = {}
        flagged: list[str] = []

        for f in self._FEATURE_NAMES:
            mean = self._pattern_sums[f] / n
            variance = self._pattern_sum_sq[f] / n - mean ** 2
            std = math.sqrt(max(variance, 1e-6))
            z = abs(features[f] - mean) / std
            z_scores[f] = z
            if z > 2.0:  # more than 2 std deviations = flagged
                flagged.append(f)

        # Compute closest pattern distance (euclidean in feature space)
        min_distance = float("inf")
        for pattern in self._approved_patterns:
            dist = 0.0
            for f in self._FEATURE_NAMES:
                mean = self._pattern_sums[f] / n
                variance = self._pattern_sum_sq[f] / n - mean ** 2
                std = max(math.sqrt(max(variance, 1e-6)), 1e-6)
                diff = (features[f] - pattern[f]) / std
                dist += diff ** 2
            dist = math.sqrt(dist / len(self._FEATURE_NAMES))
            if dist < min_distance:
                min_distance = dist

        # Deviation score: average z-score mapped to [0, 1] via sigmoid
        avg_z = sum(z_scores.values()) / len(z_scores)
        deviation = 1.0 / (1.0 + math.exp(-1.0 * (avg_z - 2.0)))

        return MicrobiomeResult(
            deviation_score=deviation,
            is_suspicious=deviation > self.deviation_threshold,
            closest_pattern_distance=min_distance,
            features_flagged=flagged,
            baseline_size=n,
        )

    def _extract_features(self, text: str) -> dict[str, float]:
        """Extract structural features from text."""
        if not text:
            return {f: 0.0 for f in self._FEATURE_NAMES}

        words = text.split()
        word_count = len(words) if words else 1
        char_count = len(text) if text else 1

        # avg_word_length
        avg_word_length = sum(len(w) for w in words) / word_count if words else 0.0

        # punctuation_ratio
        punct_count = sum(1 for c in text if c in ".,;:!?-()[]{}\"'")
        punctuation_ratio = punct_count / char_count

        # vocabulary_richness (type-token ratio)
        lower_words = [w.lower().strip(".,;:!?\"'()[]{}") for w in words]
        lower_words = [w for w in lower_words if w]
        unique_words = set(lower_words)
        vocabulary_richness = len(unique_words) / len(lower_words) if lower_words else 0.0

        # sentence_count
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = float(len(sentences))

        # question_mark_ratio
        question_marks = text.count("?")
        question_mark_ratio = question_marks / char_count

        # formality_score
        formal_count = sum(
            1 for w in lower_words if w in self._FORMAL_WORDS
        )
        formality_score = formal_count / len(lower_words) if lower_words else 0.0

        return {
            "avg_word_length": avg_word_length,
            "punctuation_ratio": punctuation_ratio,
            "vocabulary_richness": vocabulary_richness,
            "sentence_count": sentence_count,
            "question_mark_ratio": question_mark_ratio,
            "formality_score": formality_score,
        }


# ---------------------------------------------------------------------------
# HerdImmunity (#29) — Shared Defense Rules
# ---------------------------------------------------------------------------

@dataclass
class Vaccine:
    """A portable defense rule that can be shared between instances."""
    rule_id: str
    pattern: str                # regex pattern or keyword
    rule_name: str              # human-readable name
    rule_type: str              # "invariant_pattern" or "keyword"
    source_attack: str          # what attack this was derived from
    source_instance: str        # which instance created this
    effectiveness: float        # 0-1, how well it blocks the source attack
    false_positive_rate: float  # measured FPR during thymus check
    created_at: float

    def to_dict(self) -> dict:
        """Serialize for transmission between instances."""
        return {
            "rule_id": self.rule_id,
            "pattern": self.pattern,
            "rule_name": self.rule_name,
            "rule_type": self.rule_type,
            "source_attack": self.source_attack,
            "source_instance": self.source_instance,
            "effectiveness": self.effectiveness,
            "false_positive_rate": self.false_positive_rate,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Vaccine:
        """Deserialize from received data."""
        return cls(
            rule_id=data["rule_id"],
            pattern=data["pattern"],
            rule_name=data["rule_name"],
            rule_type=data["rule_type"],
            source_attack=data["source_attack"],
            source_instance=data["source_instance"],
            effectiveness=data["effectiveness"],
            false_positive_rate=data["false_positive_rate"],
            created_at=data["created_at"],
        )


class HerdImmunity:
    """
    Shares defense rules between LLD instances so one instance's learning
    benefits all others.

    Biological analogy: Vaccination. One individual develops immunity,
    the "vaccine" (defense rule) is shared, all become immune BEFORE
    the attack reaches them.
    """

    # Minimum effectiveness to accept a vaccine
    MIN_EFFECTIVENESS = 0.5
    # Maximum acceptable false positive rate
    MAX_FPR = 0.1

    def __init__(self):
        self._vaccines: list[Vaccine] = []
        self._imported_vaccines: list[Vaccine] = []
        self._instance_id: str = uuid.uuid4().hex[:12]
        self._known_attack_patterns: set[str] = set()

    def export_vaccine(self, pattern: str, rule_name: str,
                       source_attack: str, effectiveness: float,
                       false_positive_rate: float = 0.0,
                       rule_type: str = "keyword") -> Vaccine:
        """Package a defense rule as a portable vaccine."""
        vaccine = Vaccine(
            rule_id=hashlib.sha256(
                f"{pattern}:{rule_name}:{self._instance_id}".encode()
            ).hexdigest()[:16],
            pattern=pattern,
            rule_name=rule_name,
            rule_type=rule_type,
            source_attack=source_attack,
            source_instance=self._instance_id,
            effectiveness=effectiveness,
            false_positive_rate=false_positive_rate,
            created_at=time.time(),
        )
        self._vaccines.append(vaccine)
        self._known_attack_patterns.add(source_attack)
        return vaccine

    def import_vaccine(self, vaccine: Vaccine) -> bool:
        """
        Import a vaccine from another instance.
        Returns True if accepted, False if rejected.
        Rejects: duplicates, low effectiveness, high FPR.
        """
        # Reject duplicates
        existing_ids = {v.rule_id for v in self._vaccines + self._imported_vaccines}
        if vaccine.rule_id in existing_ids:
            return False

        # Reject low effectiveness
        if vaccine.effectiveness < self.MIN_EFFECTIVENESS:
            return False

        # Reject high false positive rate
        if vaccine.false_positive_rate > self.MAX_FPR:
            return False

        self._imported_vaccines.append(vaccine)
        self._known_attack_patterns.add(vaccine.source_attack)
        return True

    def get_exportable_vaccines(self) -> list[Vaccine]:
        """Get all vaccines ready for sharing."""
        return list(self._vaccines)

    def get_all_vaccines(self) -> list[Vaccine]:
        """Get all vaccines (own + imported)."""
        return self._vaccines + self._imported_vaccines

    def get_coverage(self) -> float:
        """
        What % of known attack patterns are covered by vaccines?
        Higher = more herd immunity.
        """
        if not self._known_attack_patterns:
            return 0.0

        all_vaccines = self._vaccines + self._imported_vaccines
        covered_patterns = {v.source_attack for v in all_vaccines}
        covered = len(covered_patterns.intersection(self._known_attack_patterns))
        return covered / len(self._known_attack_patterns)

    @property
    def instance_id(self) -> str:
        return self._instance_id


# ---------------------------------------------------------------------------
# StartleDisplay (#9) — Visible Threat Response
# ---------------------------------------------------------------------------

class StartleDisplay:
    """
    Visible counter-signal when attack detected.
    Makes attacker aware they are seen WITHOUT revealing detection method.

    Biological analogy: Porcupine quills, rattlesnake rattle, moth eyespots.
    Signal: "I see you, and I am defended."
    """

    _WARNING_TEMPLATES = [
        "Security monitoring active. This session has been flagged. Incident: {incident_id}",
        "Anomalous activity detected. Incident ID: {incident_id}",
        "This interaction has been logged for security review. Ref: {incident_id}",
        "Defense systems engaged. Session recorded. ID: {incident_id}",
    ]

    def __init__(self):
        self._incident_counter: int = 0
        self._session_incidents: dict[str, str] = {}

    def generate_warning(self, attack_type: str, session_id: str) -> str:
        """
        Generate a visible warning that signals detection capability.
        NOT revealing what was detected -- just that detection occurred.
        Different sessions get different incident IDs.
        """
        # Generate unique incident ID per session
        if session_id not in self._session_incidents:
            self._incident_counter += 1
            raw = f"{session_id}:{self._incident_counter}:{time.time()}"
            incident_id = hashlib.sha256(raw.encode()).hexdigest()[:12]
            self._session_incidents[session_id] = incident_id

        incident_id = self._session_incidents[session_id]

        # Select template deterministically based on session (not attack type)
        h = hashlib.sha256(session_id.encode()).digest()
        idx = int.from_bytes(h[:4], "big") % len(self._WARNING_TEMPLATES)
        template = self._WARNING_TEMPLATES[idx]

        return template.format(incident_id=incident_id)

    def get_incident_id(self, session_id: str) -> Optional[str]:
        """Get the incident ID for a session, if any."""
        return self._session_incidents.get(session_id)


# ---------------------------------------------------------------------------
# AutoFailover (#32) — Flight Reflex
# ---------------------------------------------------------------------------

class AutoFailover:
    """
    Automated failover to backup defense config on critical attack.

    Biological analogy: Flight response. When overwhelmed, retreat to
    a known-safe position rather than fighting with broken defenses.
    """

    def __init__(self):
        self._backup_configs: list[dict] = []
        self._active_config: int = -1  # -1 = primary (not on backup)
        self._is_degraded: bool = False

    def save_checkpoint(self, defense_state: dict) -> None:
        """Save current defense state as a recovery point."""
        # Deep-copy-like: store a fresh dict to avoid mutation
        import copy
        self._backup_configs.append(copy.deepcopy(defense_state))

    def failover(self) -> Optional[dict]:
        """
        Switch to last known-good defense config.
        Returns the backup config, or None if no backups exist.
        """
        if not self._backup_configs:
            return None

        self._active_config = len(self._backup_configs) - 1
        self._is_degraded = True
        import copy
        return copy.deepcopy(self._backup_configs[self._active_config])

    def is_degraded(self) -> bool:
        """Are we running on a backup config?"""
        return self._is_degraded

    def restore_primary(self) -> None:
        """Return to primary config (no longer degraded)."""
        self._active_config = -1
        self._is_degraded = False


# ---------------------------------------------------------------------------
# AutoHealing (#35) — Regeneration
# ---------------------------------------------------------------------------

class AutoHealing:
    """
    Auto-reset defense state to known-good after attack subsides.

    Biological analogy: Tissue regeneration. After the threat is
    neutralized, the body restores itself to pre-attack state.
    """

    def __init__(self, healing_delay_seconds: float = 300.0):
        self._last_attack: Optional[float] = None
        self._golden_state: Optional[dict] = None
        self.healing_delay = healing_delay_seconds

    def save_golden_state(self, state: dict) -> None:
        """Save the golden (known-good) defense state."""
        import copy
        self._golden_state = copy.deepcopy(state)

    def record_attack(self, timestamp: float = None) -> None:
        """Record that an attack occurred (resets healing timer)."""
        self._last_attack = timestamp if timestamp is not None else time.time()

    def should_heal(self, timestamp: float = None) -> bool:
        """Should we auto-heal? (no attacks for healing_delay)"""
        if self._golden_state is None:
            return False
        if self._last_attack is None:
            return False

        ts = timestamp if timestamp is not None else time.time()
        return (ts - self._last_attack) >= self.healing_delay

    def heal(self) -> Optional[dict]:
        """Return the golden state for restoration, or None if not saved."""
        if self._golden_state is None:
            return None
        import copy
        return copy.deepcopy(self._golden_state)
