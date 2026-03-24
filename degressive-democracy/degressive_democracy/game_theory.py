"""Game theory analysis for degressive democracy.

Formalizes payoff functions, Nash equilibrium conditions, and
strategic analysis for the degressive voting mechanism.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .models import PowerModel, compute_power


# ---------------------------------------------------------------------------
# Payoff parameters
# ---------------------------------------------------------------------------

@dataclass
class DegressivePayoffParams:
    """Parameters for computing politician strategy payoffs."""
    benefit_power: float = 1.0           # utility per tick per unit of power
    cost_effort: float = 0.3             # cost of fulfilling promises per tick
    benefit_broken: float = 0.2          # saved effort from breaking a promise

    withdrawal_rate_per_broken: float = 0.15  # fraction who withdraw per broken promise
    withdrawal_rate_keeper: float = 0.02       # base withdrawal rate even for keepers

    term_ticks: int = 48
    initial_votes: int = 200
    n_promises: int = 5
    power_model: PowerModel = PowerModel.LINEAR


@dataclass
class StrategyPayoff:
    """Computed payoff for a single strategy."""
    strategy: str
    total_utility: float
    power_integral: float  # sum of power over all ticks
    effort_cost: float
    final_votes: int
    final_power: float


# ---------------------------------------------------------------------------
# Payoff computation
# ---------------------------------------------------------------------------

def _power_integral(
    initial_votes: int,
    withdrawal_rate_per_tick: float,
    term_ticks: int,
    power_model: PowerModel,
) -> tuple[float, int, float]:
    """Compute power integral over the term.

    Returns (power_sum, final_votes, final_power).
    """
    votes = float(initial_votes)
    power_sum = 0.0
    for t in range(term_ticks):
        lost = votes * withdrawal_rate_per_tick
        votes = max(0.0, votes - lost)
        power = compute_power(int(votes), initial_votes, power_model)
        power_sum += power
    final_votes = int(votes)
    final_power = compute_power(final_votes, initial_votes, power_model)
    return power_sum, final_votes, final_power


def compute_keeper_payoff(params: DegressivePayoffParams) -> StrategyPayoff:
    """Payoff for a politician who keeps all promises."""
    # Low base withdrawal rate
    rate = params.withdrawal_rate_keeper / params.term_ticks
    pi, fv, fp = _power_integral(
        params.initial_votes, rate, params.term_ticks, params.power_model
    )
    effort = params.cost_effort * params.term_ticks
    utility = params.benefit_power * pi - effort
    return StrategyPayoff("keeper", utility, pi, effort, fv, fp)


def compute_breaker_payoff(
    params: DegressivePayoffParams,
    n_broken: int = 1,
) -> StrategyPayoff:
    """Payoff for a politician who breaks n promises."""
    # Higher withdrawal rate proportional to broken promises
    total_rate = (
        params.withdrawal_rate_keeper
        + params.withdrawal_rate_per_broken * n_broken
    )
    rate = total_rate / params.term_ticks
    pi, fv, fp = _power_integral(
        params.initial_votes, rate, params.term_ticks, params.power_model
    )
    # Saves effort on broken promises
    effort_saved = params.benefit_broken * n_broken
    effort = params.cost_effort * params.term_ticks - effort_saved
    utility = params.benefit_power * pi - effort
    return StrategyPayoff(f"breaker_{n_broken}", utility, pi, effort, fv, fp)


def compute_populist_payoff(params: DegressivePayoffParams) -> StrategyPayoff:
    """Payoff for a populist who makes 2x promises but breaks most."""
    n_total = params.n_promises * 2
    n_broken = int(n_total * 0.7)  # breaks 70%
    total_rate = (
        params.withdrawal_rate_keeper
        + params.withdrawal_rate_per_broken * n_broken
    )
    rate = total_rate / params.term_ticks
    pi, fv, fp = _power_integral(
        params.initial_votes, rate, params.term_ticks, params.power_model
    )
    effort_saved = params.benefit_broken * n_broken
    effort = params.cost_effort * params.term_ticks - effort_saved
    utility = params.benefit_power * pi - effort
    return StrategyPayoff("populist", utility, pi, effort, fv, fp)


def compute_strategic_min_payoff(params: DegressivePayoffParams) -> StrategyPayoff:
    """Payoff for strategic minimum: keeps visible, breaks invisible."""
    # Breaks ~40% of promises (the invisible ones)
    n_broken = int(params.n_promises * 0.4)
    # Lower withdrawal rate because broken promises were invisible
    total_rate = (
        params.withdrawal_rate_keeper
        + params.withdrawal_rate_per_broken * n_broken * 0.3  # 30% visibility penalty
    )
    rate = total_rate / params.term_ticks
    pi, fv, fp = _power_integral(
        params.initial_votes, rate, params.term_ticks, params.power_model
    )
    effort_saved = params.benefit_broken * n_broken
    effort = params.cost_effort * params.term_ticks - effort_saved
    utility = params.benefit_power * pi - effort
    return StrategyPayoff("strategic_min", utility, pi, effort, fv, fp)


# ---------------------------------------------------------------------------
# Nash equilibrium analysis
# ---------------------------------------------------------------------------

@dataclass
class NashResult:
    """Result of Nash equilibrium check."""
    is_nash: bool
    dominant_strategy: str
    payoffs: dict[str, float]
    deviation_gains: dict[str, float]  # gain from deviating to each strategy
    condition: str  # human-readable condition


def check_nash_equilibrium(
    params: Optional[DegressivePayoffParams] = None,
) -> NashResult:
    """Check whether promise-keeping is a Nash equilibrium.

    Tests all deviation strategies against keeping promises.
    """
    if params is None:
        params = DegressivePayoffParams()

    keeper = compute_keeper_payoff(params)
    strategies = {
        "keeper": keeper,
        "breaker_1": compute_breaker_payoff(params, n_broken=1),
        "breaker_3": compute_breaker_payoff(params, n_broken=3),
        "breaker_all": compute_breaker_payoff(params, n_broken=params.n_promises),
        "populist": compute_populist_payoff(params),
        "strategic_min": compute_strategic_min_payoff(params),
    }

    payoffs = {name: s.total_utility for name, s in strategies.items()}
    deviation_gains = {
        name: s.total_utility - keeper.total_utility
        for name, s in strategies.items()
        if name != "keeper"
    }

    # Promise-keeping is Nash if no deviation yields higher payoff
    is_nash = all(gain <= 0 for gain in deviation_gains.values())
    dominant = max(payoffs, key=payoffs.get)  # type: ignore

    # Derive closed-form condition for LINEAR model
    # For keeping to dominate breaking 1 promise:
    # benefit_power * (power_kept - power_lost) > benefit_broken
    condition = (
        f"Keeping is Nash iff: "
        f"benefit_power × withdrawal_penalty > benefit_broken. "
        f"With current params: {params.benefit_power} × "
        f"{params.withdrawal_rate_per_broken * params.term_ticks / 2:.2f} "
        f"= {params.benefit_power * params.withdrawal_rate_per_broken * params.term_ticks / 2:.2f} "
        f"{'>' if is_nash else '<='} {params.benefit_broken}"
    )

    return NashResult(
        is_nash=is_nash,
        dominant_strategy=dominant,
        payoffs=payoffs,
        deviation_gains=deviation_gains,
        condition=condition,
    )


# ---------------------------------------------------------------------------
# Parameter sweep
# ---------------------------------------------------------------------------

@dataclass
class SweepResult:
    """Result of a parameter sweep."""
    param_name: str
    values: list[float]
    nash_results: list[bool]
    dominant_strategies: list[str]
    critical_value: Optional[float] = None  # value where Nash flips


def parameter_sweep(
    param_name: str,
    values: list[float],
    base_params: Optional[DegressivePayoffParams] = None,
) -> SweepResult:
    """Sweep a parameter to find where Nash equilibrium breaks."""
    if base_params is None:
        base_params = DegressivePayoffParams()

    nash_results = []
    dominant_strategies = []
    critical_value = None
    prev_nash = None

    for val in values:
        params = DegressivePayoffParams(
            benefit_power=base_params.benefit_power,
            cost_effort=base_params.cost_effort,
            benefit_broken=base_params.benefit_broken,
            withdrawal_rate_per_broken=base_params.withdrawal_rate_per_broken,
            withdrawal_rate_keeper=base_params.withdrawal_rate_keeper,
            term_ticks=base_params.term_ticks,
            initial_votes=base_params.initial_votes,
            n_promises=base_params.n_promises,
            power_model=base_params.power_model,
        )
        setattr(params, param_name, val)

        result = check_nash_equilibrium(params)
        nash_results.append(result.is_nash)
        dominant_strategies.append(result.dominant_strategy)

        if prev_nash is not None and result.is_nash != prev_nash and critical_value is None:
            critical_value = val

        prev_nash = result.is_nash

    return SweepResult(
        param_name=param_name,
        values=values,
        nash_results=nash_results,
        dominant_strategies=dominant_strategies,
        critical_value=critical_value,
    )


# ---------------------------------------------------------------------------
# Coordination attack analysis
# ---------------------------------------------------------------------------

@dataclass
class CoordinationBound:
    """Minimum coordinated withdrawal to trigger power threshold."""
    threshold_name: str
    power_threshold: float
    votes_needed: int
    fraction_needed: float


def coordination_attack_bounds(
    initial_votes: int = 200,
    power_model: PowerModel = PowerModel.THRESHOLD,
) -> list[CoordinationBound]:
    """Calculate how many coordinated withdrawals trigger each power threshold."""
    bounds = []

    if power_model == PowerModel.THRESHOLD:
        thresholds = [
            ("full_to_reduced", 0.75),
            ("reduced_to_weak", 0.50),
            ("weak_to_powerless", 0.25),
        ]
    else:
        thresholds = [
            ("half_power", 0.50),
            ("quarter_power", 0.25),
            ("near_powerless", 0.10),
        ]

    for name, threshold in thresholds:
        votes_needed = initial_votes - int(initial_votes * threshold)
        fraction = votes_needed / initial_votes if initial_votes > 0 else 0
        bounds.append(CoordinationBound(
            threshold_name=name,
            power_threshold=threshold,
            votes_needed=votes_needed,
            fraction_needed=fraction,
        ))

    return bounds
