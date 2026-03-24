# Degressive Democracy

**Agent-based simulation of irreversible vote withdrawal as democratic accountability mechanism.**

> Citizens can withdraw their vote from an elected politician **once per legislative term, irreversibly**. This creates continuous accountability pressure. Our simulation (249 tests, 21 modules) shows: promise-keeping is a Nash equilibrium, populists are always eliminated, and at municipal level the mere existence of the mechanism suffices as deterrence.

```
┌──────────────────────────────────────────────────────────────────┐
│                      Simulation Layer                            │
│  simulation.py · germany.py · municipal.py · exploits.py         │
│  18 scenarios: baseline, transparency, evolution, exploits ...   │
├──────────────────────────────────────────────────────────────────┤
│                     Orchestration Layer                           │
│  election.py: tick loop · vote tracking · external shocks        │
│  advanced.py: public counter · factions · coalitions · snap elec │
├────────────────┬────────────────┬────────────────────────────────┤
│  Citizen Agent │  Politician    │  Analysis                      │
│                │  Agent         │                                │
│  satisfaction  │  effort alloc  │  game_theory.py: Nash proof    │
│  (Prospect Th) │  5 strategies  │  validation.py: cross-valid    │
│  withdrawal    │  power calc    │  sensitivity.py: param sweep   │
│  peer influence│  promise mgmt  │  evolution.py: multi-term      │
│  6 types       │  snap election │  empirical.py: backtesting     │
├────────────────┴────────────────┴────────────────────────────────┤
│                       Domain Model                               │
│  models.py: Vote · Promise · CitizenState · PoliticianState      │
│  PowerModel (4) · ExternalShock · ElectionConfig                 │
├──────────────────────────────────────────────────────────────────┤
│                    Metrics + Visualization                        │
│  metrics.py: accountability · power curves · Pearson correlation  │
│  visualize.py: 6 chart types · dashboard.py: interactive HTML    │
└──────────────────────────────────────────────────────────────────┘

Data Flow per Tick:
  Politician → allocate_effort() → PromiseState.progress++
  Citizen    → update_satisfaction() → satisfaction (Prospect Theory)
  Citizen    → decide_withdrawal() → irreversible, once per term
  IF withdraw: PoliticianState.current_votes-- → power drops
  Feedback:    less power → less effort → more broken promises → more withdrawals
```

## Key Findings

1. **Promise-keeping is Nash equilibrium** — formally proven (Theorem 1) and robust across 4 satisfaction models including Prospect Theory
2. **Transparency matters more than the mechanism** — promise tracking (Wahl-O-Mat level) halves withdrawals and doubles satisfaction
3. **Populists are always eliminated** — in 100% of tested configurations (3/4 satisfaction models)
4. **Municipal level is optimal** — zero withdrawals needed, mechanism works as "dormant institution" (Serdult 2015)
5. **Information asymmetry is the real challenge** — Strategic Minimum politicians exploit low visibility to break invisible promises unpunished (Corollary 4)

Full findings: [FINDINGS.md](FINDINGS.md) | Paper draft: [paper/draft.md](paper/draft.md)

## Quick Start

```bash
pip install -e .
python3 -m degressive_democracy       # Full simulation report
python3 -m degressive_democracy 123   # Custom seed
pytest tests/ -v                      # 249 tests
```

## Interactive Dashboard

Open `output/dashboard.html` in a browser — DE/EN toggle, animated simulation, 5 scenarios.

## Architecture

```
degressive_democracy/
├── models.py              # Dataclasses, Enums, PowerModel, ExternalShock
├── citizen.py             # Satisfaction (Prospect Theory default) + Withdrawal
├── politician.py          # 5 strategies: Keeper, StratMin, Frontloader, Populist, Adaptive
├── election.py            # Tick-based simulation engine with snap elections
├── game_theory.py         # Nash equilibrium analysis + parameter sweep
├── validation.py          # Cross-validation: game theory ↔ simulation
├── evolution.py           # Multi-term strategy evolution
├── germany.py             # 7 Germany-specific scenarios
├── advanced.py            # Public counter, factions, coalitions, calibration
├── exploits.py            # Honeypot, protest withdrawal, snap elections
├── municipal.py           # 4 government levels: municipality to federal
├── satisfaction_models.py # 4 models: Linear, Prospect Theory, Exponential, Threshold
├── empirical.py           # Backtesting against German election data (Merkel IV)
├── reversible.py          # Variant D: withdraw once, return once, then permanent
├── sensitivity.py         # Parameter sensitivity analysis
├── robust.py              # Multi-seed statistical robustness
├── visualize.py           # Matplotlib charts (6 types)
└── dashboard.py           # Interactive HTML dashboard generator
```

## Formal Result

**Theorem 1**: Promise-keeping is a Nash equilibrium iff:

```
b_p × w × V_br × T / 2 > b_br × n
```

where `b_p` = power benefit, `w` = withdrawal rate per visible broken promise, `V_br` = sum of visibilities of broken promises, `T` = term length, `b_br` = benefit per broken promise, `n` = number broken.

**Corollary 4** (Information Asymmetry Paradox): Strategic Minimum undermines Nash by minimizing `V_br` — breaking only invisible promises. The formal condition holds but the effective withdrawal rate approaches zero.

Full proof: [concepts/nash_proof.md](concepts/nash_proof.md)

## Satisfaction Model

Default: **Prospect Theory** (Kahneman & Tversky 1979, Tversky & Kahneman 1992)

Losses (broken promises) hurt 2.25× more than gains (fulfilled promises). Parameters from the original publications: α=0.88, β=0.88, λ=2.25.

Core findings verified across 4 satisfaction models — results are model-independent.

## Germany Scenarios

7 scenarios with German parameters (23.4% non-voters, Wahlprogramm visibility):

| Scenario | Withdrawals | Satisfaction |
|---|---|---|
| Status quo (vis 0.61) | 118 ± 23 | 0.69 |
| Wahl-O-Mat tracking (vis 0.83) | 91 | 0.80 |
| Full transparency (vis 0.98) | 76 ± 5 | 0.80 |
| Investigative journalism | 165 | 0.61 |
| Economic crisis (blame shift) | 79 | 0.80 |

## References

- Ferejohn, J. (1986). Incumbent Performance and Electoral Control. *Public Choice* 50.
- Kahneman, D. & Tversky, A. (1979). Prospect Theory. *Econometrica* 47(2).
- Serdult, U. (2015). The history of a dormant institution. *Representation* 51(2).
- Welp, Y. (2016). Recall referendums in Peruvian municipalities. *Democratization* 23(7).
- Laver, M. & Sergenti, E. (2011). *Party Competition*. Princeton UP.
- Epstein, J.M. & Axtell, R.L. (1996). *Growing Artificial Societies*. MIT Press.

## License

Apache 2.0 — see [LICENSE](LICENSE)

## Author

Michael Munz
