"""Statistical robustness: run scenarios across multiple seeds.

Replaces single-seed anecdotes with confidence intervals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .models import SimulationResult
from .metrics import SimulationMetrics


@dataclass
class RobustMetric:
    """A metric computed across multiple seeds."""
    name: str
    values: list[float]
    mean: float = 0.0
    median: float = 0.0
    std: float = 0.0
    min: float = 0.0
    max: float = 0.0
    ci_low: float = 0.0   # 5th percentile
    ci_high: float = 0.0  # 95th percentile

    def __post_init__(self):
        if self.values:
            self._compute()

    def _compute(self):
        v = sorted(self.values)
        n = len(v)
        self.mean = sum(v) / n
        self.median = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
        self.min = v[0]
        self.max = v[-1]
        variance = sum((x - self.mean) ** 2 for x in v) / n
        self.std = variance ** 0.5
        self.ci_low = v[max(0, int(n * 0.05))]
        self.ci_high = v[min(n - 1, int(n * 0.95))]


@dataclass
class RobustResult:
    """Result of running a scenario across multiple seeds."""
    scenario_name: str
    n_seeds: int
    metrics: dict[str, RobustMetric] = field(default_factory=dict)


def run_robust(
    scenario_fn: Callable,
    n_seeds: int = 20,
    base_seed: int = 1,
    extract_fn: Callable | None = None,
) -> RobustResult:
    """Run a scenario function across multiple seeds.

    Args:
        scenario_fn: Function that takes seed=int and returns
                     (SimulationResult, SimulationMetrics) or
                     (SimulationResult, SimulationMetrics, dict)
        n_seeds: Number of different seeds to run
        base_seed: Starting seed (runs base_seed .. base_seed + n_seeds - 1)
        extract_fn: Optional function to extract custom metrics from result.
                    Receives (result, metrics) or (result, metrics, analysis),
                    returns dict[str, float].
    """
    raw: dict[str, list[float]] = {}

    for i in range(n_seeds):
        seed = base_seed + i
        out = scenario_fn(seed=seed)

        # Handle different return types
        if isinstance(out, tuple) and len(out) == 3:
            result, metrics, analysis = out
        elif isinstance(out, tuple) and len(out) == 2:
            result, metrics = out
            analysis = None
        else:
            continue

        # Standard metrics
        _collect(raw, "total_withdrawals", float(metrics.total_withdrawals))
        _collect(raw, "avg_final_satisfaction", metrics.avg_final_satisfaction)
        _collect(raw, "promise_fulfillment_rate", metrics.promise_fulfillment_rate)
        _collect(raw, "promise_broken_rate", metrics.promise_broken_rate)
        _collect(raw, "effective_accountability", metrics.effective_accountability)
        _collect(raw, "degressive_pressure_index", metrics.degressive_pressure_index)

        # Power levels
        if metrics.final_power_levels:
            avg_power = sum(metrics.final_power_levels.values()) / len(metrics.final_power_levels)
            _collect(raw, "avg_final_power", avg_power)
            min_power = min(metrics.final_power_levels.values())
            _collect(raw, "min_final_power", min_power)

        # Custom metrics from analysis dict
        if analysis and isinstance(analysis, dict):
            for k, v in analysis.items():
                if isinstance(v, (int, float)):
                    _collect(raw, f"custom_{k}", float(v))

        # Custom extractor
        if extract_fn:
            if analysis:
                custom = extract_fn(result, metrics, analysis)
            else:
                custom = extract_fn(result, metrics)
            if custom:
                for k, v in custom.items():
                    _collect(raw, k, v)

    # Build robust metrics
    name = getattr(scenario_fn, '__name__', 'unknown')
    robust = RobustResult(scenario_name=name, n_seeds=n_seeds)
    for metric_name, values in raw.items():
        robust.metrics[metric_name] = RobustMetric(name=metric_name, values=values)

    return robust


def _collect(raw: dict[str, list[float]], key: str, value: float) -> None:
    raw.setdefault(key, []).append(value)


def print_robust_report(result: RobustResult, top_n: int = 8) -> None:
    """Print a compact robust analysis report."""
    print(f"ROBUST ANALYSIS: {result.scenario_name} ({result.n_seeds} seeds)")
    print("-" * 72)
    print(f"  {'Metric':<28} {'Mean':>7} {'Median':>7} {'Std':>6} {'[5%':>6} {'95%]':>6}")
    print("  " + "-" * 62)

    # Show most important metrics first
    priority = [
        "total_withdrawals", "avg_final_satisfaction",
        "avg_final_power", "min_final_power",
        "effective_accountability", "promise_fulfillment_rate",
    ]
    shown = set()
    for key in priority:
        if key in result.metrics:
            m = result.metrics[key]
            _print_metric(m)
            shown.add(key)

    # Then custom metrics
    count = len(shown)
    for key, m in sorted(result.metrics.items()):
        if key not in shown and count < top_n:
            _print_metric(m)
            count += 1


def _print_metric(m: RobustMetric) -> None:
    name = m.name[:28]
    print(f"  {name:<28} {m.mean:>7.2f} {m.median:>7.2f} {m.std:>6.2f} {m.ci_low:>6.2f} {m.ci_high:>6.2f}")


# ---------------------------------------------------------------------------
# Convenience: robust comparison of key scenarios
# ---------------------------------------------------------------------------

def run_robust_comparison(n_seeds: int = 20) -> dict[str, RobustResult]:
    """Run the most important scenarios with statistical robustness."""
    from .simulation import scenario_baseline, scenario_citizen_mix, scenario_single_breaker
    from .germany import run_germany_scenario

    results = {}

    # Core scenarios
    results["baseline"] = run_robust(scenario_baseline, n_seeds=n_seeds)
    results["single_breaker"] = run_robust(scenario_single_breaker, n_seeds=n_seeds)
    results["citizen_mix"] = run_robust(scenario_citizen_mix, n_seeds=n_seeds)

    # Germany: opaque vs transparent (wrap TransparencyResult to tuple)
    def _germany_opaque(seed):
        r = run_germany_scenario("opaque", seed=seed, n_citizens=500)
        return r.result, r.metrics

    def _germany_transparent(seed):
        r = run_germany_scenario("transparent", seed=seed, n_citizens=500)
        return r.result, r.metrics

    results["germany_opaque"] = run_robust(_germany_opaque, n_seeds=n_seeds)
    results["germany_transparent"] = run_robust(_germany_transparent, n_seeds=n_seeds)

    return results


def print_robust_comparison(results: dict[str, RobustResult]) -> None:
    """Print compact comparison of robust results."""
    print("ROBUST COMPARISON (key metrics across seeds)")
    print("=" * 72)
    print()

    print(f"  {'Scenario':<22} {'Withdrawals':>11} {'Satisfaction':>12} {'Min Power':>9}")
    print(f"  {'':<22} {'mean±std':>11} {'mean±std':>12} {'mean±std':>9}")
    print("  " + "-" * 55)

    for name, r in results.items():
        wd = r.metrics.get("total_withdrawals")
        sat = r.metrics.get("avg_final_satisfaction")
        mp = r.metrics.get("min_final_power")
        wd_str = f"{wd.mean:.0f}±{wd.std:.0f}" if wd else "n/a"
        sat_str = f"{sat.mean:.2f}±{sat.std:.2f}" if sat else "n/a"
        mp_str = f"{mp.mean:.2f}±{mp.std:.2f}" if mp else "n/a"
        print(f"  {name:<22} {wd_str:>11} {sat_str:>12} {mp_str:>9}")

    print()

    # Key validation: does the transparency finding hold?
    opaque = results.get("germany_opaque")
    transparent = results.get("germany_transparent")
    if opaque and transparent:
        ow = opaque.metrics["total_withdrawals"]
        tw = transparent.metrics["total_withdrawals"]
        # Check if transparent ALWAYS has fewer withdrawals
        always_fewer = all(t < o for t, o in zip(
            sorted(tw.values), sorted(ow.values)
        ))
        print(f"  Transparency finding robust? ", end="")
        if tw.ci_high < ow.ci_low:
            print("✓ YES — no overlap in 90% confidence intervals")
        elif always_fewer:
            print("✓ YES — transparent always fewer withdrawals")
        else:
            print(f"⚠ MIXED — overlap in CI (opaque: {ow.ci_low:.0f}-{ow.ci_high:.0f}, transparent: {tw.ci_low:.0f}-{tw.ci_high:.0f})")
