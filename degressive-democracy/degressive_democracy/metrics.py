"""Metrics computation for simulation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import (
    PoliticianState,
    PromiseStatus,
    SimulationResult,
    TickResult,
)


@dataclass
class SimulationMetrics:
    """Computed metrics for a simulation run."""

    # Promise compliance
    promise_fulfillment_rate: float = 0.0
    promise_broken_rate: float = 0.0
    avg_promise_progress: float = 0.0

    # Withdrawal dynamics
    total_withdrawals: int = 0
    withdrawal_curve: list[float] = field(default_factory=list)
    withdrawal_velocity: list[float] = field(default_factory=list)
    peak_withdrawal_tick: int = 0

    # Power dynamics
    final_power_levels: dict[str, float] = field(default_factory=dict)
    power_curves: dict[str, list[float]] = field(default_factory=dict)

    # Citizen satisfaction
    avg_final_satisfaction: float = 0.0
    satisfaction_curve: list[float] = field(default_factory=list)

    # System-level
    effective_accountability: float = 0.0
    degressive_pressure_index: float = 0.0


def compute_metrics(
    result: SimulationResult,
    politicians: list[PoliticianState],
) -> SimulationMetrics:
    """Compute all metrics from a simulation result."""
    m = SimulationMetrics()

    if not result.tick_results:
        return m

    # --- Promise compliance ---
    total_promises = 0
    fulfilled = 0
    broken = 0
    total_progress = 0.0

    for pol in politicians:
        for ps in pol.promise_states.values():
            total_promises += 1
            total_progress += ps.progress
            if ps.status == PromiseStatus.FULFILLED:
                fulfilled += 1
            elif ps.status in (PromiseStatus.BROKEN, PromiseStatus.ABANDONED):
                broken += 1

    if total_promises > 0:
        m.promise_fulfillment_rate = fulfilled / total_promises
        m.promise_broken_rate = broken / total_promises
        m.avg_promise_progress = total_progress / total_promises

    # --- Withdrawal dynamics ---
    cumulative = 0
    initial_total = sum(p.initial_votes for p in politicians)
    max_withdrawals_tick = 0
    max_tick = 0

    for tr in result.tick_results:
        count = len(tr.withdrawals)
        cumulative += count
        rate = cumulative / initial_total if initial_total > 0 else 0.0
        m.withdrawal_curve.append(rate)
        m.withdrawal_velocity.append(count)

        if count > max_withdrawals_tick:
            max_withdrawals_tick = count
            max_tick = tr.tick

    m.total_withdrawals = cumulative
    m.peak_withdrawal_tick = max_tick

    # --- Power dynamics ---
    for pol in politicians:
        m.final_power_levels[pol.politician_id] = pol.power
        m.power_curves[pol.politician_id] = [
            tr.power_levels.get(pol.politician_id, 1.0)
            for tr in result.tick_results
        ]

    # --- Satisfaction ---
    m.satisfaction_curve = [tr.avg_satisfaction for tr in result.tick_results]
    if m.satisfaction_curve:
        m.avg_final_satisfaction = m.satisfaction_curve[-1]

    # --- Effective accountability ---
    # Correlation between broken promises and withdrawal rate
    if len(politicians) >= 2:
        broken_rates = []
        withdrawal_rates = []
        for pol in politicians:
            total_p = len(pol.promise_states)
            broken_p = sum(
                1 for ps in pol.promise_states.values()
                if ps.status in (PromiseStatus.BROKEN, PromiseStatus.ABANDONED)
            )
            broken_rates.append(broken_p / total_p if total_p > 0 else 0.0)
            wr = 1.0 - (pol.current_votes / pol.initial_votes) if pol.initial_votes > 0 else 0.0
            withdrawal_rates.append(wr)

        m.effective_accountability = _pearson(broken_rates, withdrawal_rates)

    # --- Degressive pressure index ---
    # Average power loss per broken promise
    if m.promise_broken_rate > 0 and initial_total > 0:
        avg_power_loss = 1.0 - (sum(m.final_power_levels.values()) / len(m.final_power_levels))
        m.degressive_pressure_index = avg_power_loss / m.promise_broken_rate

    return m


def _pearson(x: list[float], y: list[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)
    denom = (var_x * var_y) ** 0.5
    if denom == 0:
        return 0.0
    return cov / denom
