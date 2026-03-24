"""Core domain types for Degressive Democracy simulation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PromiseCategory(Enum):
    ECONOMIC = "economic"
    SOCIAL = "social"
    ENVIRONMENTAL = "environmental"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"


class PromiseStatus(Enum):
    PENDING = "pending"
    PROGRESSING = "progressing"
    FULFILLED = "fulfilled"
    BROKEN = "broken"
    ABANDONED = "abandoned"


class CitizenBehavior(Enum):
    RATIONAL = "rational"
    LOYAL = "loyal"
    VOLATILE = "volatile"
    PEER_INFLUENCED = "peer_influenced"
    STRATEGIC = "strategic"
    APATHETIC = "apathetic"


class PoliticianBehavior(Enum):
    PROMISE_KEEPER = "promise_keeper"
    STRATEGIC_MIN = "strategic_minimum"
    FRONTLOADER = "frontloader"
    POPULIST = "populist"
    ADAPTIVE = "adaptive"


class PowerModel(Enum):
    LINEAR = "linear"
    THRESHOLD = "threshold"
    CONVEX = "convex"
    LOGARITHMIC = "logarithmic"


# ---------------------------------------------------------------------------
# Immutable domain objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Promise:
    """A discrete political commitment with measurable outcome."""
    promise_id: str
    category: PromiseCategory
    description: str
    difficulty: float  # 0.0-1.0
    visibility: float  # 0.0-1.0
    deadline_tick: Optional[int] = None


@dataclass(frozen=True)
class Vote:
    """A single citizen's vote for a politician."""
    citizen_id: str
    politician_id: str
    cast_tick: int = 0
    withdrawn_tick: Optional[int] = None

    @property
    def is_active(self) -> bool:
        return self.withdrawn_tick is None


# ---------------------------------------------------------------------------
# Mutable state objects
# ---------------------------------------------------------------------------

@dataclass
class PromiseState:
    """Mutable tracking of a promise's progress."""
    promise_id: str
    status: PromiseStatus = PromiseStatus.PENDING
    progress: float = 0.0  # 0.0-1.0
    effort_invested: float = 0.0
    effective_difficulty: float = 0.0  # actual difficulty after shocks (set at runtime)
    blame: float = 1.0  # 0.0=external cause, 0.5=unclear, 1.0=politician's fault


@dataclass
class ExternalShock:
    """An external event that changes promise difficulty mid-term.

    Examples: economic crisis, pandemic, coalition collapse, court ruling.
    """
    tick: int
    category: PromiseCategory
    difficulty_increase: float  # how much harder affected promises become
    description: str = ""
    blame_reduction: float = 0.5  # how much blame shifts away from politician (0-1)


@dataclass
class CitizenState:
    """Mutable citizen state during a term."""
    citizen_id: str
    behavior: CitizenBehavior
    politician_id: str  # who this citizen voted for
    satisfaction: float = 1.0
    withdrawal_threshold: float = 0.4
    has_withdrawn: bool = False
    withdrawn_tick: Optional[int] = None
    peer_group: list[str] = field(default_factory=list)
    priority_categories: list[PromiseCategory] = field(default_factory=list)


@dataclass
class PoliticianState:
    """Mutable politician state during a term."""
    politician_id: str
    behavior: PoliticianBehavior
    promises: list[Promise] = field(default_factory=list)
    promise_states: dict[str, PromiseState] = field(default_factory=dict)
    initial_votes: int = 0
    current_votes: int = 0
    power: float = 1.0
    effort_budget_per_tick: float = 1.0


# ---------------------------------------------------------------------------
# Configuration & results
# ---------------------------------------------------------------------------

@dataclass
class ElectionConfig:
    """Configuration for one election cycle simulation."""
    n_citizens: int = 1000
    n_politicians: int = 5
    term_length: int = 48  # ticks (monthly over 4 years)
    power_model: PowerModel = PowerModel.LINEAR
    promises_per_politician: int = 5
    seed: Optional[int] = None
    citizen_distribution: Optional[dict[CitizenBehavior, float]] = None
    politician_behaviors: Optional[list[PoliticianBehavior]] = None
    external_shocks: Optional[list[ExternalShock]] = None


@dataclass
class TickResult:
    """Result of a single simulation tick."""
    tick: int
    withdrawals: list[tuple[str, str]] = field(default_factory=list)  # (citizen_id, politician_id)
    promise_updates: dict[str, list[PromiseState]] = field(default_factory=dict)
    power_levels: dict[str, float] = field(default_factory=dict)
    withdrawal_rates: dict[str, float] = field(default_factory=dict)
    avg_satisfaction: float = 0.0
    events: list[str] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Complete result of one scenario run."""
    scenario_name: str
    config: ElectionConfig
    tick_results: list[TickResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    provenance: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Power computation
# ---------------------------------------------------------------------------

def compute_power(current_votes: int, initial_votes: int, model: PowerModel) -> float:
    """Compute politician power level based on remaining votes."""
    if initial_votes <= 0:
        return 0.0
    ratio = current_votes / initial_votes
    ratio = max(0.0, min(1.0, ratio))

    if model == PowerModel.LINEAR:
        return ratio
    elif model == PowerModel.THRESHOLD:
        if ratio >= 0.75:
            return 1.0
        elif ratio >= 0.50:
            return 0.6
        elif ratio >= 0.25:
            return 0.2
        else:
            return 0.0
    elif model == PowerModel.CONVEX:
        return ratio ** 2
    elif model == PowerModel.LOGARITHMIC:
        if current_votes <= 0:
            return 0.0
        return math.log(current_votes + 1) / math.log(initial_votes + 1)
    else:
        return ratio
