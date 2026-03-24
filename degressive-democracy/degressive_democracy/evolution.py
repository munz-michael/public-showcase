"""Multi-term evolution: politicians adapt strategies across election cycles.

Citizens retain memory of past terms. Politicians switch strategies
based on what worked (power retention). Natural selection of political
strategies over N election cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
    SimulationResult,
)
from .election import Election
from .metrics import SimulationMetrics, compute_metrics


ALL_STRATEGIES = list(PoliticianBehavior)


@dataclass
class TermRecord:
    """Record of one election term in the evolution."""
    term: int
    strategies: list[PoliticianBehavior]
    final_powers: dict[str, float]
    withdrawal_rates: dict[str, float]
    winner: str  # politician_id with highest power
    winner_strategy: PoliticianBehavior


@dataclass
class EvolutionResult:
    """Complete multi-term evolution result."""
    n_terms: int
    term_records: list[TermRecord]
    strategy_win_counts: dict[str, int]
    strategy_survival: dict[str, list[float]]  # strategy -> power per term
    convergence_strategy: Optional[str] = None  # what the system converges to


def run_evolution(
    n_terms: int = 10,
    n_citizens: int = 500,
    n_politicians: int = 5,
    term_length: int = 48,
    power_model: PowerModel = PowerModel.LINEAR,
    initial_strategies: Optional[list[PoliticianBehavior]] = None,
    seed: int = 42,
    memory_penalty: float = 0.1,
) -> EvolutionResult:
    """Run multi-term evolution.

    After each term:
    - The politician with the LOWEST power switches to the strategy
      of the politician with the HIGHEST power (imitation dynamics).
    - Citizens who withdrew in the previous term start the next term
      with reduced satisfaction (memory_penalty) for the same politician.
    """
    import random
    rng = random.Random(seed)

    if initial_strategies is None:
        initial_strategies = [
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.FRONTLOADER,
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.ADAPTIVE,
        ]

    current_strategies = list(initial_strategies)
    term_records: list[TermRecord] = []
    strategy_win_counts: dict[str, int] = {s.value: 0 for s in PoliticianBehavior}
    strategy_survival: dict[str, list[float]] = {s.value: [] for s in PoliticianBehavior}

    # Track citizen memory across terms
    citizen_memory: dict[str, float] = {}  # citizen_id -> satisfaction penalty

    for term in range(n_terms):
        config = ElectionConfig(
            n_citizens=n_citizens,
            n_politicians=n_politicians,
            term_length=term_length,
            power_model=power_model,
            promises_per_politician=5,
            seed=seed + term * 1000,
            politician_behaviors=current_strategies,
        )

        election = Election(config)

        # Apply citizen memory: reduce initial satisfaction for citizens
        # who withdrew in previous terms
        for citizen in election.citizens:
            penalty = citizen_memory.get(citizen.citizen_id, 0.0)
            if penalty > 0:
                citizen.satisfaction = max(0.3, 1.0 - penalty)

        # Run the term
        for t in range(1, term_length + 1):
            election.tick(t)

        # Record results
        powers = {p.politician_id: p.power for p in election.politicians}
        wr = {
            p.politician_id: 1.0 - (p.current_votes / p.initial_votes)
            if p.initial_votes > 0 else 0.0
            for p in election.politicians
        }

        winner_id = max(powers, key=powers.get)  # type: ignore
        winner_idx = int(winner_id.split("_")[1])
        winner_strategy = current_strategies[winner_idx]

        record = TermRecord(
            term=term,
            strategies=list(current_strategies),
            final_powers=powers,
            withdrawal_rates=wr,
            winner=winner_id,
            winner_strategy=winner_strategy,
        )
        term_records.append(record)
        strategy_win_counts[winner_strategy.value] += 1

        # Track per-strategy power
        for i, strat in enumerate(current_strategies):
            pol_id = f"pol_{i}"
            strategy_survival[strat.value].append(powers.get(pol_id, 0.0))

        # Update citizen memory: citizens who withdrew remember
        for citizen in election.citizens:
            if citizen.has_withdrawn:
                existing = citizen_memory.get(citizen.citizen_id, 0.0)
                citizen_memory[citizen.citizen_id] = min(existing + memory_penalty, 0.5)

        # Adaptation: loser imitates winner
        loser_id = min(powers, key=powers.get)  # type: ignore
        loser_idx = int(loser_id.split("_")[1])
        if powers[loser_id] < powers[winner_id]:
            current_strategies[loser_idx] = winner_strategy

    # Detect convergence
    final_strategies = set(current_strategies)
    convergence = None
    if len(final_strategies) == 1:
        convergence = list(final_strategies)[0].value

    # Check last 3 terms for dominant strategy
    if convergence is None and len(term_records) >= 3:
        last_winners = [r.winner_strategy.value for r in term_records[-3:]]
        if len(set(last_winners)) == 1:
            convergence = last_winners[0]

    return EvolutionResult(
        n_terms=n_terms,
        term_records=term_records,
        strategy_win_counts=strategy_win_counts,
        strategy_survival=strategy_survival,
        convergence_strategy=convergence,
    )


def print_evolution_report(result: EvolutionResult) -> None:
    """Print evolution results."""
    print(f"MULTI-TERM EVOLUTION ({result.n_terms} terms)")
    print("-" * 60)

    print(f"  {'Term':<6} {'Winner':<22} {'Strategies'}")
    print("  " + "-" * 54)
    for r in result.term_records:
        strats = ", ".join(s.value[:4] for s in r.strategies)
        powers = " ".join(f"{p:.2f}" for p in r.final_powers.values())
        print(f"  {r.term:<6} {r.winner_strategy.value:<22} [{strats}]")

    print()
    print("  Strategy Win Counts:")
    for strat, count in sorted(result.strategy_win_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            bar = "█" * count
            print(f"    {strat:<22} {bar} ({count})")

    if result.convergence_strategy:
        print(f"\n  ► System converges to: {result.convergence_strategy}")
    else:
        print(f"\n  ► No convergence after {result.n_terms} terms")
