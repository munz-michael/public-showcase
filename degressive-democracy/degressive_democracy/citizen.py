"""Citizen agent: satisfaction tracking and withdrawal decision."""

from __future__ import annotations

from .models import (
    CitizenBehavior,
    CitizenState,
    PoliticianState,
    PromiseStatus,
)


# ---------------------------------------------------------------------------
# Configurable satisfaction parameters
#
# Default: Prospect Theory (Kahneman & Tversky 1979)
# Loss aversion lambda=2.25 applied to BROKEN_PENALTY
# Reference: Tversky, A. & Kahneman, D. (1992). Advances in prospect theory.
# JRSP, 5(4), 297-323. Parameters: alpha=0.88, beta=0.88, lambda=2.25
# ---------------------------------------------------------------------------

FULFILLED_BONUS: float = 0.1
BROKEN_PENALTY: float = 0.3 * 2.25  # 0.675 — Prospect Theory loss aversion
PROGRESS_SCALING: float = 0.5


# ---------------------------------------------------------------------------
# Satisfaction update
# ---------------------------------------------------------------------------

def _promise_weight(visibility: float, is_priority: bool) -> float:
    """Weight a promise's impact on satisfaction."""
    return visibility * (1.5 if is_priority else 1.0)


def update_satisfaction(
    citizen: CitizenState,
    politician: PoliticianState,
    tick: int,
    term_length: int = 48,
) -> float:
    """Update citizen satisfaction based on politician's promise progress.

    Returns the new satisfaction value (also written to citizen.satisfaction).
    """
    if not politician.promises:
        return citizen.satisfaction

    term_progress = tick / term_length if tick > 0 else 0.01
    delta = 0.0
    total_weight = 0.0

    for promise in politician.promises:
        ps = politician.promise_states.get(promise.promise_id)
        if ps is None:
            continue

        is_priority = (
            promise.category in citizen.priority_categories
            if citizen.priority_categories
            else True  # all count equally if no priorities set
        )
        w = _promise_weight(promise.visibility, is_priority)
        total_weight += w

        # Expected progress: linear with time
        expected = min(term_progress, 1.0)
        actual = ps.progress

        # Blame attribution: how much the citizen blames the politician
        # LOYAL citizens are more forgiving, VOLATILE less so
        blame = ps.blame
        if citizen.behavior == CitizenBehavior.LOYAL:
            blame = blame * 0.5  # loyal citizens give benefit of doubt
        elif citizen.behavior == CitizenBehavior.VOLATILE:
            blame = min(blame * 1.5, 1.0)  # volatile citizens blame fully

        if ps.status == PromiseStatus.FULFILLED:
            delta += w * FULFILLED_BONUS
        elif ps.status in (PromiseStatus.BROKEN, PromiseStatus.ABANDONED):
            delta -= w * BROKEN_PENALTY * blame
        else:
            delta += w * (actual - expected) * PROGRESS_SCALING * blame

    if total_weight > 0:
        delta /= total_weight

    citizen.satisfaction = max(0.0, min(1.0, citizen.satisfaction + delta))
    return citizen.satisfaction


# ---------------------------------------------------------------------------
# Withdrawal decision
# ---------------------------------------------------------------------------

def decide_withdrawal(
    citizen: CitizenState,
    tick: int,
    term_length: int,
    peer_withdrawal_rate: float = 0.0,
) -> bool:
    """Decide whether the citizen withdraws their vote this tick.

    Returns True if the citizen decides to withdraw.
    Enforces the once-only constraint: if has_withdrawn is True, always returns False.
    """
    # Hard constraint: can only withdraw once, never return
    if citizen.has_withdrawn:
        return False

    # Apathetic citizens never withdraw
    if citizen.behavior == CitizenBehavior.APATHETIC:
        return False

    threshold = citizen.withdrawal_threshold

    # Behavior-specific adjustments
    if citizen.behavior == CitizenBehavior.LOYAL:
        threshold = min(threshold, 0.2)
    elif citizen.behavior == CitizenBehavior.VOLATILE:
        threshold = max(threshold, 0.6)
    elif citizen.behavior == CitizenBehavior.PEER_INFLUENCED:
        if peer_withdrawal_rate > 0.3:
            threshold = min(threshold + 0.15, 0.9)  # easier to trigger
    elif citizen.behavior == CitizenBehavior.STRATEGIC:
        # Only withdraw in the last 40% of the term
        if tick < term_length * 0.6:
            return False

    return citizen.satisfaction < threshold


def execute_withdrawal(citizen: CitizenState, tick: int) -> None:
    """Execute the withdrawal (mutates citizen state).

    Must only be called after decide_withdrawal returns True.
    """
    if citizen.has_withdrawn:
        raise ValueError(f"Citizen {citizen.citizen_id} has already withdrawn")
    citizen.has_withdrawn = True
    citizen.withdrawn_tick = tick
