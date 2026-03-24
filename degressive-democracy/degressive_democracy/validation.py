"""Cross-validation: game theory predictions vs. simulation results.

Bridges the analytical model (game_theory.py) with the empirical model
(election.py) to verify whether Nash predictions hold in practice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
)
from .election import Election
from .metrics import SimulationMetrics, compute_metrics
from .game_theory import (
    DegressivePayoffParams,
    check_nash_equilibrium,
)


@dataclass
class ValidationResult:
    """Result of cross-validating game theory vs. simulation."""
    nash_predicts_keeper: bool
    simulation_confirms: bool
    match: bool

    # Per-strategy empirical data
    strategy_results: dict[str, StrategyEmpirical] = field(default_factory=dict)

    # Discrepancies
    discrepancies: list[str] = field(default_factory=list)


@dataclass
class StrategyEmpirical:
    """Empirical results for one politician strategy from simulation."""
    strategy: str
    final_power: float
    withdrawal_rate: float
    promise_fulfillment: float
    avg_citizen_satisfaction: float


def validate_nash(
    n_citizens: int = 500,
    term_length: int = 48,
    power_model: PowerModel = PowerModel.LINEAR,
    seed: int = 42,
    n_runs: int = 5,
) -> ValidationResult:
    """Run simulations to verify game theory Nash prediction.

    Runs a tournament: each politician strategy competes against
    PROMISE_KEEPER opponents. The strategy that retains the most
    power is the empirical dominant strategy.
    """
    # 1. Get game theory prediction
    params = DegressivePayoffParams(
        initial_votes=n_citizens // 5,  # 5 politicians
        term_ticks=term_length,
        power_model=power_model,
    )
    nash = check_nash_equilibrium(params)

    # 2. Run simulation tournament
    strategies = [
        PoliticianBehavior.PROMISE_KEEPER,
        PoliticianBehavior.STRATEGIC_MIN,
        PoliticianBehavior.FRONTLOADER,
        PoliticianBehavior.POPULIST,
        PoliticianBehavior.ADAPTIVE,
    ]

    strategy_results: dict[str, StrategyEmpirical] = {}

    for test_strategy in strategies:
        # Put test_strategy as pol_0, rest are PROMISE_KEEPER
        behaviors = [test_strategy] + [PoliticianBehavior.PROMISE_KEEPER] * 4

        # Run multiple seeds and average
        total_power = 0.0
        total_wr = 0.0
        total_fulfillment = 0.0
        total_sat = 0.0

        for run in range(n_runs):
            config = ElectionConfig(
                n_citizens=n_citizens,
                n_politicians=5,
                term_length=term_length,
                power_model=power_model,
                promises_per_politician=5,
                seed=seed + run,
                politician_behaviors=behaviors,
            )
            election = Election(config)
            result = election.run()
            metrics = compute_metrics(result, election.politicians)

            pol_0 = election.politicians[0]
            total_power += pol_0.power
            total_wr += 1.0 - (pol_0.current_votes / pol_0.initial_votes) if pol_0.initial_votes > 0 else 0.0

            # Promise fulfillment for pol_0
            fulfilled = sum(1 for ps in pol_0.promise_states.values() if ps.progress >= 1.0)
            total_fulfillment += fulfilled / len(pol_0.promise_states) if pol_0.promise_states else 0.0

            # Satisfaction of pol_0's citizens
            pol_citizens = [c for c in election.citizens if c.politician_id == pol_0.politician_id]
            if pol_citizens:
                total_sat += sum(c.satisfaction for c in pol_citizens) / len(pol_citizens)

        strategy_results[test_strategy.value] = StrategyEmpirical(
            strategy=test_strategy.value,
            final_power=total_power / n_runs,
            withdrawal_rate=total_wr / n_runs,
            promise_fulfillment=total_fulfillment / n_runs,
            avg_citizen_satisfaction=total_sat / n_runs,
        )

    # 3. Determine empirical winner
    empirical_best = max(strategy_results.values(), key=lambda s: s.final_power)
    simulation_confirms_keeper = empirical_best.strategy == "promise_keeper"

    # 4. Identify discrepancies
    discrepancies = []

    if nash.is_nash and not simulation_confirms_keeper:
        discrepancies.append(
            f"Nash predicts keeper dominates, but simulation shows "
            f"{empirical_best.strategy} retains more power "
            f"({empirical_best.final_power:.2f} vs "
            f"{strategy_results['promise_keeper'].final_power:.2f})"
        )

    if not nash.is_nash and simulation_confirms_keeper:
        discrepancies.append(
            "Nash predicts keeper is NOT dominant, but simulation confirms keeper wins"
        )

    # Check if strategic_min exploits information asymmetry
    keeper = strategy_results.get("promise_keeper")
    strat_min = strategy_results.get("strategic_minimum")
    if keeper and strat_min:
        power_gap = keeper.final_power - strat_min.final_power
        if power_gap < 0.05:
            discrepancies.append(
                f"Strategic minimum nearly matches keeper "
                f"(power gap: {power_gap:.3f}). "
                f"Information asymmetry shields broken promises."
            )

    return ValidationResult(
        nash_predicts_keeper=nash.is_nash,
        simulation_confirms=simulation_confirms_keeper,
        match=nash.is_nash == simulation_confirms_keeper,
        strategy_results=strategy_results,
        discrepancies=discrepancies,
    )


def print_validation_report(result: ValidationResult) -> None:
    """Print a human-readable validation report."""
    print("CROSS-VALIDATION: Game Theory vs. Simulation")
    print("-" * 60)

    match_str = "✓ MATCH" if result.match else "✗ MISMATCH"
    print(f"  Game Theory predicts keeper dominant: {result.nash_predicts_keeper}")
    print(f"  Simulation confirms:                  {result.simulation_confirms}")
    print(f"  Result: {match_str}")
    print()

    print("  Strategy Tournament (5 runs avg):")
    print(f"  {'Strategy':<20} {'Power':>6} {'WR%':>6} {'Fulfilled':>9} {'Satisfaction':>12}")
    print("  " + "-" * 56)
    for s in sorted(result.strategy_results.values(), key=lambda x: -x.final_power):
        marker = " ◄" if s.final_power == max(r.final_power for r in result.strategy_results.values()) else ""
        print(
            f"  {s.strategy:<20} {s.final_power:>5.2f} {s.withdrawal_rate * 100:>5.1f}% "
            f"{s.promise_fulfillment * 100:>8.0f}%  {s.avg_citizen_satisfaction:>11.2f}{marker}"
        )

    if result.discrepancies:
        print()
        print("  Discrepancies:")
        for d in result.discrepancies:
            print(f"    ⚠ {d}")
