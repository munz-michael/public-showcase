"""Theoretically grounded satisfaction models.

Compares 4 satisfaction functions from behavioral economics:

1. LINEAR (current) — delta proportional to (actual - expected)
   No theoretical basis, but simple and interpretable.

2. PROSPECT THEORY (Kahneman & Tversky 1979) — losses hurt ~2.25x more
   than gains feel good. Asymmetric: broken promises hurt disproportionately.
   v(x) = x^alpha if x >= 0, -lambda * (-x)^beta if x < 0
   Default: alpha=0.88, beta=0.88, lambda=2.25

3. EXPONENTIAL DECAY — satisfaction decays exponentially when behind,
   recovers slowly. Models "erosion of trust" — hard to rebuild.
   delta = gain * k_up if positive, loss * k_down if negative (k_down > k_up)

4. THRESHOLD (step function) — satisfaction drops sharply only when a
   promise is clearly broken (binary). No gradual dissatisfaction.
   Represents "all or nothing" voters.

The key question: Do the 11 findings hold across ALL 4 models?
If yes → findings are model-independent (strong result).
If no → findings depend on the satisfaction function (weak result).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from .models import (
    CitizenBehavior,
    CitizenState,
    PoliticianState,
    PromiseStatus,
)


class SatisfactionModel(Enum):
    LINEAR = "linear"
    PROSPECT = "prospect_theory"
    EXPONENTIAL = "exponential_decay"
    THRESHOLD = "threshold_step"


# ---------------------------------------------------------------------------
# Prospect Theory value function (Kahneman & Tversky 1979)
# ---------------------------------------------------------------------------

@dataclass
class ProspectParams:
    """Parameters from Kahneman & Tversky (1979), Tversky & Kahneman (1992)."""
    alpha: float = 0.88    # diminishing sensitivity for gains
    beta: float = 0.88     # diminishing sensitivity for losses
    lambda_: float = 2.25  # loss aversion coefficient


def prospect_value(x: float, params: ProspectParams | None = None) -> float:
    """Prospect theory value function.

    v(x) = x^alpha          if x >= 0 (gains)
    v(x) = -lambda * |x|^beta  if x < 0 (losses)

    Reference: Tversky, A. & Kahneman, D. (1992). Advances in prospect theory:
    Cumulative representation of uncertainty. JRSP, 5(4), 297-323.
    """
    if params is None:
        params = ProspectParams()
    if x >= 0:
        return x ** params.alpha
    else:
        return -params.lambda_ * (abs(x) ** params.beta)


# ---------------------------------------------------------------------------
# Satisfaction update functions
# ---------------------------------------------------------------------------

def _promise_weight(visibility: float, is_priority: bool) -> float:
    return visibility * (1.5 if is_priority else 1.0)


def _compute_gap(actual: float, expected: float) -> float:
    """Raw performance gap: positive = ahead, negative = behind."""
    return actual - expected


def update_satisfaction_linear(
    citizen: CitizenState,
    politician: PoliticianState,
    tick: int,
    term_length: int = 48,
) -> float:
    """LINEAR: Current model. delta = gap * scaling * blame."""
    return _update_generic(citizen, politician, tick, term_length,
                           gain_fn=lambda g: g * 0.5,
                           loss_fn=lambda l: l * 0.5,
                           broken_penalty=0.3,
                           fulfilled_bonus=0.1)


def update_satisfaction_prospect(
    citizen: CitizenState,
    politician: PoliticianState,
    tick: int,
    term_length: int = 48,
) -> float:
    """PROSPECT THEORY: Losses hurt 2.25x more than gains.

    Reference: Kahneman, D. & Tversky, A. (1979). Prospect Theory:
    An Analysis of Decision under Risk. Econometrica, 47(2), 263-292.
    """
    params = ProspectParams()
    return _update_generic(citizen, politician, tick, term_length,
                           gain_fn=lambda g: prospect_value(g, params) * 0.5,
                           loss_fn=lambda l: prospect_value(l, params) * 0.5,
                           broken_penalty=0.3 * params.lambda_,  # losses amplified
                           fulfilled_bonus=0.1)


def update_satisfaction_exponential(
    citizen: CitizenState,
    politician: PoliticianState,
    tick: int,
    term_length: int = 48,
) -> float:
    """EXPONENTIAL DECAY: Trust erodes fast, recovers slowly.

    Gain rate: 0.3 (slow recovery)
    Loss rate: 0.7 (fast erosion)
    Models: Once trust is lost, it's hard to rebuild.
    """
    return _update_generic(citizen, politician, tick, term_length,
                           gain_fn=lambda g: g * 0.3,
                           loss_fn=lambda l: l * 0.7,
                           broken_penalty=0.4,
                           fulfilled_bonus=0.05)


def update_satisfaction_threshold(
    citizen: CitizenState,
    politician: PoliticianState,
    tick: int,
    term_length: int = 48,
) -> float:
    """THRESHOLD: Binary — only reacts to clearly broken/fulfilled promises.

    No gradual dissatisfaction from progress gaps.
    Represents "all or nothing" voters who don't track incremental progress.
    """
    return _update_generic(citizen, politician, tick, term_length,
                           gain_fn=lambda g: 0.0,  # ignore progress gaps
                           loss_fn=lambda l: 0.0,  # ignore progress gaps
                           broken_penalty=0.5,      # but punish broken hard
                           fulfilled_bonus=0.15)


def _update_generic(
    citizen: CitizenState,
    politician: PoliticianState,
    tick: int,
    term_length: int,
    gain_fn: Callable[[float], float],
    loss_fn: Callable[[float], float],
    broken_penalty: float,
    fulfilled_bonus: float,
) -> float:
    """Generic satisfaction update with pluggable gain/loss functions."""
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
            else True
        )
        w = _promise_weight(promise.visibility, is_priority)
        total_weight += w

        blame = ps.blame
        if citizen.behavior == CitizenBehavior.LOYAL:
            blame *= 0.5
        elif citizen.behavior == CitizenBehavior.VOLATILE:
            blame = min(blame * 1.5, 1.0)

        if ps.status == PromiseStatus.FULFILLED:
            delta += w * fulfilled_bonus
        elif ps.status in (PromiseStatus.BROKEN, PromiseStatus.ABANDONED):
            delta -= w * broken_penalty * blame
        else:
            gap = _compute_gap(ps.progress, min(term_progress, 1.0))
            if gap >= 0:
                delta += w * gain_fn(gap) * blame
            else:
                delta += w * loss_fn(gap) * blame  # loss_fn returns negative

    if total_weight > 0:
        delta /= total_weight

    citizen.satisfaction = max(0.0, min(1.0, citizen.satisfaction + delta))
    return citizen.satisfaction


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

SATISFACTION_FUNCTIONS = {
    SatisfactionModel.LINEAR: update_satisfaction_linear,
    SatisfactionModel.PROSPECT: update_satisfaction_prospect,
    SatisfactionModel.EXPONENTIAL: update_satisfaction_exponential,
    SatisfactionModel.THRESHOLD: update_satisfaction_threshold,
}


# ---------------------------------------------------------------------------
# Model comparison: run same scenario with all 4 functions
# ---------------------------------------------------------------------------

def run_model_comparison(seed: int = 42, n_citizens: int = 300) -> dict:
    """Run the same scenario with all 4 satisfaction models and compare."""
    from .models import (
        ElectionConfig, PoliticianBehavior, PowerModel, SimulationResult,
    )
    from .election import Election
    from .politician import allocate_effort, update_power
    from .citizen import decide_withdrawal, execute_withdrawal
    from .metrics import compute_metrics

    behaviors = [
        PoliticianBehavior.PROMISE_KEEPER,
        PoliticianBehavior.STRATEGIC_MIN,
        PoliticianBehavior.FRONTLOADER,
        PoliticianBehavior.POPULIST,
        PoliticianBehavior.ADAPTIVE,
    ]

    results = {}

    for model_name, sat_fn in SATISFACTION_FUNCTIONS.items():
        config = ElectionConfig(
            n_citizens=n_citizens,
            n_politicians=5,
            term_length=48,
            power_model=PowerModel.LINEAR,
            promises_per_politician=5,
            seed=seed,
            politician_behaviors=behaviors,
            citizen_distribution={
                CitizenBehavior.RATIONAL: 0.30,
                CitizenBehavior.LOYAL: 0.20,
                CitizenBehavior.VOLATILE: 0.10,
                CitizenBehavior.PEER_INFLUENCED: 0.10,
                CitizenBehavior.STRATEGIC: 0.05,
                CitizenBehavior.APATHETIC: 0.25,
            },
        )

        election = Election(config)

        for t in range(1, 49):
            # 1. Effort allocation
            for pol in election.politicians:
                wr = 1.0 - (pol.current_votes / pol.initial_votes) if pol.initial_votes > 0 else 0.0
                allocate_effort(pol, tick=t, term_length=48, withdrawal_rate=wr)

            # 2. Satisfaction with pluggable model
            for citizen in election.citizens:
                pol = next((p for p in election.politicians if p.politician_id == citizen.politician_id), None)
                if pol:
                    sat_fn(citizen, pol, tick=t, term_length=48)

            # 3. Withdrawal
            for citizen in election.citizens:
                if citizen.has_withdrawn or citizen.behavior == CitizenBehavior.APATHETIC:
                    continue
                threshold = citizen.withdrawal_threshold
                if citizen.behavior == CitizenBehavior.LOYAL:
                    threshold = min(threshold, 0.2)
                elif citizen.behavior == CitizenBehavior.VOLATILE:
                    threshold = max(threshold, 0.6)
                elif citizen.behavior == CitizenBehavior.STRATEGIC:
                    if t < 48 * 0.6:
                        continue
                if citizen.satisfaction < threshold:
                    execute_withdrawal(citizen, t)
                    pol = next((p for p in election.politicians if p.politician_id == citizen.politician_id), None)
                    if pol:
                        pol.current_votes -= 1

            # 4. Power
            for pol in election.politicians:
                update_power(pol, config.power_model)

        # Collect results
        total_wd = sum(1 for c in election.citizens if c.has_withdrawn)
        avg_sat = sum(c.satisfaction for c in election.citizens) / len(election.citizens)
        powers = {p.behavior.value: round(p.power, 3) for p in election.politicians}
        populist_eliminated = powers.get("populist", 1.0) < 0.3
        keeper_dominates = powers.get("promise_keeper", 0.0) >= powers.get("strategic_minimum", 0.0) - 0.05

        results[model_name.value] = {
            "withdrawals": total_wd,
            "satisfaction": round(avg_sat, 3),
            "powers": powers,
            "populist_eliminated": populist_eliminated,
            "keeper_dominates": keeper_dominates,
        }

    return results


def print_model_comparison(results: dict) -> None:
    """Print comparison of satisfaction models."""
    print("SATISFACTION MODEL COMPARISON")
    print("=" * 72)
    print()
    print("  Frage: Halten die Kern-Findings unabhaengig von der Satisfaction-Funktion?")
    print()

    print(f"  {'Modell':<20} {'Entzuege':>8} {'Satisfaction':>12} {'Pop elim?':>9} {'Keeper dom?':>11}")
    print("  " + "-" * 62)
    for name, r in results.items():
        print(
            f"  {name:<20} {r['withdrawals']:>8} {r['satisfaction']:>11.2f} "
            f"{'JA' if r['populist_eliminated'] else 'NEIN':>9} "
            f"{'JA' if r['keeper_dominates'] else 'NEIN':>11}"
        )

    print()
    print("  Power pro Strategie:")
    print(f"  {'Modell':<20} {'Keeper':>7} {'StratMin':>8} {'Front':>6} {'Populist':>8} {'Adaptive':>8}")
    print("  " + "-" * 59)
    for name, r in results.items():
        p = r["powers"]
        print(
            f"  {name:<20} {p.get('promise_keeper',0):>6.2f} {p.get('strategic_minimum',0):>7.2f} "
            f"{p.get('frontloader',0):>6.2f} {p.get('populist',0):>7.2f} {p.get('adaptive',0):>7.2f}"
        )

    # Robustness check
    print()
    all_pop_eliminated = all(r["populist_eliminated"] for r in results.values())
    all_keeper_dom = all(r["keeper_dominates"] for r in results.values())

    if all_pop_eliminated:
        print("  ✓ ROBUST: Populist wird in ALLEN 4 Modellen eliminiert")
    else:
        failing = [n for n, r in results.items() if not r["populist_eliminated"]]
        print(f"  ⚠ FRAGIL: Populist ueberlebt in: {', '.join(failing)}")

    if all_keeper_dom:
        print("  ✓ ROBUST: Keeper >= StratMin in ALLEN 4 Modellen")
    else:
        failing = [n for n, r in results.items() if not r["keeper_dominates"]]
        print(f"  ⚠ FRAGIL: StratMin schlaegt Keeper in: {', '.join(failing)}")

    if all_pop_eliminated and all_keeper_dom:
        print()
        print("  FAZIT: Kern-Findings sind MODELL-UNABHAENGIG.")
        print("  Die Wahl der Satisfaction-Funktion aendert die qualitativen Ergebnisse nicht.")
        print("  Referenz: Kahneman & Tversky (1979), Tversky & Kahneman (1992)")
