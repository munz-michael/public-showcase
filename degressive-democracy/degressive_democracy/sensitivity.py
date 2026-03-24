"""Sensitivity Analysis: Which parameters drive the results?

Sweeps the 3 most critical configurable parameters:
1. BROKEN_PENALTY (citizen.py) — how hard broken promises hit satisfaction
2. PROGRESS_SCALING (citizen.py) — how much progress gap matters
3. withdrawal_threshold — when citizens decide to withdraw

Modifies module-level constants in citizen.py, runs scenarios, restores defaults.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import Generator

import degressive_democracy.citizen as citizen_module
from .models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
)
from .election import Election
from .metrics import SimulationMetrics, compute_metrics


@dataclass
class SensitivityPoint:
    """Result at one parameter value."""
    value: float
    total_withdrawals_mean: float
    total_withdrawals_std: float
    satisfaction_mean: float
    keeper_power_mean: float
    stratmin_power_mean: float
    populist_power_mean: float


@dataclass
class SensitivityResult:
    """Complete sensitivity analysis for one parameter."""
    param_name: str
    default_value: float
    points: list[SensitivityPoint]
    robust_findings: list[str] = field(default_factory=list)
    fragile_findings: list[str] = field(default_factory=list)


@contextlib.contextmanager
def _override_citizen_params(
    broken_penalty: float | None = None,
    progress_scaling: float | None = None,
) -> Generator[None, None, None]:
    """Temporarily override citizen.py module-level constants."""
    orig_bp = citizen_module.BROKEN_PENALTY
    orig_ps = citizen_module.PROGRESS_SCALING
    try:
        if broken_penalty is not None:
            citizen_module.BROKEN_PENALTY = broken_penalty
        if progress_scaling is not None:
            citizen_module.PROGRESS_SCALING = progress_scaling
        yield
    finally:
        citizen_module.BROKEN_PENALTY = orig_bp
        citizen_module.PROGRESS_SCALING = orig_ps


def _run_scenario(
    seed: int,
    n_citizens: int = 200,
    withdrawal_threshold_override: float | None = None,
) -> tuple[SimulationMetrics, dict[str, float]]:
    """Run a mixed-strategy scenario and return metrics + per-strategy power."""
    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.FRONTLOADER,
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.ADAPTIVE,
        ],
    )

    election = Election(config)

    # Override withdrawal thresholds if requested
    if withdrawal_threshold_override is not None:
        for c in election.citizens:
            if c.behavior != CitizenBehavior.APATHETIC:
                c.withdrawal_threshold = withdrawal_threshold_override + election.rng.uniform(-0.05, 0.05)

    for t in range(1, 49):
        election.tick(t)

    from .models import SimulationResult
    result = SimulationResult("sensitivity", config, election.tick_results)
    metrics = compute_metrics(result, election.politicians)

    powers = {p.behavior.value: p.power for p in election.politicians}
    return metrics, powers


def _aggregate(runs: list[tuple[SimulationMetrics, dict[str, float]]]) -> SensitivityPoint:
    """Aggregate results from multiple seeds."""
    n = len(runs)
    wds = [float(m.total_withdrawals) for m, _ in runs]
    sats = [m.avg_final_satisfaction for m, _ in runs]
    keepers = [p.get("promise_keeper", 0.0) for _, p in runs]
    strats = [p.get("strategic_minimum", 0.0) for _, p in runs]
    pops = [p.get("populist", 0.0) for _, p in runs]

    wd_mean = sum(wds) / n
    return SensitivityPoint(
        value=0,  # set by caller
        total_withdrawals_mean=wd_mean,
        total_withdrawals_std=(sum((x - wd_mean) ** 2 for x in wds) / n) ** 0.5,
        satisfaction_mean=sum(sats) / n,
        keeper_power_mean=sum(keepers) / n,
        stratmin_power_mean=sum(strats) / n,
        populist_power_mean=sum(pops) / n,
    )


def run_sensitivity(
    param_name: str,
    values: list[float],
    default_value: float,
    n_seeds: int = 5,
) -> SensitivityResult:
    """Run sensitivity analysis for one parameter."""
    points = []

    for val in values:
        runs = []
        for s in range(n_seeds):
            seed = 100 + s
            if param_name == "broken_penalty":
                with _override_citizen_params(broken_penalty=val):
                    runs.append(_run_scenario(seed))
            elif param_name == "progress_scaling":
                with _override_citizen_params(progress_scaling=val):
                    runs.append(_run_scenario(seed))
            elif param_name == "withdrawal_threshold":
                runs.append(_run_scenario(seed, withdrawal_threshold_override=val))
            else:
                runs.append(_run_scenario(seed))

        point = _aggregate(runs)
        point.value = val
        points.append(point)

    # Analyze robustness
    robust, fragile = _analyze_robustness(param_name, points)

    return SensitivityResult(
        param_name=param_name,
        default_value=default_value,
        points=points,
        robust_findings=robust,
        fragile_findings=fragile,
    )


def _analyze_robustness(
    param_name: str,
    points: list[SensitivityPoint],
) -> tuple[list[str], list[str]]:
    """Analyze which findings are robust vs fragile."""
    robust = []
    fragile = []

    # Finding: Populist always loses (power < 0.3)
    pop_always_low = all(p.populist_power_mean < 0.3 for p in points)
    if pop_always_low:
        robust.append("Populist elimination holds")
    else:
        vals = [f"{p.value:.2f}" for p in points if p.populist_power_mean >= 0.3]
        fragile.append(f"Populist survives at {param_name}={', '.join(vals)}")

    # Finding: Keeper >= StratMin
    keeper_dom = all(p.keeper_power_mean >= p.stratmin_power_mean - 0.05 for p in points)
    if keeper_dom:
        robust.append("Keeper >= StratMin holds")
    else:
        vals = [f"{p.value:.2f}" for p in points if p.keeper_power_mean < p.stratmin_power_mean - 0.05]
        fragile.append(f"StratMin beats Keeper at {param_name}={', '.join(vals)}")

    # Finding: Mechanism produces withdrawals
    active = [p for p in points if p.total_withdrawals_mean > 0]
    dead = [p for p in points if p.total_withdrawals_mean == 0]
    if len(dead) == 0:
        robust.append("Mechanism always active")
    elif len(dead) == len(points):
        fragile.append(f"Mechanism NEVER active across all {param_name} values")
    else:
        dead_vals = [f"{p.value:.2f}" for p in dead]
        fragile.append(f"Mechanism inactive at {param_name}={', '.join(dead_vals)}")

    return robust, fragile


def run_full_sensitivity(n_seeds: int = 5) -> dict[str, SensitivityResult]:
    """Run sensitivity analysis for all 3 critical parameters."""
    return {
        "broken_penalty": run_sensitivity(
            "broken_penalty",
            [0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
            default_value=0.3,
            n_seeds=n_seeds,
        ),
        "progress_scaling": run_sensitivity(
            "progress_scaling",
            [0.1, 0.2, 0.3, 0.5, 0.7, 1.0],
            default_value=0.5,
            n_seeds=n_seeds,
        ),
        "withdrawal_threshold": run_sensitivity(
            "withdrawal_threshold",
            [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
            default_value=0.4,
            n_seeds=n_seeds,
        ),
    }


def print_sensitivity_report(results: dict[str, SensitivityResult]) -> None:
    """Print sensitivity analysis report."""
    print("SENSITIVITY ANALYSIS")
    print("=" * 72)
    print()

    for name, sr in results.items():
        print(f"  Parameter: {sr.param_name} (default={sr.default_value})")
        print(f"  {'Value':>6} {'Withdrawals':>12} {'Satisfaction':>12} {'Keeper':>7} {'StratMin':>8} {'Populist':>8}")
        print("  " + "-" * 56)
        for p in sr.points:
            marker = " ◄" if abs(p.value - sr.default_value) < 0.001 else ""
            print(
                f"  {p.value:>6.2f} "
                f"{p.total_withdrawals_mean:>8.0f}±{p.total_withdrawals_std:>3.0f} "
                f"{p.satisfaction_mean:>11.2f} "
                f"{p.keeper_power_mean:>6.2f} "
                f"{p.stratmin_power_mean:>7.2f} "
                f"{p.populist_power_mean:>7.2f}{marker}"
            )

        if sr.robust_findings:
            print(f"  ✓ Robust: {'; '.join(sr.robust_findings)}")
        if sr.fragile_findings:
            print(f"  ⚠ Fragile: {'; '.join(sr.fragile_findings)}")
        print()

    # Summary
    all_robust = set()
    all_fragile = set()
    for sr in results.values():
        all_robust.update(sr.robust_findings)
        all_fragile.update(sr.fragile_findings)

    print("  SUMMARY")
    print("  " + "-" * 40)
    if all_robust:
        print("  Findings that hold across ALL sweeps:")
        for f in sorted(all_robust):
            print(f"    ✓ {f}")
    if all_fragile:
        print("  Findings that break:")
        for f in sorted(all_fragile):
            print(f"    ⚠ {f}")
