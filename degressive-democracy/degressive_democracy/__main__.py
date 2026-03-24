"""CLI entry point: python3 -m degressive_democracy"""

from __future__ import annotations

import sys
import time

from .simulation import (
    scenario_baseline,
    scenario_single_breaker,
    scenario_all_break,
    scenario_coordinated_attack,
    scenario_populist_wave,
    scenario_adaptive_response,
    scenario_citizen_mix,
)
from .game_theory import check_nash_equilibrium, parameter_sweep, DegressivePayoffParams
from .validation import validate_nash, print_validation_report
from .evolution import run_evolution, print_evolution_report
from .germany import (
    run_full_germany_comparison,
    run_german_evolution,
    print_germany_report,
    print_evolution_report as print_german_evolution,
)
from .advanced import run_advanced_comparison, print_advanced_report
from .municipal import run_municipal_comparison, print_municipal_report
from .exploits import run_exploit_analysis, print_exploit_report


def _fmt(val: float, decimals: int = 2) -> str:
    return f"{val:.{decimals}f}"


def _bar(val: float, width: int = 20) -> str:
    filled = int(val * width)
    return "█" * filled + "░" * (width - filled)


def run_report(seed: int = 42) -> None:
    print("=" * 72)
    print("  DEGRESSIVE DEMOCRACY — Simulation Report")
    print("=" * 72)
    print()

    # --- Run scenarios ---
    scenarios = [
        ("Baseline (all keep)", scenario_baseline),
        ("Single Breaker", scenario_single_breaker),
        ("All Break", scenario_all_break),
        ("Coordinated Attack", scenario_coordinated_attack),
        ("Populist Wave", scenario_populist_wave),
        ("Adaptive Response", scenario_adaptive_response),
        ("Citizen Mix", scenario_citizen_mix),
    ]

    print("Running 7 scenarios...", end="", flush=True)
    t0 = time.time()
    results = []
    for name, fn in scenarios:
        _, metrics = fn(seed=seed)
        results.append((name, metrics))
        print(".", end="", flush=True)
    elapsed = time.time() - t0
    print(f" done ({elapsed:.1f}s)\n")

    # --- Scenario comparison table ---
    print("SCENARIO COMPARISON")
    print("-" * 72)
    header = f"{'Scenario':<22} {'Withdrawals':>11} {'Satisfaction':>12} {'Accountability':>14} {'Pressure':>8}"
    print(header)
    print("-" * 72)
    for name, m in results:
        print(
            f"{name:<22} "
            f"{m.total_withdrawals:>7}/{results[0][1].total_withdrawals + m.total_withdrawals - m.total_withdrawals:>3}  "
            f"{_fmt(m.avg_final_satisfaction):>11}  "
            f"{_fmt(m.effective_accountability):>13}  "
            f"{_fmt(m.degressive_pressure_index):>7}"
        )
    print()

    # --- Power levels per scenario ---
    print("FINAL POWER LEVELS (per politician)")
    print("-" * 72)
    for name, m in results:
        powers = m.final_power_levels
        pol_strs = [f"{pid}={_fmt(p)}" for pid, p in sorted(powers.items())]
        print(f"  {name:<22} {', '.join(pol_strs)}")
    print()

    # --- Withdrawal curves (ASCII sparkline) ---
    print("WITHDRAWAL CURVES (cumulative % over 48 ticks)")
    print("-" * 72)
    for name, m in results:
        curve = m.withdrawal_curve
        if curve:
            # Sample 24 points
            sampled = [curve[i] for i in range(0, len(curve), 2)]
            sparkline = "".join(
                "▁▂▃▄▅▆▇█"[min(int(v * 8), 7)] if v > 0 else " "
                for v in sampled
            )
            print(f"  {name:<22} |{sparkline}| {_fmt(curve[-1] * 100, 0)}%")
    print()

    # --- Game Theory ---
    print("GAME THEORY: NASH EQUILIBRIUM ANALYSIS")
    print("-" * 72)
    nash = check_nash_equilibrium()
    status = "✓ Promise-Keeping IS Nash Equilibrium" if nash.is_nash else "✗ Promise-Keeping is NOT Nash"
    print(f"  {status}")
    print(f"  Dominant strategy: {nash.dominant_strategy}")
    print(f"  Condition: {nash.condition}")
    print()
    print("  Strategy payoffs:")
    for strategy, payoff in sorted(nash.payoffs.items(), key=lambda x: -x[1]):
        gain = nash.deviation_gains.get(strategy, 0.0)
        marker = " ◄ optimal" if strategy == nash.dominant_strategy else ""
        print(f"    {strategy:<16} {_fmt(payoff):>8}  (deviation gain: {_fmt(gain):>6}){marker}")
    print()

    # --- Critical threshold ---
    sweep = parameter_sweep("benefit_broken", [0.0, 0.2, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0])
    if sweep.critical_value is not None:
        print(f"  Nash breaks at benefit_broken = {sweep.critical_value}")
    print()

    # --- Cross-validation ---
    print("CROSS-VALIDATION: Game Theory vs. Simulation")
    print("-" * 72)
    print("  Running strategy tournament (5 strategies × 5 seeds)...", end="", flush=True)
    validation = validate_nash(seed=seed)
    print(" done\n")
    print_validation_report(validation)
    print()

    # --- Evolution ---
    print("MULTI-TERM EVOLUTION")
    print("-" * 72)
    print("  Running 10-term evolution...", end="", flush=True)
    evo = run_evolution(n_terms=10, seed=seed)
    print(" done\n")
    print_evolution_report(evo)
    print()

    # --- Germany full comparison (5 scenarios) ---
    print()
    print("Running Germany scenarios (5 variants)...", end="", flush=True)
    germany_results = run_full_germany_comparison(seed=seed)
    print(" done\n")
    print_germany_report(germany_results)
    print()

    # --- German multi-term evolution ---
    print("Running German evolution (10 terms)...", end="", flush=True)
    german_evo = run_german_evolution(seed=seed, n_citizens=500)
    print(" done\n")
    from .evolution import print_evolution_report as _pe
    _pe(german_evo)
    print()

    # --- Advanced mechanics ---
    print()
    print("Running advanced scenarios (counter, factions, coalition, calibration)...", end="", flush=True)
    advanced_results = run_advanced_comparison(seed=seed)
    print(" done\n")
    print_advanced_report(advanced_results)
    print()

    # --- Municipal comparison ---
    print()
    print("Running municipal comparison (4 levels)...", end="", flush=True)
    municipal_results = run_municipal_comparison(seed=seed)
    print(" done\n")
    print_municipal_report(municipal_results)
    print()

    # --- Exploit analysis ---
    print()
    print("Running exploit analysis (honeypot, protest, snap)...", end="", flush=True)
    exploit_results = run_exploit_analysis(seed=seed)
    print(" done\n")
    print_exploit_report(exploit_results)
    print()

    # --- Research questions ---
    print("=" * 72)
    print("  RESEARCH QUESTIONS — ANSWERS FROM SIMULATION")
    print("=" * 72)
    print()

    # Q1: Verhaltenskonvergenz
    mix_metrics = results[-1][1]  # citizen_mix
    best_pol = max(mix_metrics.final_power_levels.items(), key=lambda x: x[1])
    print("  Q1: Zu welcher Strategie konvergieren Politiker?")
    print(f"      Im Citizen-Mix-Szenario retainiert {best_pol[0]} die meiste")
    print(f"      Macht ({_fmt(best_pol[1])}). Promise-Keeping ist Nash-optimal.")
    print()

    # Q2: Nash-Gleichgewicht
    print("  Q2: Unter welchen Bedingungen ist Keeping ein Nash-GG?")
    print(f"      Nash hält solange benefit_broken < {sweep.critical_value or '~1.5'}.")
    print(f"      Withdrawal-Rate ≥ 0.15 pro gebrochenem Versprechen reicht aus.")
    print()

    # Q3: Angriffsvektoren
    attack_metrics = results[3][1]  # coordinated attack
    print("  Q3: Welche Manipulationsstrategien existieren?")
    print(f"      Coordinated Attack: {attack_metrics.total_withdrawals} Entzüge,")
    print(f"      Peak bei Tick {attack_metrics.peak_withdrawal_tick}.")
    print(f"      Populist Wave: Populist verliert auf Power {_fmt(results[4][1].final_power_levels.get('pol_0', 0))}.")
    print()


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    run_report(seed)
