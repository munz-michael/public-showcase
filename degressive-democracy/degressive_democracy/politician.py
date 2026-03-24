"""Politician agent: effort allocation and power management."""

from __future__ import annotations

from .models import (
    PoliticianBehavior,
    PoliticianState,
    PowerModel,
    PromiseState,
    PromiseStatus,
    compute_power,
)


# ---------------------------------------------------------------------------
# Effort allocation strategies
# ---------------------------------------------------------------------------

def allocate_effort(
    politician: PoliticianState,
    tick: int,
    term_length: int,
    withdrawal_rate: float = 0.0,
) -> None:
    """Allocate effort budget across promises for this tick.

    Mutates promise_states in-place.
    """
    active_promises = [
        ps for ps in politician.promise_states.values()
        if ps.status not in (PromiseStatus.FULFILLED, PromiseStatus.BROKEN, PromiseStatus.ABANDONED)
    ]
    if not active_promises:
        return

    # Effective effort reduced by power level (feedback loop)
    effective_effort = politician.effort_budget_per_tick * politician.power

    behavior = politician.behavior

    if behavior == PoliticianBehavior.PROMISE_KEEPER:
        _allocate_equal(active_promises, effective_effort, politician)

    elif behavior == PoliticianBehavior.STRATEGIC_MIN:
        _allocate_strategic_min(active_promises, effective_effort, politician)

    elif behavior == PoliticianBehavior.FRONTLOADER:
        _allocate_frontloader(active_promises, effective_effort, politician)

    elif behavior == PoliticianBehavior.POPULIST:
        _allocate_populist(active_promises, effective_effort, politician)

    elif behavior == PoliticianBehavior.ADAPTIVE:
        _allocate_adaptive(active_promises, effective_effort, politician, withdrawal_rate)

    # Update statuses
    for ps in politician.promise_states.values():
        _update_promise_status(ps, tick, term_length)


def _effective_diff(ps: PromiseState, politician: PoliticianState) -> float:
    """Get effective difficulty (accounts for external shocks)."""
    if ps.effective_difficulty > 0:
        return ps.effective_difficulty
    promise = _get_promise(politician, ps.promise_id)
    return promise.difficulty if promise else 0.5


def _allocate_equal(
    active: list[PromiseState],
    budget: float,
    politician: PoliticianState,
) -> None:
    """Distribute effort equally across all active promises."""
    per_promise = budget / len(active)
    for ps in active:
        difficulty = _effective_diff(ps, politician)
        progress_gain = per_promise / max(difficulty, 0.1)
        ps.effort_invested += per_promise
        ps.progress = min(1.0, ps.progress + progress_gain / 10.0)


def _allocate_strategic_min(
    active: list[PromiseState],
    budget: float,
    politician: PoliticianState,
) -> None:
    """Only invest in high-visibility promises."""
    visible = []
    for ps in active:
        promise = _get_promise(politician, ps.promise_id)
        if promise and promise.visibility >= 0.5:
            visible.append((ps, promise))

    if not visible:
        return  # let low-visibility promises rot

    per_promise = budget / len(visible)
    for ps, promise in visible:
        difficulty = _effective_diff(ps, politician)
        progress_gain = per_promise / max(difficulty, 0.1)
        ps.effort_invested += per_promise
        ps.progress = min(1.0, ps.progress + progress_gain / 10.0)


def _allocate_frontloader(
    active: list[PromiseState],
    budget: float,
    politician: PoliticianState,
) -> None:
    """Allocate to easiest promises first (sorted by difficulty ascending)."""
    sorted_promises = []
    for ps in active:
        diff = _effective_diff(ps, politician)
        sorted_promises.append((ps, diff))
    sorted_promises.sort(key=lambda x: x[1])

    remaining = budget
    for ps, diff in sorted_promises:
        if remaining <= 0:
            break
        needed = max(0.0, (1.0 - ps.progress) * diff * 10.0)
        allocated = min(remaining, max(needed, remaining / len(sorted_promises)))
        progress_gain = allocated / max(diff, 0.1)
        ps.effort_invested += allocated
        ps.progress = min(1.0, ps.progress + progress_gain / 10.0)
        remaining -= allocated


def _allocate_populist(
    active: list[PromiseState],
    budget: float,
    politician: PoliticianState,
) -> None:
    """Spread effort thinly across many promises (populists make more promises)."""
    per_promise = budget / (len(active) * 2)  # intentionally thin
    for ps in active:
        difficulty = _effective_diff(ps, politician)
        progress_gain = per_promise / max(difficulty, 0.1)
        ps.effort_invested += per_promise
        ps.progress = min(1.0, ps.progress + progress_gain / 10.0)


def _allocate_adaptive(
    active: list[PromiseState],
    budget: float,
    politician: PoliticianState,
    withdrawal_rate: float,
) -> None:
    """Shift effort to high-visibility promises when withdrawal pressure rises."""
    if withdrawal_rate > 0.1:
        # Under pressure: focus on visible promises
        _allocate_strategic_min(active, budget, politician)
    else:
        # Relaxed: equal distribution
        _allocate_equal(active, budget, politician)


# ---------------------------------------------------------------------------
# Promise status updates
# ---------------------------------------------------------------------------

def _update_promise_status(ps: PromiseState, tick: int, term_length: int) -> None:
    """Update promise status based on progress and time."""
    if ps.status in (PromiseStatus.FULFILLED, PromiseStatus.BROKEN, PromiseStatus.ABANDONED):
        return

    if ps.progress >= 1.0:
        ps.status = PromiseStatus.FULFILLED
    elif ps.progress > 0.0:
        ps.status = PromiseStatus.PROGRESSING
    elif tick >= term_length:
        # End of term with no progress = broken
        ps.status = PromiseStatus.BROKEN


def _get_promise(politician: PoliticianState, promise_id: str):
    """Find a promise by ID in the politician's promise list."""
    for p in politician.promises:
        if p.promise_id == promise_id:
            return p
    return None


# ---------------------------------------------------------------------------
# Power update
# ---------------------------------------------------------------------------

def update_power(politician: PoliticianState, power_model: PowerModel) -> float:
    """Recalculate politician's power based on current votes.

    Returns new power level (also written to politician.power).
    """
    politician.power = compute_power(
        politician.current_votes,
        politician.initial_votes,
        power_model,
    )
    return politician.power
