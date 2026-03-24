"""Empirical validation: Can the simulation reproduce real political dynamics?

Backtesting against known German political data:

1. Merkel IV (2018-2021): SPD fell from 20.5% to ~15% (Sonntagsfrage)
2. Populist rise: AfD grew from 12.6% (2017) to ~10-13% (fluctuation)
3. Coalition dynamics: CDU/SPD Groko with declining support

We model this by:
- Mapping SPD satisfaction decline to our satisfaction curve
- Testing if our model reproduces the ~25% support loss over 3 years
- Checking if the simulation's withdrawal pattern matches Sonntagsfrage volatility

Data source: Infratest dimap Sonntagsfrage (publicly available aggregates)
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
from .metrics import compute_metrics
from .models import SimulationResult


# ---------------------------------------------------------------------------
# Real data: Sonntagsfrage approximations (Infratest dimap)
# ---------------------------------------------------------------------------

@dataclass
class RealDataPoint:
    """A real-world political data point for validation."""
    month: int          # months since election
    party: str
    support_pct: float  # Sonntagsfrage %
    source: str = "Infratest dimap"


# Merkel IV: March 2018 (election Sep 2017) to Sep 2021
# SPD entered coalition at ~20.5%, dropped to ~15% by mid-2019, then recovered to ~25% for 2021 election
# CDU: started ~33%, dropped to ~26% by mid-2021
MERKEL_IV_SPD = [
    RealDataPoint(0, "SPD", 20.5, "BT2017 result"),
    RealDataPoint(3, "SPD", 18.0, "Sonntagsfrage ~Jan 2018"),
    RealDataPoint(6, "SPD", 17.0, "Sonntagsfrage ~Apr 2018"),
    RealDataPoint(12, "SPD", 15.0, "Sonntagsfrage ~Oct 2018"),
    RealDataPoint(18, "SPD", 13.5, "Sonntagsfrage ~Apr 2019"),
    RealDataPoint(24, "SPD", 12.5, "Sonntagsfrage ~Oct 2019 (Tiefpunkt)"),
    RealDataPoint(30, "SPD", 15.0, "Sonntagsfrage ~Apr 2020 (Covid-Boost)"),
    RealDataPoint(36, "SPD", 16.0, "Sonntagsfrage ~Oct 2020"),
    RealDataPoint(42, "SPD", 18.0, "Sonntagsfrage ~Apr 2021"),
    RealDataPoint(48, "SPD", 25.7, "BT2021 result (Scholz-Effekt)"),
]

MERKEL_IV_CDU = [
    RealDataPoint(0, "CDU", 32.9, "BT2017 result"),
    RealDataPoint(6, "CDU", 31.0, "Sonntagsfrage ~Apr 2018"),
    RealDataPoint(12, "CDU", 28.0, "Sonntagsfrage ~Oct 2018"),
    RealDataPoint(18, "CDU", 27.0, "Sonntagsfrage ~Apr 2019"),
    RealDataPoint(24, "CDU", 26.0, "Sonntagsfrage ~Oct 2019"),
    RealDataPoint(30, "CDU", 37.0, "Sonntagsfrage ~Apr 2020 (Merkel Covid-Boost)"),
    RealDataPoint(36, "CDU", 36.0, "Sonntagsfrage ~Oct 2020"),
    RealDataPoint(42, "CDU", 28.0, "Sonntagsfrage ~Apr 2021 (Laschet-Effekt)"),
    RealDataPoint(48, "CDU", 24.1, "BT2021 result"),
]


# ---------------------------------------------------------------------------
# Validation: Map simulation to real data
# ---------------------------------------------------------------------------

@dataclass
class ValidationPoint:
    """Comparison of simulated vs real data at one point in time."""
    month: int
    real_support: float      # Sonntagsfrage %
    sim_power: float         # Simulation power (0-1)
    sim_support_mapped: float  # power mapped to % for comparison
    error: float             # absolute difference in %


@dataclass
class EmpiricalValidation:
    """Complete validation result."""
    party: str
    scenario: str
    points: list[ValidationPoint]
    mae: float  # Mean Absolute Error in percentage points
    max_error: float
    correlation: float  # Pearson between real and simulated
    qualitative_match: bool  # Does the overall trend match?


def _map_power_to_support(power: float, initial_pct: float) -> float:
    """Map simulation power (0-1) to support percentage.

    Simple linear mapping: power 1.0 = initial_pct, power 0.0 = 0%.
    """
    return power * initial_pct


def _pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    vx = sum((xi - mx) ** 2 for xi in x)
    vy = sum((yi - my) ** 2 for yi in y)
    d = (vx * vy) ** 0.5
    return cov / d if d > 0 else 0.0


def validate_against_merkel_iv(seed: int = 42) -> dict[str, EmpiricalValidation]:
    """Run simulation calibrated to Merkel IV and compare with Sonntagsfrage.

    Maps:
    - CDU/CSU → STRATEGIC_MIN (Regierungspartei, Koalitionskompromisse)
    - SPD → ADAPTIVE (reagiert auf Druck, Junior-Partner)
    - Grüne → PROMISE_KEEPER (Opposition, will Regierung werden)
    - AfD → POPULIST
    - FDP → FRONTLOADER (Nischenthemen)
    """
    config = ElectionConfig(
        n_citizens=500,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution={
            CitizenBehavior.RATIONAL: 0.30,
            CitizenBehavior.LOYAL: 0.20,
            CitizenBehavior.VOLATILE: 0.10,
            CitizenBehavior.PEER_INFLUENCED: 0.10,
            CitizenBehavior.STRATEGIC: 0.05,
            CitizenBehavior.APATHETIC: 0.25,
        },
        politician_behaviors=[
            PoliticianBehavior.STRATEGIC_MIN,    # CDU — Groko-Kompromisse
            PoliticianBehavior.ADAPTIVE,         # SPD — Junior-Partner
            PoliticianBehavior.PROMISE_KEEPER,   # Grüne
            PoliticianBehavior.POPULIST,         # AfD
            PoliticianBehavior.FRONTLOADER,      # FDP
        ],
    )

    election = Election(config)

    # Scale visibility to German level (not all promises perfectly visible)
    from .models import Promise
    for pol in election.politicians:
        new_promises = []
        for p in pol.promises:
            new_promises.append(Promise(
                promise_id=p.promise_id,
                category=p.category,
                description=p.description,
                difficulty=p.difficulty,
                visibility=max(0.1, min(1.0, p.visibility * 0.8)),
                deadline_tick=p.deadline_tick,
            ))
        pol.promises = new_promises

    # Use Prospect Theory satisfaction (losses hurt 2.25x more — more realistic)
    import degressive_democracy.citizen as _cmod
    orig_bp = _cmod.BROKEN_PENALTY
    orig_ps = _cmod.PROGRESS_SCALING
    _cmod.BROKEN_PENALTY = 0.3 * 2.25  # Prospect Theory loss aversion
    _cmod.PROGRESS_SCALING = 0.7       # Stronger reaction to progress gaps

    # Collect power per tick
    power_history: dict[str, list[float]] = {f"pol_{i}": [] for i in range(5)}

    for t in range(1, 49):
        election.tick(t)
        for pol in election.politicians:
            power_history[pol.politician_id].append(pol.power)

    # Restore defaults
    _cmod.BROKEN_PENALTY = orig_bp
    _cmod.PROGRESS_SCALING = orig_ps

    # Map to parties
    party_map = {
        "pol_0": ("CDU", MERKEL_IV_CDU, 32.9),
        "pol_1": ("SPD", MERKEL_IV_SPD, 20.5),
    }

    results = {}
    for pol_id, (party_name, real_data, initial_pct) in party_map.items():
        points = []
        for rdp in real_data:
            month = rdp.month
            if month == 0:
                sim_power = 1.0
            elif month <= 48:
                sim_power = power_history[pol_id][month - 1]
            else:
                sim_power = power_history[pol_id][-1]

            sim_support = _map_power_to_support(sim_power, initial_pct)
            error = abs(rdp.support_pct - sim_support)
            points.append(ValidationPoint(
                month=month,
                real_support=rdp.support_pct,
                sim_power=sim_power,
                sim_support_mapped=round(sim_support, 1),
                error=round(error, 1),
            ))

        real_values = [p.real_support for p in points]
        sim_values = [p.sim_support_mapped for p in points]
        mae = sum(p.error for p in points) / len(points)
        max_err = max(p.error for p in points)
        corr = _pearson(real_values, sim_values)

        # Qualitative: does the trend direction match?
        real_trend = real_values[-1] - real_values[0]  # positive = gained
        sim_trend = sim_values[-1] - sim_values[0]
        qual_match = (real_trend > 0) == (sim_trend > 0) or abs(real_trend) < 2

        results[party_name] = EmpiricalValidation(
            party=party_name,
            scenario="merkel_iv",
            points=points,
            mae=round(mae, 1),
            max_error=round(max_err, 1),
            correlation=round(corr, 3),
            qualitative_match=qual_match,
        )

    return results


def print_empirical_report(results: dict[str, EmpiricalValidation]) -> None:
    """Print empirical validation report."""
    print("EMPIRISCHE VALIDIERUNG: Simulation vs. Sonntagsfrage (Merkel IV)")
    print("=" * 72)
    print()
    print("  Mapping: CDU→StratMin, SPD→Adaptive, Gruene→Keeper, AfD→Populist, FDP→Frontloader")
    print()

    for party, ev in results.items():
        print(f"  {party}:")
        print(f"  {'Monat':>6} {'Real %':>7} {'Sim %':>7} {'Fehler':>7}")
        print("  " + "-" * 30)
        for p in ev.points:
            marker = " ◄" if p.error > 5 else ""
            print(f"  {p.month:>6} {p.real_support:>6.1f} {p.sim_support_mapped:>6.1f} {p.error:>6.1f}{marker}")

        print(f"  MAE: {ev.mae:.1f} Prozentpunkte | Max: {ev.max_error:.1f} | Korrelation: {ev.correlation:.3f}")
        print(f"  Trend-Match: {'JA' if ev.qualitative_match else 'NEIN'}")
        print()

    # Overall assessment
    all_parties = list(results.values())
    avg_mae = sum(ev.mae for ev in all_parties) / len(all_parties)
    all_qual = all(ev.qualitative_match for ev in all_parties)

    print("  GESAMTBEWERTUNG:")
    print(f"  Durchschnittlicher MAE: {avg_mae:.1f} Prozentpunkte")
    if avg_mae < 3:
        print("  ✓ SEHR GUT — Simulation reproduziert reale Dynamik quantitativ")
    elif avg_mae < 6:
        print("  ~ AKZEPTABEL — Simulation erfasst qualitative Trends")
    else:
        print("  ⚠ SCHWACH — Simulation weicht erheblich von Realdaten ab")

    if all_qual:
        print("  ✓ Qualitative Trends stimmen ueberein")
    else:
        failing = [ev.party for ev in all_parties if not ev.qualitative_match]
        print(f"  ⚠ Qualitative Trends passen nicht fuer: {', '.join(failing)}")

    print()
    print("  LIMITATIONEN:")
    print("  - Sonntagsfrage ≠ Stimmenentzug (Umfrage ist reversibel, Entzug nicht)")
    print("  - Kein Kandidaten-Effekt modelliert (Scholz-Effekt 2021)")
    print("  - Keine externen Schocks (Covid) im Basis-Szenario")
    print("  - Lineares Power-Mapping ist vereinfacht")
