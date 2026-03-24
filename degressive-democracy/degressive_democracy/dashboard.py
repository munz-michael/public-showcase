"""Interactive HTML Dashboard with animated simulation.

Generates a self-contained HTML file with:
- Animated power bars shrinking over 48 ticks
- Withdrawal heatmap (citizens turning red)
- Live satisfaction curve
- Parameter controls (transparency, citizen mix)
- Scenario comparison charts
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import (
    CitizenBehavior,
    ElectionConfig,
    PoliticianBehavior,
    PowerModel,
)
from .election import Election
from .metrics import compute_metrics, SimulationMetrics
from .models import SimulationResult

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _run_and_collect(
    n_citizens: int = 300,
    n_politicians: int = 5,
    seed: int = 42,
    behaviors: list | None = None,
    visibility_scale: float = 1.0,
    citizen_distribution: dict | None = None,
) -> dict:
    """Run simulation and collect per-tick data for animation."""
    if behaviors is None:
        behaviors = [
            PoliticianBehavior.PROMISE_KEEPER,
            PoliticianBehavior.STRATEGIC_MIN,
            PoliticianBehavior.FRONTLOADER,
            PoliticianBehavior.POPULIST,
            PoliticianBehavior.ADAPTIVE,
        ]

    config = ElectionConfig(
        n_citizens=n_citizens,
        n_politicians=n_politicians,
        term_length=48,
        power_model=PowerModel.LINEAR,
        promises_per_politician=5,
        seed=seed,
        politician_behaviors=behaviors,
        citizen_distribution=citizen_distribution,
    )

    election = Election(config)

    # Scale visibility
    if visibility_scale != 1.0:
        from .models import Promise
        for pol in election.politicians:
            new_promises = []
            for p in pol.promises:
                new_promises.append(Promise(
                    promise_id=p.promise_id,
                    category=p.category,
                    description=p.description,
                    difficulty=p.difficulty,
                    visibility=max(0.1, min(1.0, p.visibility * visibility_scale)),
                    deadline_tick=p.deadline_tick,
                ))
            pol.promises = new_promises

    # Save initial behaviors before snap elections change them
    initial_behaviors = {f"pol_{i}": b.value for i, b in enumerate(behaviors)}

    # Collect per-tick data with snap election check
    ticks_data = []
    snap_events = []
    replaced = set()
    SNAP_THRESHOLD = 0.30

    import random as _rng_mod
    snap_rng = _rng_mod.Random(seed + 999)

    for t in range(1, 49):
        tr = election.tick(t)

        # Snap election check
        for pol in election.politicians:
            if pol.politician_id in replaced:
                continue
            if pol.initial_votes <= 0:
                continue
            remaining_pct = pol.current_votes / pol.initial_votes
            if remaining_pct < SNAP_THRESHOLD:
                old_behavior = pol.behavior.value
                pol.behavior = snap_rng.choice([
                    PoliticianBehavior.PROMISE_KEEPER,
                    PoliticianBehavior.ADAPTIVE,
                ])
                # Boost satisfaction of remaining citizens
                for c in election.citizens:
                    if c.politician_id == pol.politician_id and not c.has_withdrawn:
                        c.satisfaction = min(1.0, c.satisfaction + 0.3)
                # Reset broken promises
                from .models import PromiseStatus
                for ps in pol.promise_states.values():
                    if ps.status in (PromiseStatus.BROKEN, PromiseStatus.ABANDONED):
                        ps.status = PromiseStatus.PENDING
                        ps.progress = 0.0
                replaced.add(pol.politician_id)
                snap_events.append({
                    "tick": t, "pol_id": pol.politician_id,
                    "old_behavior": old_behavior,
                    "new_behavior": pol.behavior.value,
                    "remaining_pct": round(remaining_pct, 2),
                })

        # Promise fulfillment per politician
        promise_progress = {}
        for p in election.politicians:
            total = len(p.promise_states)
            fulfilled = sum(1 for ps in p.promise_states.values() if ps.progress >= 1.0)
            broken = sum(1 for ps in p.promise_states.values()
                        if ps.status.value in ("broken", "abandoned"))
            promise_progress[p.politician_id] = {
                "fulfilled": fulfilled, "broken": broken, "total": total,
                "avg_progress": round(sum(ps.progress for ps in p.promise_states.values()) / max(total, 1), 2),
            }

        tick_data = {
            "tick": t,
            "power": {p.politician_id: round(p.power, 3) for p in election.politicians},
            "votes": {p.politician_id: p.current_votes for p in election.politicians},
            "withdrawals": len(tr.withdrawals),
            "cumulative_wd": sum(1 for c in election.citizens if c.has_withdrawn),
            "satisfaction": round(tr.avg_satisfaction, 3),
            "wd_by_pol": {},
            "promises": promise_progress,
        }
        for pid in [p.politician_id for p in election.politicians]:
            tick_data["wd_by_pol"][pid] = sum(1 for _, p in tr.withdrawals if p == pid)

        ticks_data.append(tick_data)

    # Politician metadata — use INITIAL behavior, not post-snap
    pol_meta = []
    for p in election.politicians:
        pol_meta.append({
            "id": p.politician_id,
            "behavior": initial_behaviors.get(p.politician_id, p.behavior.value),
            "current_behavior": p.behavior.value,
            "initial_votes": p.initial_votes,
            "final_votes": p.current_votes,
            "final_power": round(p.power, 3),
            "was_replaced": p.politician_id in replaced,
        })

    return {
        "ticks": ticks_data,
        "politicians": pol_meta,
        "snap_events": snap_events,
        "n_citizens": n_citizens,
        "config": {
            "seed": seed,
            "visibility_scale": visibility_scale,
        },
    }


def generate_dashboard(seed: int = 42) -> str:
    """Generate the interactive HTML dashboard with DE/EN toggle."""

    # German citizen distribution (realistic)
    de_dist = {
        CitizenBehavior.RATIONAL: 0.30,
        CitizenBehavior.LOYAL: 0.20,
        CitizenBehavior.VOLATILE: 0.10,
        CitizenBehavior.PEER_INFLUENCED: 0.10,
        CitizenBehavior.STRATEGIC: 0.05,
        CitizenBehavior.APATHETIC: 0.25,
    }
    de_behaviors = [
        PoliticianBehavior.STRATEGIC_MIN,    # Regierungspartei
        PoliticianBehavior.ADAPTIVE,         # Koalitionspartner
        PoliticianBehavior.PROMISE_KEEPER,   # Opposition Mitte
        PoliticianBehavior.POPULIST,         # Opposition Populist
        PoliticianBehavior.FRONTLOADER,      # Opposition Klein
    ]

    scenarios = {
        # Default: Deutschland Status quo — Sichtbarkeit realistisch (nicht perfekt)
        "deutschland": _run_and_collect(
            seed=seed, n_citizens=300, behaviors=de_behaviors,
            citizen_distribution=de_dist, visibility_scale=0.8,
        ),
        # Niedrige Transparenz — StratMin kommt davon
        "niedrige_transparenz": _run_and_collect(
            seed=seed, n_citizens=300, behaviors=de_behaviors,
            citizen_distribution=de_dist, visibility_scale=0.5,
        ),
        # Hohe Transparenz — StratMin wird bestraft
        "hohe_transparenz": _run_and_collect(
            seed=seed, n_citizens=300, behaviors=de_behaviors,
            citizen_distribution=de_dist, visibility_scale=1.4,
        ),
        # Alle Populisten — maximaler Kollaps
        "alle_populisten": _run_and_collect(
            seed=seed, n_citizens=300,
            behaviors=[PoliticianBehavior.POPULIST] * 5,
            citizen_distribution=de_dist,
        ),
        # Alle Keeper — Deterrence-Effekt (dormant institution)
        "alle_keeper": _run_and_collect(
            seed=seed, n_citizens=300,
            behaviors=[PoliticianBehavior.PROMISE_KEEPER] * 5,
            citizen_distribution=de_dist,
        ),
    }

    scenarios_json = json.dumps(scenarios)

    # Load template and inject data
    template_path = Path(__file__).parent / "dashboard_template.html"
    html = template_path.read_text(encoding="utf-8")
    html = html.replace("__SCENARIOS_JSON__", scenarios_json)

    path = OUTPUT_DIR / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


# Old inline HTML removed — now uses dashboard_template.html
_OLD_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Degressive Democracy — Interactive Simulation</title>
<style>
/* ============ LANGUAGE TOGGLE ============ */
[data-lang="en"] {{ display: none; }}
body.lang-en [data-lang="en"] {{ display: block; }}
body.lang-en [data-lang="de"] {{ display: none; }}
body.lang-en span[data-lang="en"],
span[data-lang="de"] {{ display: inline; }}
body.lang-en span[data-lang="de"] {{ display: none; }}
span[data-lang="en"] {{ display: none; }}
body.lang-en span[data-lang="en"] {{ display: inline; }}

.lang-toggle {{
    position: fixed; top: 12px; right: 20px; z-index: 100;
    background: #161b22; border: 1px solid #30363d; border-radius: 20px;
    padding: 4px; display: flex; gap: 0;
}}
.lang-toggle button {{
    background: transparent; color: #8b949e; border: none;
    padding: 6px 14px; border-radius: 16px; cursor: pointer; font-size: 13px; font-weight: 600;
}}
.lang-toggle button.active {{
    background: #58a6ff; color: #0d1117;
}}
</style>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    padding: 20px;
    max-width: 1400px;
    margin: 0 auto;
}}
h1 {{ font-size: 24px; margin-bottom: 4px; }}
h2 {{ font-size: 16px; color: #8b949e; margin-bottom: 20px; font-weight: normal; }}
h3 {{ font-size: 14px; color: #58a6ff; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }}

.controls {{
    display: flex; gap: 12px; margin-bottom: 20px; align-items: center; flex-wrap: wrap;
}}
.controls select, .controls button {{
    background: #161b22; color: #e6edf3; border: 1px solid #30363d;
    padding: 8px 14px; border-radius: 6px; font-size: 13px; cursor: pointer;
}}
.controls button {{
    background: #238636; border-color: #238636; font-weight: 600;
}}
.controls button:hover {{ background: #2ea043; }}
.controls button.active {{ background: #f85149; border-color: #f85149; }}
.controls .speed {{ background: #161b22; padding: 8px 12px; border-radius: 6px; border: 1px solid #30363d; }}

.grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
}}
.panel {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 16px;
}}
.panel.full {{ grid-column: 1 / -1; }}

/* Tick counter */
.tick-display {{
    font-size: 48px;
    font-weight: 700;
    color: #58a6ff;
    text-align: center;
    font-variant-numeric: tabular-nums;
}}
.tick-label {{ text-align: center; color: #8b949e; font-size: 12px; }}

/* Power bars */
.power-bar-container {{
    margin-bottom: 8px;
}}
.power-bar-label {{
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    margin-bottom: 2px;
}}
.power-bar-label .name {{ color: #e6edf3; }}
.power-bar-label .value {{ color: #8b949e; font-variant-numeric: tabular-nums; }}
.power-bar-bg {{
    height: 24px;
    background: #21262d;
    border-radius: 4px;
    overflow: hidden;
    position: relative;
}}
.power-bar-fill {{
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
}}
.power-bar-fill.keeper {{ background: linear-gradient(90deg, #238636, #3fb950); }}
.power-bar-fill.strategic {{ background: linear-gradient(90deg, #d29922, #f0883e); }}
.power-bar-fill.frontloader {{ background: linear-gradient(90deg, #1f6feb, #58a6ff); }}
.power-bar-fill.populist {{ background: linear-gradient(90deg, #da3633, #f85149); }}
.power-bar-fill.adaptive {{ background: linear-gradient(90deg, #8957e5, #bc8cff); }}

/* Satisfaction gauge */
.gauge {{
    height: 8px; background: #21262d; border-radius: 4px; margin: 8px 0;
}}
.gauge-fill {{
    height: 100%; border-radius: 4px; transition: width 0.3s ease;
    background: linear-gradient(90deg, #f85149, #f0883e, #3fb950);
}}

/* Withdrawal counter */
.wd-counter {{
    font-size: 36px; font-weight: 700; text-align: center;
    font-variant-numeric: tabular-nums;
}}
.wd-counter.low {{ color: #3fb950; }}
.wd-counter.mid {{ color: #f0883e; }}
.wd-counter.high {{ color: #f85149; }}

/* Chart area */
canvas {{ width: 100%; height: 200px; }}

/* Citizen grid */
.citizen-grid {{
    display: flex; flex-wrap: wrap; gap: 2px;
}}
.citizen-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    transition: background-color 0.3s ease;
}}
.citizen-dot.active {{ background: #3fb950; }}
.citizen-dot.withdrawn {{ background: #f85149; }}
.citizen-dot.apathetic {{ background: #30363d; }}

/* Findings */
.finding {{
    background: #0d1117; border-left: 3px solid #58a6ff;
    padding: 8px 12px; margin-bottom: 8px; font-size: 13px; border-radius: 0 4px 4px 0;
}}
.finding.warn {{ border-color: #f0883e; }}
.finding.bad {{ border-color: #f85149; }}
</style>
</head>
<body>

<!-- Language Toggle -->
<div class="lang-toggle">
    <button id="btnDE" class="active" onclick="setLang('de')">DE</button>
    <button id="btnEN" onclick="setLang('en')">EN</button>
</div>

<h1>Degressive Democracy</h1>
<h2>
    <span data-lang="de">Interaktive Simulation: Was passiert wenn Buerger ihre Stimme waehrend der Legislaturperiode entziehen koennen?</span>
    <span data-lang="en">Interactive Simulation: What happens when citizens can withdraw their vote during a legislative term?</span>
</h2>

<!-- INTRO -->
<div class="panel full" style="margin-bottom:16px; border-left: 3px solid #58a6ff;">
    <div data-lang="de">
        <h3>Das Konzept</h3>
        <p style="font-size:14px; line-height:1.6; color:#c9d1d9; margin-bottom:8px;">
            In heutigen Demokratien geben Buerger alle 4 Jahre ihre Stimme ab — und haben danach keinen Einfluss mehr.
            <strong>Degressives Stimmrecht</strong> aendert das: Jeder Buerger kann seine Stimme <strong>einmal pro Legislaturperiode
            unwiderruflich entziehen</strong>. Das erzeugt kontinuierlichen Druck auf Politiker, ihre Wahlversprechen einzuhalten.
        </p>
        <p style="font-size:13px; color:#8b949e;">
            Das Standard-Szenario zeigt eine <strong>deutsche Bundestagswahl</strong>: 300 Buerger (25% Nichtwaehler),
            5 Parteien (Regierung: Strategic Min + Adaptive, Opposition: Keeper + Populist + Frontloader),
            48 Monate Legislaturperiode. Druecke <strong>Play</strong> und beobachte wer ueberlebt.
        </p>
    </div>
    <div data-lang="en">
        <h3>The Concept</h3>
        <p style="font-size:14px; line-height:1.6; color:#c9d1d9; margin-bottom:8px;">
            In today's democracies, citizens vote once every 4 years — and have no influence after that.
            <strong>Degressive voting</strong> changes this: Each citizen can <strong>withdraw their vote once per legislative term,
            irreversibly</strong>. This creates continuous pressure on politicians to keep their promises.
        </p>
        <p style="font-size:13px; color:#8b949e;">
            The default scenario models a <strong>German federal election</strong>: 300 citizens (25% non-voters),
            5 parties (Government: Strategic Min + Adaptive, Opposition: Keeper + Populist + Frontloader),
            48-month legislative term. Press <strong>Play</strong> and watch who survives.
        </p>
    </div>
</div>

<div class="controls">
    <select id="scenario">
        <option value="deutschland" data-de="&#127465;&#127466; Deutschland (5 Parteien)" data-en="&#127465;&#127466; Germany (5 parties)">&#127465;&#127466; Deutschland (5 Parteien)</option>
        <option value="niedrige_transparenz" data-de="&#128065; Niedrige Transparenz (vis x0.5)" data-en="&#128065; Low Transparency (vis x0.5)">&#128065; Niedrige Transparenz (vis x0.5)</option>
        <option value="hohe_transparenz" data-de="&#128161; Hohe Transparenz (vis x1.4)" data-en="&#128161; High Transparency (vis x1.4)">&#128161; Hohe Transparenz (vis x1.4)</option>
        <option value="alle_populisten" data-de="&#128520; Alle Populisten" data-en="&#128520; All Populists">&#128520; Alle Populisten</option>
        <option value="alle_keeper" data-de="&#9989; Alle Promise Keeper" data-en="&#9989; All Promise Keepers">&#9989; Alle Promise Keeper</option>
    </select>
    <button id="playBtn" onclick="togglePlay()">&#9654; Play</button>
    <button onclick="resetSim()">&#8634; Reset</button>
    <div class="speed">
        Speed: <input type="range" id="speedSlider" min="50" max="1000" value="300" style="vertical-align:middle; width:100px;">
    </div>
    <div style="color:#8b949e; font-size:12px; margin-left:auto;">
        <span data-lang="de">Seed: 42 | 300 Buerger | 48 Monate | 25% Nichtwaehler</span>
        <span data-lang="en">Seed: 42 | 300 citizens | 48 months | 25% non-voters</span>
    </div>
</div>

<div class="grid">
    <!-- Tick + Satisfaction -->
    <div class="panel" style="text-align:center;">
        <h3><span data-lang="de">Legislaturperiode</span><span data-lang="en">Legislative Term</span></h3>
        <div class="tick-display" id="tickDisplay">0</div>
        <div class="tick-label"><span data-lang="de">Monat / 48</span><span data-lang="en">Month / 48</span></div>
        <div style="margin-top:12px;">
            <h3><span data-lang="de">Buerger-Zufriedenheit</span><span data-lang="en">Citizen Satisfaction</span></h3>
            <p style="font-size:11px; color:#8b949e; margin-bottom:4px;">
                <span data-lang="de">Durchschnitt aller Buerger. Sinkt wenn Versprechen gebrochen werden.</span>
                <span data-lang="en">Average across all citizens. Drops when promises are broken.</span>
            </p>
            <div class="gauge"><div class="gauge-fill" id="satGauge" style="width:100%"></div></div>
            <div style="font-size:24px; font-weight:600;" id="satValue">1.00</div>
        </div>
    </div>

    <!-- Withdrawal counter + citizen grid -->
    <div class="panel">
        <h3><span data-lang="de">Stimmenentzuege</span><span data-lang="en">Vote Withdrawals</span></h3>
        <div class="wd-counter low" id="wdCounter">0 / 200</div>
        <div style="font-size:11px; color:#8b949e; text-align:center; margin-bottom:8px;">
            <span data-lang="de">kumulativ | diesen Monat:</span>
            <span data-lang="en">cumulative | this month:</span>
            <span id="wdThisTick">0</span>
        </div>
        <p style="font-size:11px; color:#8b949e; margin-bottom:6px;">
            <span data-lang="de">Jeder Buerger kann nur EINMAL entziehen — unwiderruflich. Entzogene Stimmen kommen nicht zurueck.</span>
            <span data-lang="en">Each citizen can only withdraw ONCE — irreversibly. Withdrawn votes never come back.</span>
        </p>
        <h3>
            <span data-lang="de">Buerger</span><span data-lang="en">Citizens</span>
            <span style="font-weight:normal; font-size:11px;">
                (<span style="color:#3fb950;">&#9679;</span>=<span data-lang="de">aktiv</span><span data-lang="en">active</span>
                <span style="color:#f85149;">&#9679;</span>=<span data-lang="de">entzogen</span><span data-lang="en">withdrawn</span>)
            </span>
        </h3>
        <div class="citizen-grid" id="citizenGrid"></div>
    </div>

    <!-- Power bars -->
    <div class="panel full">
        <h3><span data-lang="de">Macht pro Politiker</span><span data-lang="en">Power per Politician</span></h3>
        <p style="font-size:12px; color:#8b949e; margin-bottom:8px;">
            <span data-lang="de">
                Macht = f(verbleibende Stimmen). Weniger Stimmen = weniger Macht = weniger Faehigkeit Versprechen umzusetzen.
                Das ist der Feedback-Loop: gebrochene Versprechen &#8594; Entzuege &#8594; weniger Macht &#8594; noch mehr gebrochene Versprechen.
            </span>
            <span data-lang="en">
                Power = f(remaining votes). Fewer votes = less power = less ability to fulfill promises.
                This is the feedback loop: broken promises &#8594; withdrawals &#8594; less power &#8594; more broken promises.
            </span>
        </p>
        <div id="powerBars"></div>
        <div style="margin-top:8px; font-size:11px; color:#8b949e;">
            <span data-lang="de">
                <span style="color:#3fb950;">&#9632;</span> Promise Keeper: haelt alle Versprechen |
                <span style="color:#f0883e;">&#9632;</span> Strategic Min: haelt nur sichtbare |
                <span style="color:#58a6ff;">&#9632;</span> Frontloader: einfache zuerst |
                <span style="color:#f85149;">&#9632;</span> Populist: verspricht viel, haelt wenig |
                <span style="color:#bc8cff;">&#9632;</span> Adaptive: reagiert auf Druck
            </span>
            <span data-lang="en">
                <span style="color:#3fb950;">&#9632;</span> Promise Keeper: keeps all promises |
                <span style="color:#f0883e;">&#9632;</span> Strategic Min: keeps only visible ones |
                <span style="color:#58a6ff;">&#9632;</span> Frontloader: easy ones first |
                <span style="color:#f85149;">&#9632;</span> Populist: promises much, delivers little |
                <span style="color:#bc8cff;">&#9632;</span> Adaptive: responds to pressure
            </span>
        </div>
    </div>

    <!-- Live charts -->
    <div class="panel">
        <h3><span data-lang="de">Power-Verlauf</span><span data-lang="en">Power Over Time</span></h3>
        <p style="font-size:11px; color:#8b949e; margin-bottom:4px;">
            <span data-lang="de">Jede Linie ist ein Politiker. Faellt eine Linie, verliert er Stimmen.</span>
            <span data-lang="en">Each line is a politician. A falling line means losing votes.</span>
        </p>
        <canvas id="powerChart"></canvas>
    </div>
    <div class="panel">
        <h3><span data-lang="de">Entzugs-Geschwindigkeit</span><span data-lang="en">Withdrawal Velocity</span></h3>
        <p style="font-size:11px; color:#8b949e; margin-bottom:4px;">
            <span data-lang="de">Neue Entzuege pro Monat. Hohe Balken = Entzugs-Welle.</span>
            <span data-lang="en">New withdrawals per month. Tall bars = withdrawal wave.</span>
        </p>
        <canvas id="wdChart"></canvas>
    </div>

    <!-- Findings -->
    <div class="panel full">
        <h3><span data-lang="de">Live-Erkenntnisse</span><span data-lang="en">Live Findings</span></h3>
        <div id="findings"></div>
    </div>

    <!-- Key findings summary -->
    <div class="panel full" style="border-left: 3px solid #3fb950;">
        <div data-lang="de">
            <h3>Zentrale Ergebnisse der Forschung</h3>
            <div class="finding">1. <strong>Promise-Keeping ist Nash-Gleichgewicht</strong> — es lohnt sich nicht, Versprechen zu brechen, solange Buerger entziehen koennen</div>
            <div class="finding">2. <strong>Transparenz ist wichtiger als der Mechanismus</strong> — Wahl-O-Mat-Tracking halbiert die Entzuege und verdoppelt die Zufriedenheit</div>
            <div class="finding bad">3. <strong>Populisten werden immer eliminiert</strong> — in 100% aller getesteten Konfigurationen</div>
            <div class="finding warn">4. <strong>Auf kommunaler Ebene reicht die Drohung</strong> — 0 Entzuege noetig, der Mechanismus wirkt durch blosse Existenz</div>
            <div class="finding">5. <strong>Externe Krisen sind der blinde Fleck</strong> — Blame Shifting schuetzt Politiker vor Bestrafung</div>
        </div>
        <div data-lang="en">
            <h3>Key Research Findings</h3>
            <div class="finding">1. <strong>Promise-keeping is a Nash Equilibrium</strong> — breaking promises doesn't pay as long as citizens can withdraw</div>
            <div class="finding">2. <strong>Transparency matters more than the mechanism</strong> — promise tracking halves withdrawals and doubles satisfaction</div>
            <div class="finding bad">3. <strong>Populists are always eliminated</strong> — in 100% of tested configurations</div>
            <div class="finding warn">4. <strong>At municipal level, the threat alone suffices</strong> — 0 withdrawals needed, the mechanism works by mere existence</div>
            <div class="finding">5. <strong>External crises are the blind spot</strong> — blame shifting protects politicians from punishment</div>
        </div>
    </div>
</div>

<script>
const SCENARIOS = {scenarios_json};
const COLORS = {{
    'promise_keeper': '#3fb950',
    'strategic_minimum': '#f0883e',
    'frontloader': '#58a6ff',
    'populist': '#f85149',
    'adaptive': '#bc8cff',
}};
const BAR_CLASSES = {{
    'promise_keeper': 'keeper',
    'strategic_minimum': 'strategic',
    'frontloader': 'frontloader',
    'populist': 'populist',
    'adaptive': 'adaptive',
}};

let currentScenario = 'deutschland';
let currentTick = 0;
let playing = false;
let interval = null;
let data = SCENARIOS[currentScenario];

// --- Init ---
function init() {{
    data = SCENARIOS[currentScenario];
    currentTick = 0;

    // Build citizen grid
    const grid = document.getElementById('citizenGrid');
    grid.innerHTML = '';
    for (let i = 0; i < data.n_citizens; i++) {{
        const dot = document.createElement('div');
        dot.className = 'citizen-dot active';
        dot.id = 'c_' + i;
        grid.appendChild(dot);
    }}

    // Build power bars
    const bars = document.getElementById('powerBars');
    bars.innerHTML = '';
    data.politicians.forEach(p => {{
        const cls = BAR_CLASSES[p.behavior] || 'keeper';
        bars.innerHTML += `
            <div class="power-bar-container">
                <div class="power-bar-label">
                    <span class="name">${{p.behavior.replace(/_/g,' ').replace(/\\b\\w/g,l=>l.toUpperCase())}}</span>
                    <span class="value" id="pv_${{p.id}}">1.00 | ${{p.initial_votes}} Stimmen</span>
                </div>
                <div class="power-bar-bg">
                    <div class="power-bar-fill ${{cls}}" id="pb_${{p.id}}" style="width:100%"></div>
                </div>
            </div>`;
    }});

    // Clear charts
    powerHistory = {{}};
    wdHistory = [];
    data.politicians.forEach(p => {{ powerHistory[p.id] = []; }});

    updateDisplay();
}}

// --- Animation ---
let powerHistory = {{}};
let wdHistory = [];

function stepForward() {{
    if (currentTick >= 48) {{
        stopPlay();
        return;
    }}
    currentTick++;
    const td = data.ticks[currentTick - 1];

    // Update power bars
    data.politicians.forEach(p => {{
        const power = td.power[p.id];
        const votes = td.votes[p.id];
        document.getElementById('pb_' + p.id).style.width = (power * 100) + '%';
        document.getElementById('pv_' + p.id).textContent =
            power.toFixed(2) + ' | ' + votes + ' Stimmen';
        powerHistory[p.id].push(power);
    }});

    // Update withdrawal counter
    const cumWd = td.cumulative_wd;
    const counter = document.getElementById('wdCounter');
    counter.textContent = cumWd + ' / ' + data.n_citizens;
    counter.className = 'wd-counter ' + (cumWd < 30 ? 'low' : cumWd < 80 ? 'mid' : 'high');
    document.getElementById('wdThisTick').textContent = td.withdrawals;

    // Update citizen dots (turn red for withdrawn)
    // We mark dots by cumulative count
    for (let i = 0; i < data.n_citizens; i++) {{
        const dot = document.getElementById('c_' + i);
        if (i < cumWd) {{
            dot.className = 'citizen-dot withdrawn';
        }}
    }}

    // Update satisfaction
    document.getElementById('satGauge').style.width = (td.satisfaction * 100) + '%';
    document.getElementById('satValue').textContent = td.satisfaction.toFixed(2);

    // Update tick
    document.getElementById('tickDisplay').textContent = currentTick;

    // Withdrawal history
    wdHistory.push(td.withdrawals);

    // Draw charts
    drawCharts();
    updateFindings(td);
}}

function updateDisplay() {{
    document.getElementById('tickDisplay').textContent = currentTick;
    document.getElementById('wdCounter').textContent = '0 / ' + data.n_citizens;
    document.getElementById('wdCounter').className = 'wd-counter low';
    document.getElementById('satGauge').style.width = '100%';
    document.getElementById('satValue').textContent = '1.00';
    document.getElementById('wdThisTick').textContent = '0';
    document.getElementById('findings').innerHTML =
        '<div class="finding">Drücke Play um die Simulation zu starten...</div>';

    // Reset bars
    data.politicians.forEach(p => {{
        document.getElementById('pb_' + p.id).style.width = '100%';
        document.getElementById('pv_' + p.id).textContent = '1.00 | ' + p.initial_votes + ' Stimmen';
    }});

    // Reset citizen dots
    for (let i = 0; i < data.n_citizens; i++) {{
        const dot = document.getElementById('c_' + i);
        if (dot) dot.className = 'citizen-dot active';
    }}

    // Clear canvases
    ['powerChart', 'wdChart'].forEach(id => {{
        const c = document.getElementById(id);
        const ctx = c.getContext('2d');
        c.width = c.offsetWidth;
        c.height = 200;
        ctx.clearRect(0, 0, c.width, c.height);
    }});
}}

function drawCharts() {{
    // Power chart
    const pc = document.getElementById('powerChart');
    const pctx = pc.getContext('2d');
    pc.width = pc.offsetWidth;
    pc.height = 200;
    pctx.clearRect(0, 0, pc.width, pc.height);

    const xScale = pc.width / 48;
    const yScale = pc.height - 20;

    data.politicians.forEach(p => {{
        const hist = powerHistory[p.id];
        if (hist.length < 2) return;
        pctx.beginPath();
        pctx.strokeStyle = COLORS[p.behavior] || '#8b949e';
        pctx.lineWidth = 2;
        hist.forEach((v, i) => {{
            const x = i * xScale;
            const y = yScale - v * (yScale - 10) + 10;
            if (i === 0) pctx.moveTo(x, y);
            else pctx.lineTo(x, y);
        }});
        pctx.stroke();
    }});

    // Withdrawal velocity chart
    const wc = document.getElementById('wdChart');
    const wctx = wc.getContext('2d');
    wc.width = wc.offsetWidth;
    wc.height = 200;
    wctx.clearRect(0, 0, wc.width, wc.height);

    if (wdHistory.length > 0) {{
        const maxWd = Math.max(...wdHistory, 1);
        const bw = wc.width / 48;
        wdHistory.forEach((v, i) => {{
            const h = (v / maxWd) * (wc.height - 20);
            const x = i * bw;
            wctx.fillStyle = v > 10 ? '#f85149' : v > 3 ? '#f0883e' : '#3fb950';
            wctx.fillRect(x, wc.height - h - 10, bw - 1, h);
        }});
    }}
}}

let currentLang = 'de';

function setLang(lang) {{
    currentLang = lang;
    document.body.className = lang === 'en' ? 'lang-en' : '';
    document.getElementById('btnDE').className = lang === 'de' ? 'active' : '';
    document.getElementById('btnEN').className = lang === 'en' ? 'active' : '';
    // Update select options
    document.querySelectorAll('#scenario option').forEach(opt => {{
        opt.textContent = opt.getAttribute('data-' + lang) || opt.textContent;
    }});
    updateFindings(currentTick > 0 ? data.ticks[currentTick - 1] : null);
}}

function t(de, en) {{ return currentLang === 'en' ? en : de; }}

function updateFindings(td) {{
    const f = document.getElementById('findings');
    if (!td) {{
        f.innerHTML = '<div class="finding">' + t(
            'Druecke Play um die Simulation zu starten...',
            'Press Play to start the simulation...'
        ) + '</div>';
        return;
    }}
    let html = '';

    const populist = data.politicians.find(p => p.behavior === 'populist');
    if (populist) {{
        const popPower = td.power[populist.id];
        if (popPower < 0.1 && currentTick > 5) {{
            html += '<div class="finding bad">' + t(
                'Populist eliminiert — Power ' + popPower.toFixed(2) + '. Zu viele Versprechen, zu wenig Umsetzung.',
                'Populist eliminated — Power ' + popPower.toFixed(2) + '. Too many promises, too little delivery.'
            ) + '</div>';
        }}
    }}

    if (td.satisfaction < 0.5) {{
        html += '<div class="finding warn">' + t(
            'Zufriedenheit unter 50% — Buerger verlieren Vertrauen. Entzugs-Welle droht.',
            'Satisfaction below 50% — citizens losing trust. Withdrawal wave imminent.'
        ) + '</div>';
    }}

    if (td.cumulative_wd > data.n_citizens * 0.2) {{
        const pct = Math.round(td.cumulative_wd/data.n_citizens*100);
        html += '<div class="finding bad">' + t(
            pct + '% der Stimmen entzogen. Politiker verlieren ihre demokratische Legitimation.',
            pct + '% of votes withdrawn. Politicians losing democratic legitimacy.'
        ) + '</div>';
    }}

    const allKeeper = data.politicians.every(p => td.power[p.id] > 0.9);
    if (allKeeper && currentTick > 20) {{
        html += '<div class="finding">' + t(
            'Alle Politiker behalten volle Macht — der Mechanismus wirkt als Deterrence. Wie in der Schweiz: die blosse Existenz diszipliniert.',
            'All politicians retain full power — the mechanism works as deterrence. Like in Switzerland: mere existence disciplines.'
        ) + '</div>';
    }}

    // Feedback loop detection
    const losingPols = data.politicians.filter(p => td.power[p.id] < 0.5 && td.power[p.id] > 0.01);
    if (losingPols.length > 0 && currentTick > 10 && currentTick < 40) {{
        html += '<div class="finding warn">' + t(
            'Feedback-Loop aktiv: weniger Macht = weniger Effort = mehr gebrochene Versprechen = mehr Entzuege.',
            'Feedback loop active: less power = less effort = more broken promises = more withdrawals.'
        ) + '</div>';
    }}

    if (currentTick === 48) {{
        html += '<div class="finding" style="border-color:#58a6ff; font-weight:600;">' + t(
            'Legislaturperiode beendet. Entzuege: ' + td.cumulative_wd + '/' + data.n_citizens +
            ', Zufriedenheit: ' + td.satisfaction.toFixed(2) +
            '. Bei der naechsten Wahl wuerden die Buerger dieses Ergebnis beruecksichtigen.',
            'Legislative term ended. Withdrawals: ' + td.cumulative_wd + '/' + data.n_citizens +
            ', Satisfaction: ' + td.satisfaction.toFixed(2) +
            '. In the next election, citizens would factor in this track record.'
        ) + '</div>';
    }}

    if (!html) {{
        html = '<div class="finding">' + t(
            'Monat ' + currentTick + ' — Simulation laeuft. Beobachte die Power-Balken und das Buerger-Grid.',
            'Month ' + currentTick + ' — Simulation running. Watch the power bars and citizen grid.'
        ) + '</div>';
    }}
    f.innerHTML = html;
}}

// --- Controls ---
function togglePlay() {{
    if (playing) stopPlay();
    else startPlay();
}}

function startPlay() {{
    if (currentTick >= 48) resetSim();
    playing = true;
    document.getElementById('playBtn').innerHTML = '&#9724; Pause';
    document.getElementById('playBtn').classList.add('active');
    const speed = 1050 - parseInt(document.getElementById('speedSlider').value);
    interval = setInterval(stepForward, speed);
}}

function stopPlay() {{
    playing = false;
    document.getElementById('playBtn').innerHTML = '&#9654; Play';
    document.getElementById('playBtn').classList.remove('active');
    if (interval) clearInterval(interval);
}}

function resetSim() {{
    stopPlay();
    currentScenario = document.getElementById('scenario').value;
    data = SCENARIOS[currentScenario];
    powerHistory = {{}};
    wdHistory = [];
    data.politicians.forEach(p => {{ powerHistory[p.id] = []; }});
    init();
}}

document.getElementById('scenario').addEventListener('change', resetSim);
document.getElementById('speedSlider').addEventListener('input', () => {{
    if (playing) {{ stopPlay(); startPlay(); }}
}});

// Boot
init();
</script>
</body>
</html>"""

