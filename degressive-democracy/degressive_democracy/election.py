"""Election engine: tick-based term cycle orchestration."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
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
from .citizen import decide_withdrawal, execute_withdrawal, update_satisfaction
from .politician import allocate_effort, update_power


# ---------------------------------------------------------------------------
# Default distributions
# ---------------------------------------------------------------------------

DEFAULT_CITIZEN_DISTRIBUTION: dict[CitizenBehavior, float] = {
    CitizenBehavior.RATIONAL: 0.40,
    CitizenBehavior.LOYAL: 0.20,
    CitizenBehavior.VOLATILE: 0.15,
    CitizenBehavior.PEER_INFLUENCED: 0.15,
    CitizenBehavior.STRATEGIC: 0.05,
    CitizenBehavior.APATHETIC: 0.05,
}

PROMISE_TEMPLATES = [
    ("Lower taxes", PromiseCategory.ECONOMIC, 0.5, 0.8),
    ("Better healthcare", PromiseCategory.SOCIAL, 0.7, 0.9),
    ("Green energy transition", PromiseCategory.ENVIRONMENTAL, 0.6, 0.5),
    ("New infrastructure", PromiseCategory.INFRASTRUCTURE, 0.4, 0.3),
    ("Improved security", PromiseCategory.SECURITY, 0.3, 0.6),
    ("Education reform", PromiseCategory.SOCIAL, 0.6, 0.7),
    ("Digital transformation", PromiseCategory.ECONOMIC, 0.5, 0.4),
    ("Housing program", PromiseCategory.SOCIAL, 0.8, 0.8),
    ("Climate protection", PromiseCategory.ENVIRONMENTAL, 0.7, 0.6),
    ("Job creation", PromiseCategory.ECONOMIC, 0.4, 0.7),
]


# ---------------------------------------------------------------------------
# Election engine
# ---------------------------------------------------------------------------

class Election:
    """Orchestrates one election term simulation."""

    def __init__(self, config: ElectionConfig):
        self.config = config
        self.rng = random.Random(config.seed)
        self.citizens: list[CitizenState] = []
        self.politicians: list[PoliticianState] = []
        self.tick_results: list[TickResult] = []
        self._setup()

    def _setup(self) -> None:
        """Phase 0: Create agents and assign votes."""
        self._create_politicians()
        self._create_citizens()
        self._assign_votes()

    def _create_politicians(self) -> None:
        behaviors = self.config.politician_behaviors
        if behaviors is None:
            behaviors = [PoliticianBehavior.PROMISE_KEEPER] * self.config.n_politicians

        for i, behavior in enumerate(behaviors):
            pol_id = f"pol_{i}"
            n_promises = self.config.promises_per_politician
            if behavior == PoliticianBehavior.POPULIST:
                n_promises = n_promises * 2  # populists promise more

            promises = self._generate_promises(pol_id, n_promises)
            pol = PoliticianState(
                politician_id=pol_id,
                behavior=behavior,
                promises=promises,
                promise_states={
                    p.promise_id: PromiseState(
                        promise_id=p.promise_id,
                        effective_difficulty=p.difficulty,
                    )
                    for p in promises
                },
            )
            self.politicians.append(pol)

    def _generate_promises(self, pol_id: str, count: int) -> list[Promise]:
        templates = list(PROMISE_TEMPLATES)
        self.rng.shuffle(templates)
        promises = []
        for i in range(count):
            t = templates[i % len(templates)]
            promises.append(Promise(
                promise_id=f"{pol_id}_p{i}",
                category=t[1],
                description=t[0],
                difficulty=t[2] + self.rng.uniform(-0.1, 0.1),
                visibility=t[3] + self.rng.uniform(-0.1, 0.1),
            ))
        return promises

    def _create_citizens(self) -> None:
        dist = self.config.citizen_distribution or DEFAULT_CITIZEN_DISTRIBUTION
        behaviors = []
        for behavior, fraction in dist.items():
            count = int(self.config.n_citizens * fraction)
            behaviors.extend([behavior] * count)
        # Fill remainder with RATIONAL
        while len(behaviors) < self.config.n_citizens:
            behaviors.append(CitizenBehavior.RATIONAL)
        self.rng.shuffle(behaviors)

        categories = list(PromiseCategory)
        for i, behavior in enumerate(behaviors):
            # Assign 1-2 priority categories randomly
            n_priorities = self.rng.randint(1, 2)
            priorities = self.rng.sample(categories, n_priorities)

            threshold = 0.4 + self.rng.uniform(-0.1, 0.1)
            self.citizens.append(CitizenState(
                citizen_id=f"c_{i}",
                behavior=behavior,
                politician_id="",  # assigned in _assign_votes
                satisfaction=1.0,
                withdrawal_threshold=threshold,
                priority_categories=priorities,
            ))

    def _assign_votes(self) -> None:
        """Distribute citizens equally across politicians."""
        per_pol = self.config.n_citizens // self.config.n_politicians
        remainder = self.config.n_citizens % self.config.n_politicians

        idx = 0
        for i, pol in enumerate(self.politicians):
            count = per_pol + (1 if i < remainder else 0)
            for _ in range(count):
                if idx < len(self.citizens):
                    self.citizens[idx].politician_id = pol.politician_id
                    idx += 1
            pol.initial_votes = count
            pol.current_votes = count

        # Build peer groups (random subset of citizens voting for same politician)
        by_pol: dict[str, list[str]] = {}
        for c in self.citizens:
            by_pol.setdefault(c.politician_id, []).append(c.citizen_id)
        for c in self.citizens:
            peers = by_pol.get(c.politician_id, [])
            if len(peers) > 5:
                c.peer_group = self.rng.sample(
                    [p for p in peers if p != c.citizen_id],
                    min(5, len(peers) - 1),
                )

    # ---------------------------------------------------------------------------
    # Tick execution
    # ---------------------------------------------------------------------------

    def tick(self, t: int) -> TickResult:
        """Execute one simulation tick."""
        result = TickResult(tick=t)

        # 0. Apply external shocks
        self._apply_shocks(t, result)

        # 1. Politicians allocate effort
        for pol in self.politicians:
            wr = self._withdrawal_rate(pol.politician_id)
            allocate_effort(pol, tick=t, term_length=self.config.term_length, withdrawal_rate=wr)

        # 2-3. Citizens observe and update satisfaction
        for citizen in self.citizens:
            pol = self._get_politician(citizen.politician_id)
            if pol:
                update_satisfaction(citizen, pol, tick=t, term_length=self.config.term_length)

        # 4. Citizens decide withdrawal
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

        # 6. Collect metrics
        result.promise_updates = {
            pol.politician_id: list(pol.promise_states.values())
            for pol in self.politicians
        }
        satisfactions = [c.satisfaction for c in self.citizens]
        result.avg_satisfaction = sum(satisfactions) / len(satisfactions) if satisfactions else 0.0

        self.tick_results.append(result)
        return result

    def run(self) -> SimulationResult:
        """Run the full term simulation."""
        for t in range(1, self.config.term_length + 1):
            self.tick(t)

        return SimulationResult(
            scenario_name="custom",
            config=self.config,
            tick_results=self.tick_results,
        )

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    def _get_politician(self, pol_id: str) -> Optional[PoliticianState]:
        for p in self.politicians:
            if p.politician_id == pol_id:
                return p
        return None

    def _withdrawal_rate(self, pol_id: str) -> float:
        pol = self._get_politician(pol_id)
        if not pol or pol.initial_votes <= 0:
            return 0.0
        return 1.0 - (pol.current_votes / pol.initial_votes)

    def _peer_withdrawal_rate(self, citizen: CitizenState) -> float:
        if not citizen.peer_group:
            return 0.0
        withdrawn = sum(
            1 for c in self.citizens
            if c.citizen_id in citizen.peer_group and c.has_withdrawn
        )
        return withdrawn / len(citizen.peer_group)

    def _apply_shocks(self, tick: int, result: TickResult) -> None:
        """Apply external shocks that match this tick."""
        if not self.config.external_shocks:
            return
        for shock in self.config.external_shocks:
            if shock.tick != tick:
                continue
            result.events.append(f"SHOCK: {shock.description or shock.category.value} (+{shock.difficulty_increase} difficulty)")
            for pol in self.politicians:
                for promise in pol.promises:
                    if promise.category == shock.category:
                        ps = pol.promise_states.get(promise.promise_id)
                        if ps and ps.status not in (PromiseStatus.FULFILLED, PromiseStatus.BROKEN):
                            ps.effective_difficulty = min(1.0, ps.effective_difficulty + shock.difficulty_increase)
                            ps.blame = max(0.0, ps.blame - shock.blame_reduction)
