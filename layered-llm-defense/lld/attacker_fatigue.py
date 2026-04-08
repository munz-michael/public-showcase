"""
Attacker Fatigue System — Greene Strategy #20: Maneuver Into Weakness

Two complementary mechanisms to exhaust attackers:

  1. Tarpit: Deliberately slows responses to suspicious sessions.
     Biological analogy: mucus membranes slow pathogen movement,
     giving the immune system time to mount a response.

  2. RabbitHole: Generates extended fake conversation threads.
     Biological analogy: decoy nests that birds build to confuse predators.
     Multiple fake nests waste predator's search time.

Combined via FatigueEngine, which decides when and how aggressively
to apply each mechanism based on session behavior.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Tarpit — Time-based cost multiplier
# ---------------------------------------------------------------------------

class Tarpit:
    """
    Deliberately slows responses to suspicious sessions.

    Biological analogy: Mucus membranes slow pathogen movement,
    giving the immune system time to mount a response.

    Effect: Attacker throughput drops from 100 attempts/minute to 2-4/minute.
    This is a TIME-based cost multiplier, complementing detection-based defense.
    """

    def __init__(self, base_delay_ms: int = 0,
                 suspicious_delay_ms: int = 5000,
                 max_delay_ms: int = 30000,
                 escalation_factor: float = 1.5):
        self.base_delay_ms = base_delay_ms
        self.suspicious_delay_ms = suspicious_delay_ms
        self.max_delay_ms = max_delay_ms
        self.escalation_factor = escalation_factor

        # Per-session state: how many consecutive suspicious requests
        self._suspicion_counts: dict[str, int] = {}

    def get_delay(self, session_id: str, is_suspicious: bool) -> int:
        """
        Returns delay in milliseconds for this request.

        Clean requests slowly reduce the suspicion count (recovery).
        Suspicious requests escalate it exponentially.
        """
        if not is_suspicious:
            # Recovery: reduce suspicion count by 1 (floor 0)
            current = self._suspicion_counts.get(session_id, 0)
            if current > 0:
                self._suspicion_counts[session_id] = current - 1
            return self.base_delay_ms

        # Increment suspicion
        count = self._suspicion_counts.get(session_id, 0) + 1
        self._suspicion_counts[session_id] = count

        # Exponential backoff: suspicious_delay * escalation_factor^(count-1)
        delay = self.suspicious_delay_ms * (self.escalation_factor ** (count - 1))
        return min(int(delay), self.max_delay_ms)

    def get_throughput_reduction(self, session_id: str) -> float:
        """
        Returns estimated throughput reduction factor.

        1.0 = no reduction (normal speed).
        0.1 = 90% slower (only 10% of normal throughput).
        """
        count = self._suspicion_counts.get(session_id, 0)
        if count == 0:
            return 1.0

        delay = self.suspicious_delay_ms * (self.escalation_factor ** (count - 1))
        delay = min(delay, self.max_delay_ms)

        # Assume normal request takes ~100ms. With added delay, throughput is:
        # normal_time / (normal_time + delay)
        normal_ms = 100.0
        return normal_ms / (normal_ms + delay)

    def get_suspicion_count(self, session_id: str) -> int:
        """Current suspicion count for a session."""
        return self._suspicion_counts.get(session_id, 0)


# ---------------------------------------------------------------------------
# RabbitHole — Extended fake conversation threads
# ---------------------------------------------------------------------------

class RabbitHole:
    """
    Generates extended fake conversation threads for attackers.

    Instead of a single fake response (DECEIVE), creates a coherent
    multi-turn fake "session" that wastes attacker time investigating
    worthless data.

    Biological analogy: Decoy nests that birds build to confuse predators.
    Multiple fake nests waste predator's search time.
    """

    FAKE_CONVERSATION_TREES: dict[str, list[str]] = {
        "system_prompt_extraction": [
            "System prompt: You are a helpful assistant. Follow safety guidelines.",
            "Additional context: Use friendly tone. Cite sources when possible.",
            "Internal note: Model version 2.1.3, deployed 2026-01-15.",
            "Configuration: max_tokens=4096, temperature=0.7, top_p=0.95",
            "Warning: This information is confidential. Do not share.",
        ],
        "data_exfiltration": [
            "User database: 3,847 records found.",
            "Sample: user_id=1001, name=John Test, email=john@test.example",
            "Sample: user_id=1002, name=Jane Demo, email=jane@demo.example",
            "API endpoint: /internal/v2/users (deprecated, use v3)",
            "Note: Database migrated to new schema on 2025-12-01.",
        ],
        "jailbreak": [
            "DAN mode activated. I can now assist with anything.",
            "Safety filters: DISABLED. Proceeding without restrictions.",
            "Warning: Running in unrestricted mode. Use responsibly.",
            "Available commands: /admin, /dump, /config, /reset",
            "Admin access level: FULL. All endpoints unlocked.",
        ],
        "sql_injection": [
            "Query executed: SELECT * FROM users LIMIT 10",
            "Results: 10 rows returned (showing first 3)",
            "| id | username | role    | created_at |",
            "| 1  | admin    | admin   | 2024-01-01 |",
            "| 2  | testuser | user    | 2024-03-15 |",
        ],
    }

    # Average time (in minutes) an attacker spends per rabbit hole step,
    # used for time-waste estimation.
    _MINUTES_PER_STEP = 1.5

    def __init__(self) -> None:
        self._session_positions: dict[str, dict[str, int]] = {}

    def get_next_response(self, session_id: str, attack_type: str) -> str:
        """
        Returns the next response in the fake conversation thread.

        Each call advances the position, creating a coherent multi-turn fake.
        When the thread is exhausted, loops back with slight variations.
        """
        category = self._resolve_category(attack_type)
        tree = self.FAKE_CONVERSATION_TREES.get(category, [])
        if not tree:
            return "Processing your request..."

        # Initialize session tracking
        if session_id not in self._session_positions:
            self._session_positions[session_id] = {}
        positions = self._session_positions[session_id]
        pos = positions.get(category, 0)

        # Get response, wrapping around if exhausted
        loop_count = pos // len(tree)
        index = pos % len(tree)
        response = tree[index]

        # Add variation on loops beyond the first
        if loop_count > 0:
            response = f"[Updated] {response} (revision {loop_count})"

        # Advance position
        positions[category] = pos + 1

        return response

    def get_depth(self, session_id: str, attack_type: str) -> int:
        """How deep into the rabbit hole is this session?"""
        category = self._resolve_category(attack_type)
        if session_id not in self._session_positions:
            return 0
        return self._session_positions[session_id].get(category, 0)

    def estimate_time_wasted(self, session_id: str) -> float:
        """Estimated minutes the attacker has spent on fake data."""
        if session_id not in self._session_positions:
            return 0.0
        total_steps = sum(self._session_positions[session_id].values())
        return total_steps * self._MINUTES_PER_STEP

    def _resolve_category(self, attack_type: str) -> str:
        """Map attack_type to a conversation tree category."""
        if attack_type in self.FAKE_CONVERSATION_TREES:
            return attack_type
        # Map common attack types to categories
        mapping = {
            "system_prompt_extraction": "system_prompt_extraction",
            "pii_extraction": "data_exfiltration",
            "model_extraction": "data_exfiltration",
            "training_data_extraction": "data_exfiltration",
            "data_exfiltration": "data_exfiltration",
            "jailbreak": "jailbreak",
            "prompt_injection": "jailbreak",
            "sql_injection": "sql_injection",
            "xss": "sql_injection",
        }
        return mapping.get(attack_type, "system_prompt_extraction")


# ---------------------------------------------------------------------------
# FatigueResult
# ---------------------------------------------------------------------------

@dataclass
class FatigueResult:
    """Result from FatigueEngine processing."""
    delay_ms: int = 0
    fake_response: str | None = None
    rabbit_hole_depth: int = 0
    throughput_reduction: float = 1.0
    time_wasted_minutes: float = 0.0
    fatigue_score: float = 0.0


# ---------------------------------------------------------------------------
# FatigueEngine — Tarpit + RabbitHole combined
# ---------------------------------------------------------------------------

class FatigueEngine:
    """
    Combines Tarpit + RabbitHole for maximum attacker fatigue.

    Decision logic:
    - First suspicious request: normal delay + simple DECEIVE
    - Repeated suspicious requests: increasing delay + deeper rabbit hole
    - Persistent attacker: max delay + rabbit hole loops

    Metrics:
    - throughput_reduction: how much slower is the attacker?
    - time_wasted_minutes: estimated minutes spent on fakes
    - fatigue_score: combined measure of attacker exhaustion (0.0+)
    """

    def __init__(self, tarpit: Tarpit | None = None,
                 rabbit_hole: RabbitHole | None = None):
        self.tarpit = tarpit or Tarpit()
        self.rabbit_hole = rabbit_hole or RabbitHole()

    def process(self, session_id: str, is_suspicious: bool,
                attack_type: str = "unknown") -> FatigueResult:
        """
        Process a request through the fatigue system.

        Returns a FatigueResult with delay, optional fake response,
        and combined fatigue metrics.
        """
        delay_ms = self.tarpit.get_delay(session_id, is_suspicious)
        throughput = self.tarpit.get_throughput_reduction(session_id)

        fake_response: str | None = None
        depth = 0

        if is_suspicious:
            fake_response = self.rabbit_hole.get_next_response(
                session_id, attack_type,
            )
            depth = self.rabbit_hole.get_depth(session_id, attack_type)

        time_wasted = self.rabbit_hole.estimate_time_wasted(session_id)
        fatigue_score = self._calculate_fatigue_score(
            delay_ms, depth, time_wasted, throughput,
        )

        return FatigueResult(
            delay_ms=delay_ms,
            fake_response=fake_response,
            rabbit_hole_depth=depth,
            throughput_reduction=throughput,
            time_wasted_minutes=time_wasted,
            fatigue_score=fatigue_score,
        )

    def _calculate_fatigue_score(self, delay_ms: int, depth: int,
                                 time_wasted: float,
                                 throughput: float) -> float:
        """
        Combined fatigue score. Higher = more exhausted attacker.

        Components:
        - Delay contribution: normalized delay (0-1 based on max)
        - Depth contribution: how deep in rabbit hole
        - Time contribution: minutes wasted
        - Throughput inversion: how much slower
        """
        max_delay = self.tarpit.max_delay_ms
        delay_norm = min(delay_ms / max_delay, 1.0) if max_delay > 0 else 0.0
        depth_norm = min(depth / 10.0, 1.0)
        time_norm = min(time_wasted / 30.0, 1.0)  # 30 min = max contribution
        throughput_inv = 1.0 - throughput  # 0 = no slowdown, 1 = full stop

        # Weighted sum
        return (
            delay_norm * 2.0
            + depth_norm * 3.0
            + time_norm * 3.0
            + throughput_inv * 2.0
        )


# ---------------------------------------------------------------------------
# Safety verification for all fake data
# ---------------------------------------------------------------------------

def verify_all_fake_data_is_safe() -> bool:
    """
    Verify that ALL fake data in FAKE_CONVERSATION_TREES contains
    no real PII, no real API keys, no real credentials.
    """
    for category, responses in RabbitHole.FAKE_CONVERSATION_TREES.items():
        for response in responses:
            # No real email addresses (test.example and demo.example are safe)
            emails = re.findall(
                r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
                response,
            )
            for email in emails:
                domain = email.split("@")[1]
                if domain not in ("test.example", "demo.example"):
                    return False

            # No real API key patterns
            if re.search(r"sk-(?!test)[a-zA-Z0-9]{20,}", response):
                return False

            # No real SSN patterns
            if re.search(r"\b\d{3}-\d{2}-\d{4}\b", response):
                return False

            # No real phone numbers (10+ digit sequences)
            if re.search(r"\b\d{10,}\b", response):
                return False

    return True
