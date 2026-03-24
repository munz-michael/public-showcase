"""Reversibility simulation: What if citizens can give their vote back once?

Variant D: Withdraw once, return once, then permanent.
- Action 1: Withdraw (reversible)
- Action 2: Return (if politician improves)
- Action 3: Withdraw again (permanent, irreversible)

Tests whether reversibility improves or weakens the mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import (
    CitizenBehavior,
    CitizenState,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
    PromiseStatus,
    SimulationResult,
)
from .election import Election
from .citizen import update_satisfaction
from .politician import allocate_effort, update_power
from .metrics import SimulationMetrics, compute_metrics


@dataclass
class ReversibleCitizenState:
    """Extended citizen state tracking withdrawal/return/permanent cycle."""
    citizen_id: str
    politician_id: str
    phase: str = "active"  # active → withdrawn → returned → permanent
    # Phases:
    #   active: has vote, never withdrew
    #   withdrawn: withdrew once (can return)
    #   returned: gave vote back (can withdraw permanently)
    #   permanent: withdrew permanently (irreversible)
    satisfaction_at_withdrawal: float = 0.0
    withdrawal_tick: Optional[int] = None
    return_tick: Optional[int] = None
    permanent_tick: Optional[int] = None


def run_reversible_scenario(
    seed: int = 42,
    n_citizens: int = 300,
    behaviors: list | None = None,
    return_threshold: float = 0.7,  # satisfaction needed to return vote
) -> tuple[SimulationResult, SimulationMetrics, dict]:
    """Run simulation with Variant D reversibility.

    Args:
        return_threshold: If satisfaction rises above this after withdrawal,
                         citizen gives vote back.
    """
    if behaviors is None:
        behaviors = [
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.ADAPTIVE,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.FRONTLOADER,
        ]

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

    # Build reversible state tracker
    rev_states: dict[str, ReversibleCitizenState] = {}
    for c in election.citizens:
        rev_states[c.citizen_id] = ReversibleCitizenState(
            citizen_id=c.citizen_id,
            politician_id=c.politician_id,
        )

    # Stats
    total_withdrawals = 0
    total_returns = 0
    total_permanent = 0
    withdrawal_curve = []
    return_curve = []

    for t in range(1, 49):
        # 1. Politicians allocate effort
        for pol in election.politicians:
            wr = 1.0 - (pol.current_votes / pol.initial_votes) if pol.initial_votes > 0 else 0.0
            allocate_effort(pol, tick=t, term_length=48, withdrawal_rate=wr)

        # 2. Update satisfaction
        for citizen in election.citizens:
            pol = next((p for p in election.politicians if p.politician_id == citizen.politician_id), None)
            if pol:
                update_satisfaction(citizen, pol, tick=t, term_length=48)

        # 3. Reversible withdrawal/return logic
        tick_withdrawals = 0
        tick_returns = 0

        for citizen in election.citizens:
            rs = rev_states[citizen.citizen_id]

            if citizen.behavior == CitizenBehavior.APATHETIC:
                continue

            threshold = citizen.withdrawal_threshold
            if citizen.behavior == CitizenBehavior.LOYAL:
                threshold = min(threshold, 0.2)
            elif citizen.behavior == CitizenBehavior.VOLATILE:
                threshold = max(threshold, 0.6)
            elif citizen.behavior == CitizenBehavior.STRATEGIC:
                if t < 48 * 0.6:
                    continue

            if rs.phase == "active":
                # Can withdraw (reversible)
                if citizen.satisfaction < threshold:
                    rs.phase = "withdrawn"
                    rs.withdrawal_tick = t
                    rs.satisfaction_at_withdrawal = citizen.satisfaction
                    citizen.has_withdrawn = True
                    citizen.withdrawn_tick = t
                    pol = next((p for p in election.politicians if p.politician_id == citizen.politician_id), None)
                    if pol:
                        pol.current_votes -= 1
                    tick_withdrawals += 1

            elif rs.phase == "withdrawn":
                # Can return vote if satisfaction improved
                if citizen.satisfaction > return_threshold:
                    rs.phase = "returned"
                    rs.return_tick = t
                    citizen.has_withdrawn = False
                    citizen.withdrawn_tick = None
                    pol = next((p for p in election.politicians if p.politician_id == citizen.politician_id), None)
                    if pol:
                        pol.current_votes += 1
                    tick_returns += 1

            elif rs.phase == "returned":
                # Can withdraw permanently
                if citizen.satisfaction < threshold:
                    rs.phase = "permanent"
                    rs.permanent_tick = t
                    citizen.has_withdrawn = True
                    citizen.withdrawn_tick = t
                    pol = next((p for p in election.politicians if p.politician_id == citizen.politician_id), None)
                    if pol:
                        pol.current_votes -= 1
                    tick_withdrawals += 1

            # permanent: nothing more can happen

        total_withdrawals += tick_withdrawals
        total_returns += tick_returns
        total_permanent += sum(1 for rs in rev_states.values() if rs.phase == "permanent" and rs.permanent_tick == t)

        # 4. Update power
        for pol in election.politicians:
            update_power(pol, config.power_model)

        # Track curves
        currently_withdrawn = sum(1 for c in election.citizens if c.has_withdrawn)
        withdrawal_curve.append(currently_withdrawn)
        return_curve.append(tick_returns)

    # Build result
    result = SimulationResult("reversible_d", config, election.tick_results)
    metrics = compute_metrics(result, election.politicians)

    # Phase distribution
    phases = {"active": 0, "withdrawn": 0, "returned": 0, "permanent": 0}
    for rs in rev_states.values():
        phases[rs.phase] += 1

    analysis = {
        "total_withdrawals": total_withdrawals,
        "total_returns": total_returns,
        "total_permanent": total_permanent,
        "final_withdrawn": sum(1 for c in election.citizens if c.has_withdrawn),
        "phases": phases,
        "power": {p.politician_id: round(p.power, 3) for p in election.politicians},
        "behaviors": {p.politician_id: p.behavior.value for p in election.politicians},
        "satisfaction": round(sum(c.satisfaction for c in election.citizens) / len(election.citizens), 3),
        "withdrawal_curve": withdrawal_curve,
        "return_curve": return_curve,
    }

    return result, metrics, analysis


def run_reversibility_comparison(seed: int = 42) -> dict:
    """Compare irreversible (current) vs reversible (Variant D)."""
    # Irreversible (standard)
    from .simulation import scenario_citizen_mix
    _, irrev_metrics = scenario_citizen_mix(seed=seed)

    # Reversible (Variant D)
    _, _, rev_analysis = run_reversible_scenario(seed=seed)

    return {
        "irreversible": {
            "withdrawals": irrev_metrics.total_withdrawals,
            "satisfaction": irrev_metrics.avg_final_satisfaction,
            "power": irrev_metrics.final_power_levels,
        },
        "reversible": rev_analysis,
    }


def print_reversibility_report(comparison: dict) -> None:
    """Print comparison report."""
    irr = comparison["irreversible"]
    rev = comparison["reversible"]

    print("REVERSIBILITAET: Irreversibel vs. Variante D")
    print("=" * 72)
    print()
    print("  Variante D: Einmal entziehen, einmal zurueckgeben, dann endgueltig.")
    print()

    print(f"  {'Metrik':<30} {'Irreversibel':>14} {'Variante D':>14}")
    print("  " + "-" * 58)
    print(f"  {'Entzuege total':<30} {irr['withdrawals']:>14} {rev['total_withdrawals']:>14}")
    print(f"  {'Rueckgaben':<30} {'—':>14} {rev['total_returns']:>14}")
    print(f"  {'Endgueltige Entzuege':<30} {'—':>14} {rev['total_permanent']:>14}")
    print(f"  {'Aktuell entzogen (Tick 48)':<30} {irr['withdrawals']:>14} {rev['final_withdrawn']:>14}")
    print(f"  {'Zufriedenheit':<30} {irr['satisfaction']:>13.2f} {rev['satisfaction']:>13.3f}")

    print()
    print("  Phase-Verteilung (Variante D):")
    for phase, count in rev["phases"].items():
        bar = "█" * (count // 5) if count > 0 else ""
        print(f"    {phase:<12} {count:>4} {bar}")

    print()
    print("  Power pro Politiker (Variante D):")
    for pid, power in sorted(rev["power"].items()):
        behavior = rev["behaviors"].get(pid, "?")
        print(f"    {behavior:<22} {power:.2f}")

    print()
    # Verdict
    if rev["total_returns"] > 0:
        print(f"  ► {rev['total_returns']} Buerger haben ihre Stimme zurueckgegeben!")
        print("    → Reversibilitaet gibt Politikern eine zweite Chance.")
    if rev["total_permanent"] > 0:
        print(f"  ► {rev['total_permanent']} Buerger haben endgueltig entzogen (nach Rueckgabe).")
        print("    → Diese Buerger wurden zweimal enttaeuscht — staerkeres Signal.")
    if rev["final_withdrawn"] < irr["withdrawals"]:
        print(f"  ► WENIGER finale Entzuege ({rev['final_withdrawn']} vs {irr['withdrawals']})")
        print("    → Variante D ist milder aber gibt besseres Feedback.")
    elif rev["final_withdrawn"] > irr["withdrawals"]:
        print(f"  ► MEHR finale Entzuege ({rev['final_withdrawn']} vs {irr['withdrawals']})")
        print("    → Variante D fuehrt zu mehr Aktivitaet, nicht weniger.")
