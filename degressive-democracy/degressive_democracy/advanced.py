"""Advanced mechanics: public counter, factions, parties, calibration.

Extends the core simulation with:
1. Public Withdrawal Counter — visible signal that influences citizen decisions
2. Citizen Factions — organized groups with coordinated withdrawal strategies
3. Party Layer — politicians belong to parties with coalition agreements
4. Calibration — empirical parameters from German political data
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .models import (
    CitizenBehavior,
    CitizenState,
    ElectionConfig,
    ExternalShock,
    PoliticianBehavior,
    PoliticianState,
    PowerModel,
    Promise,
    PromiseCategory,
    PromiseState,
    PromiseStatus,
    SimulationResult,
    TickResult,
)
from .election import Election
from .citizen import decide_withdrawal, execute_withdrawal, update_satisfaction
from .politician import allocate_effort, update_power
from .metrics import SimulationMetrics, compute_metrics


# ===================================================================
# 1. PUBLIC WITHDRAWAL COUNTER
# ===================================================================

@dataclass
class PublicCounterState:
    """Tracks publicly visible withdrawal counts per politician."""
    counts: dict[str, int] = field(default_factory=dict)  # pol_id -> withdrawal count
    rates: dict[str, float] = field(default_factory=dict)  # pol_id -> withdrawal rate
    trend: dict[str, float] = field(default_factory=dict)  # pol_id -> velocity (new per tick)


def apply_public_counter_effect(
    citizen: CitizenState,
    counter: PublicCounterState,
    sensitivity: float = 0.1,
) -> None:
    """Public counter influences citizen satisfaction.

    When citizens SEE that others are withdrawing, it lowers their
    own satisfaction — a visible signal of collective dissatisfaction.
    """
    rate = counter.rates.get(citizen.politician_id, 0.0)
    trend = counter.trend.get(citizen.politician_id, 0.0)

    if rate > 0.1:  # above 10% withdrawn — signal kicks in
        # Satisfaction penalty proportional to withdrawal rate
        signal_penalty = rate * sensitivity
        # Trend amplifies: accelerating withdrawals are scarier
        if trend > 5:
            signal_penalty *= 1.5
        citizen.satisfaction = max(0.0, citizen.satisfaction - signal_penalty)


# ===================================================================
# 2. CITIZEN FACTIONS
# ===================================================================

class FactionStrategy(Enum):
    """How a faction decides when to trigger coordinated withdrawal."""
    THRESHOLD = "threshold"          # withdraw when satisfaction < X
    TIMED = "timed"                  # withdraw at specific tick
    REACTIVE = "reactive"            # withdraw when counter shows > X% already gone
    OPPORTUNISTIC = "opportunistic"  # withdraw when politician power drops below X


@dataclass
class Faction:
    """An organized group of citizens with coordinated withdrawal."""
    faction_id: str
    member_ids: list[str]
    target_politician_id: str
    strategy: FactionStrategy
    trigger_value: float  # threshold/tick/rate/power depending on strategy
    activated: bool = False


def check_faction_trigger(
    faction: Faction,
    tick: int,
    counter: PublicCounterState,
    politician_power: float,
    avg_satisfaction: float,
) -> bool:
    """Check if a faction's trigger condition is met."""
    if faction.activated:
        return False

    if faction.strategy == FactionStrategy.THRESHOLD:
        return avg_satisfaction < faction.trigger_value
    elif faction.strategy == FactionStrategy.TIMED:
        return tick >= faction.trigger_value
    elif faction.strategy == FactionStrategy.REACTIVE:
        rate = counter.rates.get(faction.target_politician_id, 0.0)
        return rate > faction.trigger_value
    elif faction.strategy == FactionStrategy.OPPORTUNISTIC:
        return politician_power < faction.trigger_value
    return False


def activate_faction(
    faction: Faction,
    citizens: list[CitizenState],
    tick: int,
) -> list[str]:
    """Activate faction — all members withdraw simultaneously."""
    faction.activated = True
    withdrawn = []
    for citizen in citizens:
        if citizen.citizen_id in faction.member_ids and not citizen.has_withdrawn:
            execute_withdrawal(citizen, tick)
            withdrawn.append(citizen.citizen_id)
    return withdrawn


# ===================================================================
# 3. PARTY LAYER
# ===================================================================

@dataclass
class Party:
    """A political party that contains multiple politicians."""
    party_id: str
    name: str
    politician_ids: list[str]
    ideology: float = 0.5  # 0=left, 1=right (simplified)


@dataclass
class CoalitionAgreement:
    """A coalition agreement between parties."""
    party_ids: list[str]
    shared_promises: list[str]  # promise_ids that both parties committed to
    power_threshold: float = 0.5  # coalition collapses if combined power < this
    collapsed: bool = False


def check_coalition_health(
    agreement: CoalitionAgreement,
    politicians: list[PoliticianState],
) -> tuple[bool, float]:
    """Check if coalition still holds.

    Returns (is_healthy, combined_power).
    """
    combined_power = 0.0
    for pol in politicians:
        if pol.politician_id in agreement.party_ids:
            combined_power += pol.power

    is_healthy = combined_power >= agreement.power_threshold
    return is_healthy, combined_power


def collapse_coalition(
    agreement: CoalitionAgreement,
    politicians: list[PoliticianState],
) -> None:
    """When coalition collapses, shared promises become harder."""
    agreement.collapsed = True
    for pol in politicians:
        if pol.politician_id in agreement.party_ids:
            for ps in pol.promise_states.values():
                if ps.promise_id in agreement.shared_promises:
                    # Shared promises become much harder without coalition partner
                    ps.effective_difficulty = min(1.0, ps.effective_difficulty + 0.3)
                    ps.blame = max(0.0, ps.blame - 0.3)  # partial blame reduction


# ===================================================================
# 4. CALIBRATION (Politbarometer-Proxy)
# ===================================================================

@dataclass
class CalibrationParams:
    """Empirically calibrated parameters based on German political data.

    Sources:
    - Wahlbeteiligung BT2021: 76.6% (-> 23.4% apathisch)
    - Infratest dimap Sonntagsfrage Volatilität: ~3-5% pro Monat
    - Politbarometer Zufriedenheit: ~40-60% "zufrieden" during normal times
    - Forschungsgruppe Wahlen: ~15% Wechselwähler pro Wahl
    """
    # Citizen distribution (from Wahlforschung)
    apathetic_rate: float = 0.234      # BT2021 Nichtwähler
    loyal_rate: float = 0.20           # Stammwähler
    volatile_rate: float = 0.10        # Protestwähler
    rational_rate: float = 0.30        # Wechselwähler (sachbezogen)
    peer_influenced_rate: float = 0.116  # fills to 1.0
    strategic_rate: float = 0.05

    # Satisfaction dynamics (from Politbarometer)
    normal_satisfaction: float = 0.55   # typical "zufrieden mit Regierung"
    crisis_satisfaction: float = 0.30   # during crisis
    honeymoon_duration: int = 6         # ticks of high satisfaction after election

    # Withdrawal calibration (from Sonntagsfrage volatility)
    monthly_volatility: float = 0.04    # ~4% opinion change per month
    withdrawal_threshold_mean: float = 0.35  # calibrated to match ~15% Wechselwähler

    def to_citizen_distribution(self) -> dict[CitizenBehavior, float]:
        return {
            CitizenBehavior.APATHETIC: self.apathetic_rate,
            CitizenBehavior.LOYAL: self.loyal_rate,
            CitizenBehavior.VOLATILE: self.volatile_rate,
            CitizenBehavior.RATIONAL: self.rational_rate,
            CitizenBehavior.PEER_INFLUENCED: self.peer_influenced_rate,
            CitizenBehavior.STRATEGIC: self.strategic_rate,
        }


# ===================================================================
# ADVANCED ELECTION ENGINE
# ===================================================================

class AdvancedElection(Election):
    """Election with public counter, factions, parties, and calibration."""

    def __init__(
        self,
        config: ElectionConfig,
        factions: Optional[list[Faction]] = None,
        parties: Optional[list[Party]] = None,
        coalition: Optional[CoalitionAgreement] = None,
        enable_public_counter: bool = True,
        counter_sensitivity: float = 0.1,
        calibration: Optional[CalibrationParams] = None,
    ):
        super().__init__(config)
        self.factions = factions or []
        self.parties = parties or []
        self.coalition = coalition
        self.enable_public_counter = enable_public_counter
        self.counter_sensitivity = counter_sensitivity
        self.calibration = calibration
        self.counter = PublicCounterState()

        # Apply calibration to withdrawal thresholds
        if calibration:
            for citizen in self.citizens:
                citizen.withdrawal_threshold = (
                    calibration.withdrawal_threshold_mean
                    + self.rng.uniform(-0.1, 0.1)
                )

    def tick(self, t: int) -> TickResult:
        """Extended tick with advanced mechanics."""
        result = TickResult(tick=t)

        # 0. Apply external shocks
        self._apply_shocks(t, result)

        # 0b. Check coalition health
        if self.coalition and not self.coalition.collapsed:
            healthy, combined = check_coalition_health(self.coalition, self.politicians)
            if not healthy:
                collapse_coalition(self.coalition, self.politicians)
                result.events.append(
                    f"COALITION COLLAPSED: combined power {combined:.2f} < {self.coalition.power_threshold}"
                )

        # 1. Politicians allocate effort
        for pol in self.politicians:
            wr = self._withdrawal_rate(pol.politician_id)
            allocate_effort(pol, tick=t, term_length=self.config.term_length, withdrawal_rate=wr)

        # 2. Citizens observe and update satisfaction
        for citizen in self.citizens:
            pol = self._get_politician(citizen.politician_id)
            if pol:
                update_satisfaction(citizen, pol, tick=t, term_length=self.config.term_length)

        # 2b. Public counter effect on satisfaction
        if self.enable_public_counter:
            for citizen in self.citizens:
                if not citizen.has_withdrawn:
                    apply_public_counter_effect(citizen, self.counter, self.counter_sensitivity)

        # 3. Check faction triggers
        for faction in self.factions:
            if faction.activated:
                continue
            pol = self._get_politician(faction.target_politician_id)
            pol_power = pol.power if pol else 0.0
            faction_citizens = [c for c in self.citizens if c.citizen_id in faction.member_ids]
            avg_sat = (
                sum(c.satisfaction for c in faction_citizens) / len(faction_citizens)
                if faction_citizens else 1.0
            )

            if check_faction_trigger(faction, t, self.counter, pol_power, avg_sat):
                withdrawn_ids = activate_faction(faction, self.citizens, t)
                for cid in withdrawn_ids:
                    citizen = next((c for c in self.citizens if c.citizen_id == cid), None)
                    if citizen:
                        pol = self._get_politician(citizen.politician_id)
                        if pol:
                            pol.current_votes -= 1
                        result.withdrawals.append((cid, citizen.politician_id))
                result.events.append(
                    f"FACTION {faction.faction_id} activated: {len(withdrawn_ids)} withdrawals"
                )

        # 4. Individual citizen withdrawal decisions
        for citizen in self.citizens:
            if citizen.has_withdrawn:
                continue
            peer_rate = self._peer_withdrawal_rate(citizen)
            if decide_withdrawal(citizen, t, self.config.term_length, peer_rate):
                execute_withdrawal(citizen, t)
                pol = self._get_politician(citizen.politician_id)
                if pol:
                    pol.current_votes -= 1
                result.withdrawals.append((citizen.citizen_id, citizen.politician_id))

        # 5. Update power levels
        for pol in self.politicians:
            update_power(pol, self.config.power_model)
            result.power_levels[pol.politician_id] = pol.power
            result.withdrawal_rates[pol.politician_id] = self._withdrawal_rate(pol.politician_id)

        # 6. Update public counter
        self._update_counter(result)

        # 7. Collect metrics
        result.promise_updates = {
            pol.politician_id: list(pol.promise_states.values())
            for pol in self.politicians
        }
        satisfactions = [c.satisfaction for c in self.citizens]
        result.avg_satisfaction = sum(satisfactions) / len(satisfactions) if satisfactions else 0.0

        self.tick_results.append(result)
        return result

    def _update_counter(self, result: TickResult) -> None:
        """Update the public withdrawal counter after each tick."""
        for pol in self.politicians:
            pid = pol.politician_id
            withdrawn_this_tick = sum(1 for _, p in result.withdrawals if p == pid)
            prev_count = self.counter.counts.get(pid, 0)
            new_count = prev_count + withdrawn_this_tick
            self.counter.counts[pid] = new_count
            self.counter.rates[pid] = new_count / pol.initial_votes if pol.initial_votes > 0 else 0.0
            self.counter.trend[pid] = float(withdrawn_this_tick)


# ===================================================================
# SCENARIO RUNNERS
# ===================================================================

def scenario_public_counter(
    seed: int = 42,
    n_citizens: int = 500,
    sensitivity: float = 0.1,
) -> tuple[SimulationResult, SimulationMetrics]:
    """Compare with vs without public counter."""
    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.ADAPTIVE,
        ],
    )
    election = AdvancedElection(
        config,
        enable_public_counter=True,
        counter_sensitivity=sensitivity,
    )
    for t in range(1, 49):
        election.tick(t)
    result = SimulationResult("public_counter", config, election.tick_results)
    metrics = compute_metrics(result, election.politicians)
    return result, metrics


def scenario_faction_attack(
    seed: int = 42,
    n_citizens: int = 500,
    faction_size: float = 0.15,
    trigger_tick: int = 20,
) -> tuple[SimulationResult, SimulationMetrics]:
    """Organized faction withdraws at a coordinated time."""
    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.ADAPTIVE,
            PoliticianBehavior.FRONTLOADER,
        ],
    )

    election = AdvancedElection(config, enable_public_counter=True)

    # Create faction targeting pol_2 (strategic_min)
    target_pol = election.politicians[2]
    target_citizens = [
        c.citizen_id for c in election.citizens
        if c.politician_id == target_pol.politician_id
    ]
    faction_members = target_citizens[:int(len(target_citizens) * faction_size)]

    faction = Faction(
        faction_id="opposition_bloc",
        member_ids=faction_members,
        target_politician_id=target_pol.politician_id,
        strategy=FactionStrategy.TIMED,
        trigger_value=trigger_tick,
    )
    election.factions = [faction]

    for t in range(1, 49):
        election.tick(t)
    result = SimulationResult("faction_attack", config, election.tick_results)
    metrics = compute_metrics(result, election.politicians)
    return result, metrics


def scenario_coalition_government(
    seed: int = 42,
    n_citizens: int = 500,
) -> tuple[SimulationResult, SimulationMetrics]:
    """Two-party coalition that can collapse under pressure."""
    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=4,
        term_length=48,
        power_model=PowerModel.THRESHOLD,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=[
            PoliticianBehavior.PROMISE_KEEPER,   # Coalition A
            PoliticianBehavior.ADAPTIVE,         # Coalition A
            PoliticianBehavior.STRATEGIC_MIN,    # Opposition
            PoliticianBehavior.POPULIST,         # Opposition
        ],
    )

    election = AdvancedElection(config, enable_public_counter=True)

    # Coalition between pol_0 and pol_1
    # Shared promises: infrastructure and environmental (hard to deliver alone)
    shared = []
    for pol in election.politicians[:2]:
        for p in pol.promises:
            if p.category in (PromiseCategory.INFRASTRUCTURE, PromiseCategory.ENVIRONMENTAL):
                shared.append(p.promise_id)

    coalition = CoalitionAgreement(
        party_ids=["pol_0", "pol_1"],
        shared_promises=shared,
        power_threshold=1.0,  # both need to retain significant power
    )
    election.coalition = coalition

    for t in range(1, 49):
        election.tick(t)
    result = SimulationResult("coalition_gov", config, election.tick_results)
    metrics = compute_metrics(result, election.politicians)
    return result, metrics


def scenario_calibrated_germany(
    seed: int = 42,
    n_citizens: int = 1000,
) -> tuple[SimulationResult, SimulationMetrics]:
    """Germany with empirically calibrated parameters."""
    cal = CalibrationParams()

    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution=cal.to_citizen_distribution(),
        politician_behaviors=[
            PoliticianBehavior.STRATEGIC_MIN,    # Regierungspartei
            PoliticianBehavior.ADAPTIVE,         # Koalitionspartner
            PoliticianBehavior.PROMISE_KEEPER,   # Opposition Mitte
            PoliticianBehavior.POPULIST,         # Opposition Populist
            PoliticianBehavior.FRONTLOADER,      # Opposition Klein
        ],
    )

    election = AdvancedElection(
        config,
        enable_public_counter=True,
        counter_sensitivity=cal.monthly_volatility,
        calibration=cal,
    )

    for t in range(1, 49):
        election.tick(t)
    result = SimulationResult("calibrated_germany", config, election.tick_results)
    metrics = compute_metrics(result, election.politicians)
    return result, metrics


# ===================================================================
# COMPARISON REPORT
# ===================================================================

def run_advanced_comparison(seed: int = 42) -> dict[str, tuple[SimulationResult, SimulationMetrics]]:
    """Run all advanced scenarios and return results."""
    return {
        "public_counter": scenario_public_counter(seed=seed),
        "faction_attack": scenario_faction_attack(seed=seed),
        "coalition_gov": scenario_coalition_government(seed=seed),
        "calibrated_de": scenario_calibrated_germany(seed=seed),
    }


def print_advanced_report(results: dict[str, tuple[SimulationResult, SimulationMetrics]]) -> None:
    """Print comparison of advanced scenarios."""
    print("ADVANCED MECHANICS COMPARISON")
    print("=" * 72)
    print()
    print(f"  {'Scenario':<20} {'Withdrawals':>11} {'Satisfaction':>12} {'Accountability':>14}")
    print("  " + "-" * 59)
    for name, (result, metrics) in results.items():
        print(
            f"  {name:<20} "
            f"{metrics.total_withdrawals:>10} "
            f"{metrics.avg_final_satisfaction:>11.2f} "
            f"{metrics.effective_accountability:>13.2f}"
        )

    print()

    # Events
    for name, (result, metrics) in results.items():
        events = []
        for tr in result.tick_results:
            for e in tr.events:
                events.append(f"    Tick {tr.tick}: {e}")
        if events:
            print(f"  {name} events:")
            for e in events[:5]:  # max 5 events
                print(e)
            if len(events) > 5:
                print(f"    ... and {len(events) - 5} more")
            print()
