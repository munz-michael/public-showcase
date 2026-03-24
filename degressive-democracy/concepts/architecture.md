# Architektur — Degressive Democracy

## Designprinzipien

1. **Asymmetrische Irreversibilität**: Einmal-Entzug, kein Zurückgeben
2. **Deterministic Core**: Kernmechanik modellunabhängig (Power-Berechnung, Constraint-Enforcement)
3. **Parametrische Vielfalt**: 6 × 5 × 4 Verhaltenskombinationen
4. **Emergenz durch Einfachheit**: Einfache Agenten-Regeln → komplexes Systemverhalten

## Architektur-Schichten

```
┌─────────────────────────────────────────────────┐
│               Simulation Layer                   │
│   simulation.py: 10 Szenarien, Szenario-Runner  │
├─────────────────────────────────────────────────┤
│              Orchestration Layer                  │
│   election.py: Tick-Loop, Setup, Vote-Tracking  │
├─────────────┬───────────────┬───────────────────┤
│  Citizen    │  Politician   │    Game Theory     │
│  Agent      │  Agent        │    Analysis        │
│             │               │                    │
│ satisfaction│ effort alloc  │ payoff functions   │
│ withdrawal  │ power calc    │ Nash equilibrium   │
│ peer influe │ promise mgmt  │ parameter sweep    │
├─────────────┴───────────────┴───────────────────┤
│                 Domain Model                     │
│  models.py: Vote, Promise, CitizenState,        │
│  PoliticianState, PowerModel, ElectionConfig    │
├─────────────────────────────────────────────────┤
│              Metrics + Provenance                │
│  metrics.py: Accountability, Power Curves       │
│  config/provenance.py: SHA-256 Chain            │
└─────────────────────────────────────────────────┘
```

## Datenfluss pro Tick

```
1. Politiker → allocate_effort() → PromiseState.progress++
2. Bürger → update_satisfaction() → CitizenState.satisfaction
3. Bürger → decide_withdrawal() → bool
4. IF withdraw: execute_withdrawal() → PoliticianState.current_votes--
5. Politician → update_power() → PoliticianState.power
6. Feedback: power → effective_effort (nächster Tick)
```

## Kern-Invarianten

- `citizen.has_withdrawn` kann nur von `False` → `True` wechseln (nie zurück)
- `sum(pol.current_votes for pol in politicians) + withdrawn == n_citizens`
- `0.0 <= satisfaction <= 1.0`
- `0.0 <= power <= 1.0`
- `0.0 <= progress <= 1.0`

## Offene Entscheidungen

| Entscheidung | Optionen | Status |
|-------------|----------|--------|
| Netzwerk-Topologie für Peer-Influence | Small-World, Scale-Free, Zufall | Offen |
| Informationsasymmetrie-Modell | Visibility-basiert, Delay-basiert | Visibility gewählt |
| Zeitliche Diskontierung | Lineare Erwartung, Exponential | Linear gewählt |
| Multi-Parteien Stimmentransfer | Nur Entzug vs. Transfer zu anderem Politiker | Nur Entzug gewählt |
