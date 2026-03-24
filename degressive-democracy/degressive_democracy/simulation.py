"""Predefined simulation scenarios."""

from __future__ import annotations

import sys
from typing import Callable, Optional

from .models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
    SimulationResult,
)
from .election import Election
from .metrics import SimulationMetrics, compute_metrics

# Provenance integration (optional)
try:
    # Provenance chain (optional, not included in standalone package)
    from provenance import ProvenanceChain
    HAS_PROVENANCE = True
except ImportError:
    HAS_PROVENANCE = False


def _run_scenario(
    name: str,
    config: ElectionConfig,
    pre_hook: Optional[Callable[[Election], None]] = None,
    tick_hook: Optional[Callable[[Election, int], None]] = None,
) -> tuple[SimulationResult, SimulationMetrics]:
    """Run a scenario with optional hooks for customization."""
    election = Election(config)

    if pre_hook:
        pre_hook(election)

    for t in range(1, config.term_length + 1):
        if tick_hook:
            tick_hook(election, t)
        election.tick(t)

    result = SimulationResult(
        scenario_name=name,
        config=config,
        tick_results=election.tick_results,
    )

    # Add provenance if available
    if HAS_PROVENANCE:
        chain = ProvenanceChain(operation=f"simulation_{name}")
        chain.add_step("config", {
            "n_citizens": config.n_citizens,
            "n_politicians": config.n_politicians,
            "term_length": config.term_length,
            "power_model": config.power_model.value,
            "seed": config.seed,
        })
        chain.add_step("result", {
            "total_ticks": len(result.tick_results),
            "total_withdrawals": sum(len(tr.withdrawals) for tr in result.tick_results),
        })
        result.provenance = chain.finalize(output=f"scenario_{name}_complete")

    metrics = compute_metrics(result, election.politicians)
    result.metrics = {
        "promise_fulfillment_rate": metrics.promise_fulfillment_rate,
        "promise_broken_rate": metrics.promise_broken_rate,
        "total_withdrawals": metrics.total_withdrawals,
        "avg_final_satisfaction": metrics.avg_final_satisfaction,
        "effective_accountability": metrics.effective_accountability,
        "degressive_pressure_index": metrics.degressive_pressure_index,
        "peak_withdrawal_tick": metrics.peak_withdrawal_tick,
        "final_power_levels": metrics.final_power_levels,
    }

    return result, metrics


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def scenario_baseline(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """All politicians keep all promises. Control group."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 4,
    )
    return _run_scenario("baseline", config)


def scenario_single_breaker(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """One politician uses strategic minimum, rest keep promises."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
        ],
    )
    return _run_scenario("single_breaker", config)


def scenario_all_break(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """All politicians break promises equally."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[PoliticianBehavior.STRATEGIC_MIN] * 4,
    )
    return _run_scenario("all_break", config)


def scenario_strategic_minimum(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """All politicians only fulfill visible promises."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[PoliticianBehavior.STRATEGIC_MIN] * 4,
    )
    return _run_scenario("strategic_minimum", config)


def scenario_coordinated_attack(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """30% of citizens withdraw simultaneously at tick 24."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 4,
    )

    def tick_hook(election: Election, tick: int) -> None:
        if tick == 23:
            # Tank satisfaction of 30% of non-withdrawn citizens before tick 24
            # They will naturally withdraw during tick 24
            target = int(len(election.citizens) * 0.3)
            count = 0
            for c in election.citizens:
                if count >= target:
                    break
                if not c.has_withdrawn:
                    c.satisfaction = 0.0
                    count += 1

    return _run_scenario("coordinated_attack", config, tick_hook=tick_hook)


def scenario_populist_wave(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """1 populist vs. 3 promise keepers."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
        ],
    )
    return _run_scenario("populist_wave", config)


def scenario_coalition_dynamics(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """2 parties, coalition requires >50% combined power."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.THRESHOLD,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.STRATEGIC_MIN,
        ],
    )
    return _run_scenario("coalition_dynamics", config)


def scenario_adaptive_response(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """All politicians use ADAPTIVE behavior."""
    config = ElectionConfig(
        n_citizens=200,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[PoliticianBehavior.ADAPTIVE] * 4,
    )
    return _run_scenario("adaptive_response", config)


def scenario_power_model_comparison(
    seed: int = 42,
) -> dict[str, tuple[SimulationResult, SimulationMetrics]]:
    """Same scenario across all 4 power models."""
    results = {}
    for model in PowerModel:
        config = ElectionConfig(
            n_citizens=200,
            n_politicians=4,
            term_length=48,
            power_model=model,
            promises_per_politician=5,
            seed=seed,
            politician_behaviors=[
                PoliticianBehavior.STRATEGIC_MIN,
                PoliticianBehavior.PROMISE_KEEPER,
                PoliticianBehavior.PROMISE_KEEPER,
                PoliticianBehavior.PROMISE_KEEPER,
            ],
        )
        results[model.value] = _run_scenario(f"power_comparison_{model.value}", config)
    return results


def scenario_citizen_mix(seed: int = 42) -> tuple[SimulationResult, SimulationMetrics]:
    """Realistic citizen distribution with mixed politician strategies."""
    config = ElectionConfig(
        n_citizens=500,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution={
            CitizenBehavior.RATIONAL: 0.40,
            CitizenBehavior.LOYAL: 0.20,
            CitizenBehavior.VOLATILE: 0.15,
            CitizenBehavior.PEER_INFLUENCED: 0.15,
            CitizenBehavior.STRATEGIC: 0.05,
            CitizenBehavior.APATHETIC: 0.05,
        },
        politician_behaviors=[
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.FRONTLOADER,
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.ADAPTIVE,
        ],
    )
    return _run_scenario("citizen_mix", config)


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------

ALL_SCENARIOS: dict[str, Callable] = {
    "baseline": scenario_baseline,
    "single_breaker": scenario_single_breaker,
    "all_break": scenario_all_break,
    "strategic_minimum": scenario_strategic_minimum,
    "coordinated_attack": scenario_coordinated_attack,
    "populist_wave": scenario_populist_wave,
    "coalition_dynamics": scenario_coalition_dynamics,
    "adaptive_response": scenario_adaptive_response,
    "power_model_comparison": scenario_power_model_comparison,
    "citizen_mix": scenario_citizen_mix,
}
