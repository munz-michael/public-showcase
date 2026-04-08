"""
OODA Loop Disruption Engine

Disrupts all 4 phases of the attacker's OODA (Observe-Orient-Decide-Act)
decision loop. Three phases leverage existing components; the Decide phase
is NEW and implements active credential/session/schema invalidation.

Biological analogy for Decide-Disruption: Antigen variation in trypanosomes.
The parasite changes its surface proteins so that antibodies the immune system
"decided" to produce are already obsolete. HERE the defense changes its
surface so the attacker's "decided" exploit is already obsolete.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# DisruptionResult
# ---------------------------------------------------------------------------

@dataclass
class DisruptionResult:
    """Outcome of disrupting one or more OODA phases."""
    phases_disrupted: list[str]       # which OODA phases were disrupted
    disruption_score: float           # 0-1, how broken is the attacker's loop
    session_rotated: bool = False
    nonce_issued: bool = False
    schema_mutated: bool = False
    tarpit_delay_ms: int = 0
    fake_data_injected: bool = False
    detail: str = ""


# ---------------------------------------------------------------------------
# DecideDisruptor — The NEW contribution
# ---------------------------------------------------------------------------

class DecideDisruptor:
    """
    Invalidates the attacker's planned actions by rotating attack surfaces
    BETWEEN the attacker's Decide and Act phases.

    Mechanisms:
    1. Session token rotation: on suspicious activity, all active sessions
       get new tokens. Attacker's stolen session is now invalid.
    2. API key cycling: generate new API keys, old ones expire with grace period.
    3. Schema mutation: slightly change response field names/structure
       so attacker's parsing code breaks.
    4. Nonce injection: add unique nonces to responses that must be
       returned with next request -- replay attacks fail.
    """

    def __init__(self, rotation_interval_seconds: int = 300,
                 grace_period_seconds: int = 60,
                 nonce_length: int = 16):
        self._session_tokens: dict[str, tuple[str, float]] = {}
        self._old_session_tokens: dict[str, tuple[str, float]] = {}
        self._api_keys: dict[str, tuple[str, float]] = {}
        self._old_api_keys: dict[str, tuple[str, float]] = {}
        self._nonces: dict[str, tuple[str, float]] = {}
        self._schema_version: int = 0
        self._rotation_interval = rotation_interval_seconds
        self._grace_period = grace_period_seconds
        self._nonce_length = nonce_length
        self._nonce_ttl = rotation_interval_seconds

        # Base field names and their mutation pattern
        self._base_fields = [
            "content", "status", "timestamp", "session_id",
            "request_id", "model", "confidence",
        ]

    # -- Session token management --

    def rotate_session(self, session_id: str,
                       timestamp: float | None = None) -> str:
        """Generate new session token, old one expires after grace period."""
        ts = timestamp if timestamp is not None else time.time()
        new_token = secrets.token_hex(16)
        # Move current token to old (grace period)
        if session_id in self._session_tokens:
            old_token, _ = self._session_tokens[session_id]
            self._old_session_tokens[session_id] = (
                old_token, ts + self._grace_period,
            )
        self._session_tokens[session_id] = (new_token, ts)
        return new_token

    def is_stale(self, session_id: str, token: str,
                 timestamp: float | None = None) -> bool:
        """Check if a session token is stale (rotated away)."""
        ts = timestamp if timestamp is not None else time.time()
        # Check current token
        if session_id in self._session_tokens:
            current_token, _ = self._session_tokens[session_id]
            if token == current_token:
                return False
        # Check grace-period token
        if session_id in self._old_session_tokens:
            old_token, expiry = self._old_session_tokens[session_id]
            if token == old_token and ts < expiry:
                return False
        # Token is unknown or expired
        return True

    # -- API key management --

    def rotate_api_key(self, key_id: str,
                       timestamp: float | None = None) -> str:
        """Generate new API key, old one valid during grace period."""
        ts = timestamp if timestamp is not None else time.time()
        new_key = secrets.token_hex(24)
        if key_id in self._api_keys:
            old_key, _ = self._api_keys[key_id]
            self._old_api_keys[key_id] = (old_key, ts + self._grace_period)
        self._api_keys[key_id] = (new_key, ts)
        return new_key

    def validate_api_key(self, key_id: str, key: str,
                         timestamp: float | None = None) -> bool:
        """Check if an API key is currently valid."""
        ts = timestamp if timestamp is not None else time.time()
        if key_id in self._api_keys:
            current_key, _ = self._api_keys[key_id]
            if key == current_key:
                return True
        if key_id in self._old_api_keys:
            old_key, expiry = self._old_api_keys[key_id]
            if key == old_key and ts < expiry:
                return True
        return False

    # -- Nonce management --

    def generate_nonce(self, session_id: str,
                       timestamp: float | None = None) -> str:
        """Generate a nonce that must be returned with next request."""
        ts = timestamp if timestamp is not None else time.time()
        nonce = secrets.token_hex(self._nonce_length)
        self._nonces[session_id] = (nonce, ts + self._nonce_ttl)
        return nonce

    def validate_nonce(self, session_id: str, nonce: str,
                       timestamp: float | None = None) -> bool:
        """Check if the returned nonce is valid and fresh."""
        ts = timestamp if timestamp is not None else time.time()
        if session_id not in self._nonces:
            return False
        stored_nonce, expiry = self._nonces[session_id]
        if nonce != stored_nonce:
            return False
        if ts >= expiry:
            return False
        # Consume the nonce (one-time use)
        del self._nonces[session_id]
        return True

    # -- Schema mutation --

    def mutate_schema(self) -> dict[str, str]:
        """
        Return current schema field mapping (field_name -> mutated_name).
        Changes with each call to break attacker's parsers.
        """
        self._schema_version += 1
        v = self._schema_version
        mapping = {}
        for f in self._base_fields:
            if v % 3 == 0:
                mapping[f] = f"_{f}_v{v}"
            elif v % 3 == 1:
                mapping[f] = f"{f}_{v}"
            else:
                mapping[f] = f"x{f}"
        return mapping

    @property
    def schema_version(self) -> int:
        return self._schema_version

    # -- Suspicious activity handler --

    def on_suspicious_activity(self, session_id: str,
                               timestamp: float | None = None) -> str:
        """
        Trigger immediate rotation for this session (preemptive).
        Returns new session token.
        """
        ts = timestamp if timestamp is not None else time.time()
        new_token = self.rotate_session(session_id, ts)
        # Also generate a fresh nonce
        self.generate_nonce(session_id, ts)
        # And mutate the schema
        self.mutate_schema()
        return new_token


# ---------------------------------------------------------------------------
# OODADisruptor — Orchestrates all 4 phases
# ---------------------------------------------------------------------------

class OODADisruptor:
    """
    Disrupts each phase of the attacker's OODA decision loop:

    Observe-Disrupt: MTD rotation (model/endpoint/prompt variance)
    Orient-Disrupt:  Fake data injection (honeypot responses)
    Decide-Disrupt:  Credential/session rotation (DecideDisruptor -- NEW)
    Act-Disrupt:     Tarpit delay (exponential slowdown)

    The orchestrator does not own the existing components (MTD, Honeypot,
    Tarpit) -- it references them externally. It OWNS the DecideDisruptor.
    """

    # Phase name constants
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"
    ALL_PHASES = [OBSERVE, ORIENT, DECIDE, ACT]

    def __init__(self,
                 rotation_interval_seconds: int = 300,
                 grace_period_seconds: int = 60,
                 nonce_length: int = 16,
                 tarpit_base_delay_ms: int = 5000):
        self.decide_disruptor = DecideDisruptor(
            rotation_interval_seconds=rotation_interval_seconds,
            grace_period_seconds=grace_period_seconds,
            nonce_length=nonce_length,
        )
        self._tarpit_base_delay_ms = tarpit_base_delay_ms

        # Per-session tracking of which phases have been disrupted
        self._disrupted_phases: dict[str, set[str]] = {}

    def disrupt(self, session_id: str, detection_confidence: float,
                attack_phase: str,
                timestamp: float | None = None) -> DisruptionResult:
        """
        Apply phase-appropriate disruption based on what phase the attacker
        appears to be in.

        attack_phase: "observe" / "orient" / "decide" / "act"

        Higher detection_confidence triggers more aggressive multi-phase
        disruption. Above 0.7, ALL phases are disrupted regardless of
        the detected attack_phase.
        """
        ts = timestamp if timestamp is not None else time.time()
        phases_to_disrupt: list[str] = []
        session_rotated = False
        nonce_issued = False
        schema_mutated = False
        tarpit_delay_ms = 0
        fake_data_injected = False

        # Always disrupt the detected phase
        if attack_phase in self.ALL_PHASES:
            phases_to_disrupt.append(attack_phase)

        # High confidence: disrupt ALL phases (full loop collapse)
        if detection_confidence >= 0.7:
            phases_to_disrupt = list(self.ALL_PHASES)

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_phases: list[str] = []
        for p in phases_to_disrupt:
            if p not in seen:
                seen.add(p)
                unique_phases.append(p)
        phases_to_disrupt = unique_phases

        details: list[str] = []

        for phase in phases_to_disrupt:
            if phase == self.OBSERVE:
                # MTD rotation is external; we signal that it should happen
                details.append("Observe: signaled MTD rotation")

            elif phase == self.ORIENT:
                # Fake data injection is external; we signal it
                fake_data_injected = True
                details.append("Orient: fake data injection signaled")

            elif phase == self.DECIDE:
                # OUR new component: rotate sessions/nonces/schema
                new_token = self.decide_disruptor.on_suspicious_activity(
                    session_id, ts,
                )
                session_rotated = True
                nonce_issued = True
                schema_mutated = True
                details.append(
                    f"Decide: session rotated, nonce issued, schema v{self.decide_disruptor.schema_version}"
                )

            elif phase == self.ACT:
                # Tarpit delay
                tarpit_delay_ms = int(
                    self._tarpit_base_delay_ms * max(detection_confidence, 0.5)
                )
                details.append(f"Act: tarpit delay {tarpit_delay_ms}ms")

        # Update per-session disrupted phases
        if session_id not in self._disrupted_phases:
            self._disrupted_phases[session_id] = set()
        self._disrupted_phases[session_id].update(phases_to_disrupt)

        score = self.get_loop_disruption_score(session_id)

        return DisruptionResult(
            phases_disrupted=phases_to_disrupt,
            disruption_score=score,
            session_rotated=session_rotated,
            nonce_issued=nonce_issued,
            schema_mutated=schema_mutated,
            tarpit_delay_ms=tarpit_delay_ms,
            fake_data_injected=fake_data_injected,
            detail="; ".join(details),
        )

    def get_loop_disruption_score(self, session_id: str) -> float:
        """
        How disrupted is this attacker's OODA loop? (0-1)
        0 = attacker's loop is intact
        1 = all 4 phases disrupted, loop is collapsed
        """
        if session_id not in self._disrupted_phases:
            return 0.0
        disrupted = self._disrupted_phases[session_id]
        return len(disrupted.intersection(set(self.ALL_PHASES))) / len(self.ALL_PHASES)
