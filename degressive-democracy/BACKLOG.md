# Backlog — Degressive Democracy

Ideen, Inspirationen und Forschungsfragen für dieses Projekt.

## Priorisiert (nächste Iteration)

- [ ] Koalitionsvertrag-Szenario: 2 Parteien teilen Promise-Set, beide haften
- [ ] Warum konvergiert DE zu ADAPTIVE statt KEEPER? Tiefenanalyse der Apathie-Wirkung
- [ ] Früherer Journalismus (Tick 12 statt 24) — wie ändert sich das Ergebnis?

## Evaluieren

- [ ] Netzwerk-Topologie für Peer-Influence (Small-World vs. Scale-Free)
- [ ] Mehrparteiensystem: Stimmen-Transfer zwischen Politikern statt nur Entzug?
- [ ] Zeitliche Diskontierung: Sind frühe Entzüge wertvoller als späte?
- [ ] Koalitionsvertrag als gemeinsames Promise-Set (2 Parteien teilen Versprechen)

## Erledigt

- [x] Projektstruktur angelegt (2026-03-23)
- [x] Core-Modell: models, citizen, politician (2026-03-23)
- [x] Simulation: election, 10 scenarios, metrics (2026-03-23)
- [x] Game Theory: Nash-Analyse + Parameter-Sweep (2026-03-23)
- [x] Cross-Validation: Game Theory ↔ Simulation (2026-03-23)
- [x] Multi-Term Evolution: 10 Perioden, Konvergenznachweis (2026-03-23)
- [x] CLI Report: `python3 -m degressive_democracy` (2026-03-23)
- [x] Deutschland-Szenario: 3 Transparenz-Stufen mit Wahlprogramm-Versprechen (2026-03-23)
- [x] Literature Review: Deep Research + 6 Kernquellen + Relevanz-Bewertung (2026-03-23)
- [x] Tests: 185 Tests (models, citizen, politician, election, simulation, game_theory, validation, evolution, germany) (2026-03-23)
- [x] Bug: Hardcoded 48.0 in citizen.py Satisfaction-Formel → term_length Parameter (2026-03-23)
- [x] Investigativer Journalismus-Szenario: Aufdeckung ab Tick 24 (2026-03-23)
- [x] Social Media Amplification: Peer-Influence verbreitet Entzugs-Nachrichten (2026-03-23)
- [x] Multi-Term Evolution mit Deutschland-Parametern: Konvergiert zu ADAPTIVE (2026-03-23)
- [x] 5-Varianten Deutschland-Vergleich im CLI (2026-03-23)
- [x] ExternalShock-Modell: dynamische Difficulty + blame_reduction (2026-03-23)
- [x] Blame Attribution: Bürger-Typ-spezifisch (LOYAL ×0.5, VOLATILE ×1.5) (2026-03-23)
- [x] Wirtschaftskrise-Szenario: ECONOMIC +0.3 difficulty, blame -0.6 (2026-03-23)
- [x] Blame-Shifting-Szenario: Koalitionskrise, Politiker manipulieren blame (2026-03-23)
- [x] 7-Varianten Deutschland-Vergleich im CLI (2026-03-23)
- [x] Tests erweitert: 193 Tests (2026-03-23)
- [x] Öffentlicher Entzugs-Counter: Signal-Mechanismus (2026-03-23)
- [x] Citizen Factions: 4 Strategien (Threshold, Timed, Reactive, Opportunistic) (2026-03-23)
- [x] Party-Layer: Koalitionsverträge + Kollaps-Mechanik (2026-03-23)
- [x] Kalibrierung: Politbarometer-Proxy (BT2021, Infratest dimap) (2026-03-23)
- [x] AdvancedElection Engine: vereint alle 4 Mechanics (2026-03-23)
- [x] 4 Advanced-Szenarien + Tests: 213 Tests total (2026-03-23)
- [x] Investigativer Journalismus-Szenario: Aufdeckung ab Tick 24 (2026-03-23)
- [x] Social Media Amplification: Peer-Influence verbreitet Entzugs-Nachrichten (2026-03-23)
- [x] Multi-Term Evolution mit Deutschland-Parametern: Konvergiert zu ADAPTIVE (2026-03-23)
- [x] Tests erweitert: 185 Tests (+ journalism, social_media, german_evolution) (2026-03-23)
- [x] Honeypot-Exploit, Protest-Withdrawal, Snap Election (2026-03-23)
- [x] Sensitivity Analysis: 3 Parameter, alle Findings robust (2026-03-23)
- [x] FINDINGS.md Standalone-Report (2026-03-23)
- [x] README-Cleanup: doppelte Nummern, fehlende Module (2026-03-23)
- [x] Interaktives Dashboard: DE/EN, Animation, Snap Elections, Strategie-Karten (2026-03-23)
- [x] Statische Charts: 6 Visualisierungen (matplotlib) (2026-03-23)
- [x] Reversibilitaet Variante D: einmal zurueck, dann endgueltig (2026-03-23)
- [x] Praxis-Konzept: Stufenplan Kommune → Bund, Papier + Digital (2026-03-23)
- [x] 249 Tests total (2026-03-23)

## Parken

- [ ] MCP-Server für interaktive Abfragen
- [ ] Paper-Draft (JASSS oder arXiv Preprint)
- [ ] LinkedIn-Post zu den Kernergebnissen

## Verworfen

- [x] Vergleich mit Liquid Democracy als eigenes Szenario — zu weit entfernt vom Kernmechanismus (Delegation ≠ Entzug)
- [x] Variante E (Liquid-Style Reversibilität) — verliert Alleinstellungsmerkmal, wird zu LD
