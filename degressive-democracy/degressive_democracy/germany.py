"""Deutschland-Szenario: Degressive Demokratie mit Bundestagswahl-Parametern.

Modelliert den Bundestag mit realistischen Parametern:
- 5 Parteien mit typischen Strategien
- Versprechen aus echten Wahlprogramm-Kategorien
- 3 Transparenz-Stufen: Status quo, Wahlprogramm-Tracking, volle Transparenz
- 4-Jahres-Legislaturperiode (48 Monate)

Die Versprechen-Kategorien und Visibility-Werte orientieren sich an der
tatsächlichen öffentlichen Wahrnehmung von Wahlversprechen in Deutschland.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .models import (
    CitizenBehavior,
    ElectionConfig,
    ExternalShock,
    PoliticianBehavior,
    PowerModel,
    Promise,
    PromiseCategory,
    SimulationResult,
)
from .election import Election
from .metrics import SimulationMetrics, compute_metrics
from .evolution import run_evolution, EvolutionResult


# ---------------------------------------------------------------------------
# Deutsche Wahlprogramm-Versprechen
# ---------------------------------------------------------------------------

# Visibility-Stufen basierend auf öffentlicher Wahrnehmung:
# 1.0 = Kernversprechen, in jeder Talkshow diskutiert
# 0.7 = Im Wahlprogramm prominent, medial begleitet
# 0.4 = Im Wahlprogramm, aber kaum mediale Aufmerksamkeit
# 0.2 = Technische Details, nur Fachöffentlichkeit

WAHLPROGRAMM_PROMISES_OPAQUE = [
    # (Beschreibung, Kategorie, Schwierigkeit, Visibility im Status Quo)
    ("Steuern senken / Entlastung Mittelstand", PromiseCategory.ECONOMIC, 0.7, 0.9),
    ("Rente sichern / Rentenreform", PromiseCategory.SOCIAL, 0.8, 1.0),
    ("Klimaschutz / CO2-Reduktion", PromiseCategory.ENVIRONMENTAL, 0.8, 0.9),
    ("Digitalisierung Verwaltung", PromiseCategory.INFRASTRUCTURE, 0.6, 0.5),
    ("Innere Sicherheit stärken", PromiseCategory.SECURITY, 0.5, 0.7),
    ("Bezahlbarer Wohnraum", PromiseCategory.SOCIAL, 0.9, 0.8),
    ("Bildungsoffensive", PromiseCategory.SOCIAL, 0.7, 0.6),
    ("Infrastruktur Schiene/Strasse", PromiseCategory.INFRASTRUCTURE, 0.7, 0.4),
    ("Bürokratieabbau", PromiseCategory.ECONOMIC, 0.5, 0.3),
    ("Fachkräfteeinwanderung regeln", PromiseCategory.ECONOMIC, 0.6, 0.5),
]

# Mit Wahlprogramm-Tracking (Wahl-O-Mat, Abgeordnetenwatch):
# Alle Versprechen werden systematisch verfolgt → Visibility steigt
WAHLPROGRAMM_PROMISES_TRACKED = [
    (desc, cat, diff, min(vis + 0.3, 1.0))
    for desc, cat, diff, vis in WAHLPROGRAMM_PROMISES_OPAQUE
]

# Volle Transparenz: Alle Versprechen sind maximal sichtbar
WAHLPROGRAMM_PROMISES_TRANSPARENT = [
    (desc, cat, diff, 1.0)
    for desc, cat, diff, _ in WAHLPROGRAMM_PROMISES_OPAQUE
]


# ---------------------------------------------------------------------------
# Deutsche Bürger-Verteilung
# ---------------------------------------------------------------------------

# Basierend auf Wahlforschung (Infratest dimap Wahltypen):
# - Stammwähler ≈ LOYAL
# - Wechselwähler ≈ RATIONAL
# - Protestwähler ≈ VOLATILE
# - Sozial beeinflusst ≈ PEER_INFLUENCED
# - Taktisch ≈ STRATEGIC
# - Nichtwähler ≈ APATHETIC (Wahlbeteiligung BT2021: 76.6% → 23.4% apathisch)

GERMAN_CITIZEN_DISTRIBUTION = {
    CitizenBehavior.RATIONAL: 0.30,
    CitizenBehavior.LOYAL: 0.20,
    CitizenBehavior.VOLATILE: 0.10,
    CitizenBehavior.PEER_INFLUENCED: 0.10,
    CitizenBehavior.STRATEGIC: 0.05,
    CitizenBehavior.APATHETIC: 0.25,
}


# ---------------------------------------------------------------------------
# Partei-Strategien
# ---------------------------------------------------------------------------

# Vereinfachtes Modell: 5 Parteien mit typischen Verhaltensmustern
GERMAN_PARTY_STRATEGIES = {
    "Regierungspartei A": PoliticianBehavior.STRATEGIC_MIN,    # Koalitionskompromisse
    "Regierungspartei B": PoliticianBehavior.ADAPTIVE,         # Kleinerer Partner, reagiert auf Druck
    "Opposition Mitte": PoliticianBehavior.PROMISE_KEEPER,     # Will Regierung werden
    "Opposition Populist": PoliticianBehavior.POPULIST,        # Viele Versprechen, wenig Umsetzung
    "Opposition Klein": PoliticianBehavior.FRONTLOADER,        # Nischenthemen schnell umsetzen
}


# ---------------------------------------------------------------------------
# Transparenz-Szenarien
# ---------------------------------------------------------------------------

@dataclass
class TransparencyResult:
    """Ergebnis eines Transparenz-Szenarios."""
    name: str
    description: str
    avg_visibility: float
    metrics: SimulationMetrics
    result: SimulationResult
    strategic_min_power: float
    keeper_power: float
    populist_power: float


def _build_promises(pol_id: str, templates: list, rng, count: int = 5) -> list[Promise]:
    """Baue Versprechen aus Templates."""
    selected = list(templates)
    rng.shuffle(selected)
    promises = []
    for i in range(min(count, len(selected))):
        desc, cat, diff, vis = selected[i]
        promises.append(Promise(
            promise_id=f"{pol_id}_p{i}",
            category=cat,
            description=desc,
            difficulty=diff + rng.uniform(-0.05, 0.05),
            visibility=max(0.0, min(1.0, vis + rng.uniform(-0.05, 0.05))),
        ))
    return promises


def run_germany_scenario(
    transparency: str = "opaque",
    seed: int = 42,
    n_citizens: int = 1000,
) -> TransparencyResult:
    """Führe ein Deutschland-Szenario mit gegebener Transparenz-Stufe aus.

    Args:
        transparency: "opaque" (Status quo), "tracked" (Wahl-O-Mat),
                      "transparent" (volle Transparenz)
    """
    import random
    rng = random.Random(seed)

    if transparency == "tracked":
        templates = WAHLPROGRAMM_PROMISES_TRACKED
        desc = "Wahlprogramm-Tracking (Wahl-O-Mat, Abgeordnetenwatch): Visibility +0.3"
    elif transparency == "transparent":
        templates = WAHLPROGRAMM_PROMISES_TRANSPARENT
        desc = "Volle Transparenz: Alle Versprechen Visibility 1.0"
    else:
        templates = WAHLPROGRAMM_PROMISES_OPAQUE
        desc = "Status quo: Visibility nach medialer Aufmerksamkeit"

    strategies = list(GERMAN_PARTY_STRATEGIES.values())

    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution=GERMAN_CITIZEN_DISTRIBUTION,
        politician_behaviors=strategies,
    )

    election = Election(config)

    # Überschreibe die generierten Versprechen mit Wahlprogramm-Versprechen
    for pol in election.politicians:
        n = 10 if pol.behavior == PoliticianBehavior.POPULIST else 5
        new_promises = _build_promises(pol.politician_id, templates, rng, count=n)
        pol.promises = new_promises
        from .models import PromiseState as _PS
        pol.promise_states = {
            p.promise_id: _PS(promise_id=p.promise_id)
            for p in new_promises
        }

    # Run
    for t in range(1, 49):
        election.tick(t)

    result = SimulationResult(
        scenario_name=f"germany_{transparency}",
        config=config,
        tick_results=election.tick_results,
    )
    metrics = compute_metrics(result, election.politicians)

    # Identifiziere Strategien
    strat_min_power = next(
        (p.power for p in election.politicians if p.behavior == PoliticianBehavior.STRATEGIC_MIN),
        0.0
    )
    keeper_power = next(
        (p.power for p in election.politicians if p.behavior == PoliticianBehavior.PROMISE_KEEPER),
        0.0
    )
    populist_power = next(
        (p.power for p in election.politicians if p.behavior == PoliticianBehavior.POPULIST),
        0.0
    )

    avg_vis = sum(
        p.visibility for pol in election.politicians for p in pol.promises
    ) / max(1, sum(len(pol.promises) for pol in election.politicians))

    return TransparencyResult(
        name=transparency,
        description=desc,
        avg_visibility=avg_vis,
        metrics=metrics,
        result=result,
        strategic_min_power=strat_min_power,
        keeper_power=keeper_power,
        populist_power=populist_power,
    )


def run_germany_scenario_with_hook(
    transparency: str = "opaque",
    seed: int = 42,
    n_citizens: int = 1000,
    tick_hook=None,
) -> TransparencyResult:
    """Wie run_germany_scenario, aber mit optionalem tick_hook.

    tick_hook(election, tick) wird VOR jedem Tick aufgerufen.
    Ermöglicht Mid-Term-Interventionen (Journalismus, Social Media).
    """
    import random
    rng = random.Random(seed)

    if transparency == "tracked":
        templates = WAHLPROGRAMM_PROMISES_TRACKED
        desc = "Wahlprogramm-Tracking (Wahl-O-Mat, Abgeordnetenwatch): Visibility +0.3"
    elif transparency == "transparent":
        templates = WAHLPROGRAMM_PROMISES_TRANSPARENT
        desc = "Volle Transparenz: Alle Versprechen Visibility 1.0"
    else:
        templates = WAHLPROGRAMM_PROMISES_OPAQUE
        desc = "Status quo: Visibility nach medialer Aufmerksamkeit"

    strategies = list(GERMAN_PARTY_STRATEGIES.values())

    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution=GERMAN_CITIZEN_DISTRIBUTION,
        politician_behaviors=strategies,
    )

    election = Election(config)

    # Überschreibe Versprechen mit Wahlprogramm-Versprechen
    from .models import PromiseState
    for pol in election.politicians:
        n = 10 if pol.behavior == PoliticianBehavior.POPULIST else 5
        new_promises = _build_promises(pol.politician_id, templates, rng, count=n)
        pol.promises = new_promises
        pol.promise_states = {
            p.promise_id: PromiseState(promise_id=p.promise_id)
            for p in new_promises
        }

    for t in range(1, 49):
        if tick_hook:
            tick_hook(election, t)
        election.tick(t)

    result = SimulationResult(
        scenario_name=f"germany_{transparency}",
        config=config,
        tick_results=election.tick_results,
    )
    metrics = compute_metrics(result, election.politicians)

    strat_min_power = next(
        (p.power for p in election.politicians if p.behavior == PoliticianBehavior.STRATEGIC_MIN), 0.0
    )
    keeper_power = next(
        (p.power for p in election.politicians if p.behavior == PoliticianBehavior.PROMISE_KEEPER), 0.0
    )
    populist_power = next(
        (p.power for p in election.politicians if p.behavior == PoliticianBehavior.POPULIST), 0.0
    )
    avg_vis = sum(
        p.visibility for pol in election.politicians for p in pol.promises
    ) / max(1, sum(len(pol.promises) for pol in election.politicians))

    return TransparencyResult(
        name=transparency,
        description=desc,
        avg_visibility=avg_vis,
        metrics=metrics,
        result=result,
        strategic_min_power=strat_min_power,
        keeper_power=keeper_power,
        populist_power=populist_power,
    )


# ---------------------------------------------------------------------------
# Szenario: Investigativer Journalismus
# ---------------------------------------------------------------------------

def scenario_investigative_journalism(
    seed: int = 42,
    reveal_tick: int = 24,
    n_citizens: int = 1000,
) -> TransparencyResult:
    """Unsichtbare Versprechen werden mid-term aufgedeckt.

    Ab reveal_tick werden alle Versprechen mit visibility < 0.5
    auf 0.8 hochgesetzt — simuliert investigativen Journalismus
    oder Whistleblower, die gebrochene unsichtbare Versprechen aufdecken.
    """
    revealed = False

    def _reveal_hook(election: Election, tick: int) -> None:
        nonlocal revealed
        if tick == reveal_tick and not revealed:
            revealed = True
            for pol in election.politicians:
                new_promises = []
                for p in pol.promises:
                    if p.visibility < 0.5:
                        # Aufdeckung: Visibility springt auf 0.8
                        new_p = Promise(
                            promise_id=p.promise_id,
                            category=p.category,
                            description=p.description,
                            difficulty=p.difficulty,
                            visibility=0.8,
                            deadline_tick=p.deadline_tick,
                        )
                        new_promises.append(new_p)
                    else:
                        new_promises.append(p)
                pol.promises = new_promises

    result = run_germany_scenario_with_hook(
        "opaque", seed=seed, n_citizens=n_citizens, tick_hook=_reveal_hook,
    )
    result.name = "journalism"
    result.description = f"Investigativer Journalismus: Aufdeckung unsichtbarer Versprechen ab Tick {reveal_tick}"
    return result


# ---------------------------------------------------------------------------
# Szenario: Social Media Amplification
# ---------------------------------------------------------------------------

def scenario_social_media(
    seed: int = 42,
    n_citizens: int = 1000,
    amplification_start: int = 12,
) -> TransparencyResult:
    """Peer-Influence verbreitet Wissen über gebrochene Versprechen.

    Ab amplification_start: Wenn ein Bürger entzieht, sinkt die Satisfaction
    seiner Peer-Group zusätzlich — Social Media verbreitet die Nachricht
    über gebrochene Versprechen schneller als traditionelle Medien.
    """

    def _social_media_hook(election: Election, tick: int) -> None:
        if tick < amplification_start:
            return
        # Finde Bürger die gerade entzogen haben (im letzten Tick)
        if not election.tick_results:
            return
        last_tick = election.tick_results[-1]
        withdrawn_ids = {cid for cid, _ in last_tick.withdrawals}
        if not withdrawn_ids:
            return

        # Social Media Amplification: Peers der Entziehenden verlieren Satisfaction
        for citizen in election.citizens:
            if citizen.has_withdrawn:
                continue
            # Prüfe ob ein Peer gerade entzogen hat
            overlap = set(citizen.peer_group) & withdrawn_ids
            if overlap:
                # Jeder entziehende Peer senkt Satisfaction um 0.05
                penalty = len(overlap) * 0.05
                citizen.satisfaction = max(0.0, citizen.satisfaction - penalty)

    result = run_germany_scenario_with_hook(
        "opaque", seed=seed, n_citizens=n_citizens, tick_hook=_social_media_hook,
    )
    result.name = "social_media"
    result.description = f"Social Media Amplification: Peer-Influence ab Tick {amplification_start}"
    return result


# ---------------------------------------------------------------------------
# Multi-Term Evolution mit Deutschland-Parametern
# ---------------------------------------------------------------------------

def run_german_evolution(
    n_terms: int = 10,
    seed: int = 42,
    n_citizens: int = 1000,
) -> EvolutionResult:
    """Multi-Term Evolution mit deutschen Parametern.

    Verwendet die deutsche Bürger-Verteilung und Partei-Strategien.
    """
    return run_evolution(
        n_terms=n_terms,
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        initial_strategies=list(GERMAN_PARTY_STRATEGIES.values()),
        seed=seed,
        memory_penalty=0.1,
    )


# ---------------------------------------------------------------------------
# Szenario: Externe Krise (Economic Shock)
# ---------------------------------------------------------------------------

# Typische externe Schocks in einer Legislaturperiode
GERMAN_SHOCKS_ECONOMIC_CRISIS = [
    ExternalShock(
        tick=18,
        category=PromiseCategory.ECONOMIC,
        difficulty_increase=0.3,
        description="Wirtschaftskrise: Rezession, Steuereinbruch",
        blame_reduction=0.6,  # Bürger sehen: Politiker kann nichts dafür
    ),
]

GERMAN_SHOCKS_PANDEMIC = [
    ExternalShock(
        tick=12,
        category=PromiseCategory.SOCIAL,
        difficulty_increase=0.4,
        description="Pandemie: Gesundheitssystem überlastet",
        blame_reduction=0.7,
    ),
    ExternalShock(
        tick=12,
        category=PromiseCategory.ECONOMIC,
        difficulty_increase=0.2,
        description="Pandemie: Wirtschaftliche Folgen",
        blame_reduction=0.5,
    ),
]

GERMAN_SHOCKS_COALITION_COLLAPSE = [
    ExternalShock(
        tick=24,
        category=PromiseCategory.INFRASTRUCTURE,
        difficulty_increase=0.3,
        description="Koalitionskrise: Infrastruktur-Projekte blockiert",
        blame_reduction=0.3,  # Bürger geben Politiker teilweise Schuld
    ),
    ExternalShock(
        tick=24,
        category=PromiseCategory.ENVIRONMENTAL,
        difficulty_increase=0.2,
        description="Koalitionskrise: Klimaschutz verwässert",
        blame_reduction=0.2,  # Bürger sehen: hätte verhindert werden können
    ),
]


def scenario_economic_crisis(
    seed: int = 42,
    n_citizens: int = 1000,
) -> TransparencyResult:
    """Wirtschaftskrise ab Monat 18 — externe Ursache, niedrige Blame."""
    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution=GERMAN_CITIZEN_DISTRIBUTION,
        politician_behaviors=list(GERMAN_PARTY_STRATEGIES.values()),
        external_shocks=GERMAN_SHOCKS_ECONOMIC_CRISIS,
    )
    election = Election(config)
    for t in range(1, 49):
        election.tick(t)

    result = SimulationResult(
        scenario_name="germany_crisis",
        config=config,
        tick_results=election.tick_results,
    )
    metrics = compute_metrics(result, election.politicians)

    return TransparencyResult(
        name="crisis",
        description="Wirtschaftskrise ab Tick 18: ECONOMIC +0.3 difficulty, blame -0.6",
        avg_visibility=0.61,
        metrics=metrics,
        result=result,
        strategic_min_power=next((p.power for p in election.politicians if p.behavior == PoliticianBehavior.STRATEGIC_MIN), 0.0),
        keeper_power=next((p.power for p in election.politicians if p.behavior == PoliticianBehavior.PROMISE_KEEPER), 0.0),
        populist_power=next((p.power for p in election.politicians if p.behavior == PoliticianBehavior.POPULIST), 0.0),
    )


def scenario_blame_shifting(
    seed: int = 42,
    n_citizens: int = 1000,
) -> TransparencyResult:
    """Politiker manipulieren blame — behaupten externe Ursachen.

    Koalitionskrise: Blame wird reduziert, aber nicht so stark wie bei
    echter externer Krise. Bürger-Typen reagieren unterschiedlich:
    LOYAL glaubt die Ausrede, VOLATILE nicht.
    """
    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=5,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        citizen_distribution=GERMAN_CITIZEN_DISTRIBUTION,
        politician_behaviors=list(GERMAN_PARTY_STRATEGIES.values()),
        external_shocks=GERMAN_SHOCKS_COALITION_COLLAPSE,
    )
    election = Election(config)
    for t in range(1, 49):
        election.tick(t)

    result = SimulationResult(
        scenario_name="germany_blame",
        config=config,
        tick_results=election.tick_results,
    )
    metrics = compute_metrics(result, election.politicians)

    return TransparencyResult(
        name="blame_shift",
        description="Koalitionskrise ab Tick 24: blame_reduction 0.2-0.3 (Bürger skeptisch)",
        avg_visibility=0.61,
        metrics=metrics,
        result=result,
        strategic_min_power=next((p.power for p in election.politicians if p.behavior == PoliticianBehavior.STRATEGIC_MIN), 0.0),
        keeper_power=next((p.power for p in election.politicians if p.behavior == PoliticianBehavior.PROMISE_KEEPER), 0.0),
        populist_power=next((p.power for p in election.politicians if p.behavior == PoliticianBehavior.POPULIST), 0.0),
    )


# ---------------------------------------------------------------------------
# Erweiterter Vergleich: alle 7 Deutschland-Szenarien
# ---------------------------------------------------------------------------

def run_full_germany_comparison(seed: int = 42, n_citizens: int = 1000) -> list[TransparencyResult]:
    """Alle 7 Deutschland-Szenarien im Vergleich."""
    return [
        run_germany_scenario("opaque", seed=seed, n_citizens=n_citizens),
        run_germany_scenario("tracked", seed=seed, n_citizens=n_citizens),
        run_germany_scenario("transparent", seed=seed, n_citizens=n_citizens),
        scenario_investigative_journalism(seed=seed, n_citizens=n_citizens),
        scenario_social_media(seed=seed, n_citizens=n_citizens),
        scenario_economic_crisis(seed=seed, n_citizens=n_citizens),
        scenario_blame_shifting(seed=seed, n_citizens=n_citizens),
    ]


def run_transparency_comparison(seed: int = 42) -> list[TransparencyResult]:
    """Führe alle 3 Transparenz-Stufen aus und vergleiche."""
    return [
        run_germany_scenario("opaque", seed=seed),
        run_germany_scenario("tracked", seed=seed),
        run_germany_scenario("transparent", seed=seed),
    ]


def print_germany_report(results: list[TransparencyResult]) -> None:
    """Drucke den Deutschland-Vergleich."""
    print("DEUTSCHLAND-SZENARIO: Transparenz-Vergleich")
    print("=" * 72)
    print()
    print("  Frage: Reicht degressives Stimmrecht allein, oder braucht es")
    print("  zusätzlich Transparenz (Wahl-O-Mat, Abgeordnetenwatch)?")
    print()

    # Tabelle
    print(f"  {'Transparenz':<16} {'Avg Vis':>7} {'Entzüge':>8} {'StratMin':>8} {'Keeper':>7} {'Populist':>8} {'Satisfaction':>12}")
    print("  " + "-" * 68)
    for r in results:
        print(
            f"  {r.name:<16} "
            f"{r.avg_visibility:>6.2f} "
            f"{r.metrics.total_withdrawals:>7} "
            f"{r.strategic_min_power:>7.2f} "
            f"{r.keeper_power:>7.2f} "
            f"{r.populist_power:>7.2f} "
            f"{r.metrics.avg_final_satisfaction:>11.2f}"
        )

    print()

    # Analyse
    opaque = results[0]
    transparent = results[2]
    gap_opaque = opaque.keeper_power - opaque.strategic_min_power
    gap_transparent = transparent.keeper_power - transparent.strategic_min_power

    print("  Analyse:")
    opaque_withdrawals = opaque.metrics.total_withdrawals
    transparent_withdrawals = transparent.metrics.total_withdrawals

    if transparent_withdrawals < opaque_withdrawals * 0.5:
        print("  ► BESTÄTIGT: Transparenz verbessert das System deutlich!")
        print(f"    Status quo:   {opaque_withdrawals} Entzüge, Satisfaction {opaque.metrics.avg_final_satisfaction:.2f}")
        print(f"    Transparent:  {transparent_withdrawals} Entzüge, Satisfaction {transparent.metrics.avg_final_satisfaction:.2f}")
        print(f"    → {opaque_withdrawals - transparent_withdrawals} weniger Entzüge bei voller Transparenz.")
        print("    → Transparenz zwingt Strategic Minimum zu Promise Keeping.")
    else:
        print(f"  ► Entzüge opaque: {opaque_withdrawals}, transparent: {transparent_withdrawals}")

    if gap_opaque > 0.1:
        print(f"  ► Im Status quo wird StratMin bereits bestraft (Power {opaque.strategic_min_power:.2f})")
        print("    Deutsche Wahlprogramme sind sichtbar genug für Accountability.")
    elif gap_transparent > gap_opaque + 0.1:
        print("  ► Transparenz verstärkt den Accountability-Druck messbar.")

    # Populist
    if transparent.populist_power < 0.1:
        print("  ► Populisten werden unter voller Transparenz eliminiert")
        print(f"    (Power: {transparent.populist_power:.2f})")

    # Journalismus + Social Media (wenn vorhanden)
    journalism = next((r for r in results if r.name == "journalism"), None)
    social = next((r for r in results if r.name == "social_media"), None)

    if journalism:
        print()
        print(f"  ► Investigativer Journalismus: {journalism.metrics.total_withdrawals} Entzüge, "
              f"StratMin Power {journalism.strategic_min_power:.2f}")
        if journalism.metrics.total_withdrawals > opaque_withdrawals:
            print("    → Aufdeckung mid-term erzeugt MEHR Entzüge als Status quo")
            print("    → Verzögerte Transparenz bestraft stärker als dauerhaft niedrige")
        elif journalism.metrics.total_withdrawals < opaque_withdrawals:
            print("    → Weniger Entzüge als Status quo — Aufdeckung kommt zu spät")

    if social:
        print(f"  ► Social Media: {social.metrics.total_withdrawals} Entzüge, "
              f"StratMin Power {social.strategic_min_power:.2f}")
        if social.metrics.total_withdrawals > opaque_withdrawals:
            print("    → Peer-Amplification verstärkt den Accountability-Druck")
        else:
            print("    → Social Media hat keinen signifikanten Zusatzeffekt")
