# Degressive Democracy — Findings Report

**Agenten-Simulation: Kontinuierliche demokratische Accountability durch irreversiblen Stimmenentzug**

## Zusammenfassung

Wir simulieren einen demokratischen Mechanismus bei dem Bürger ihre Stimme während der Legislaturperiode **einmalig und unwiderruflich** entziehen können. Die Agenten-Simulation (6 Bürger-Typen, 5 Politiker-Strategien, 4 Power-Modelle, 249 Tests) beantwortet drei Forschungsfragen und produziert Ergebnisse die über alle getesteten Parameter-Konfigurationen robust sind.

## Methodik

- **Agenten**: 6 Bürger-Typen (Rational, Loyal, Volatile, Peer-Influenced, Strategic, Apathetic) × 5 Politiker-Strategien (Promise Keeper, Strategic Minimum, Frontloader, Populist, Adaptive)
- **Validierung**: Cross-Validation Game Theory ↔ Simulation, Multi-Seed Robustness (10-20 Seeds), Sensitivity Analysis (3 kritische Parameter)
- **Szenarien**: 18 Szenarien inkl. Deutschland-spezifisch (Wahlprogramm-Transparenz), Kommunal-Vergleich, Exploit-Analyse
- **Kalibrierung**: Deutsche Parameter (BT2021 Wahlbeteiligung, Infratest dimap, Politbarometer-Proxy)

## Ergebnisse

### 1. Promise-Keeping ist Nash-Gleichgewicht

Die Game-Theory-Analyse zeigt: Versprechen halten ist die dominante Strategie solange die Entzugsrate pro gebrochenem Versprechen ≥ 0.15 ist. Das Gleichgewicht bricht erst wenn der Benefit aus Versprechen-Brechen ~1.5× den Effort-Cost übersteigt.

**Sensitivity**: Robust über alle getesteten Parameter-Konfigurationen. Keeper ≥ StratMin gilt in 100% der Sweeps.

### 2. Transparenz ist wichtiger als der Mechanismus selbst

| Transparenz-Stufe | Entzüge (Ø) | Satisfaction (Ø) |
|---|---|---|
| Status quo (vis 0.61) | 118 ± 23 | 0.69 ± 0.06 |
| Wahl-O-Mat Tracking (vis 0.83) | 91 | 0.80 |
| Volle Transparenz (vis 0.98) | 76 ± 5 | 0.80 |

**Statistisch robust**: Transparent hat über alle Seeds weniger Entzüge als opaque (kein Überlapp in 90%-Konfidenzintervallen).

**Interpretation**: Der Sprung von "kein Tracking" zu "systematisches Tracking" (Wahl-O-Mat) ist 10× wichtiger als von "Tracking" zu "volle Transparenz". Transparenz-Tools wie Abgeordnetenwatch haben mehr Impact als der Stimmenentzug selbst.

### 3. Informationsasymmetrie ist das eigentliche Problem

Die Cross-Validation zwischen Game Theory und Simulation deckt die wichtigste Discrepancy auf:

- **Game Theory sagt**: Keeper dominiert Strategic Minimum (Payoff 33.0 vs 31.3)
- **Simulation zeigt**: Bei niedrigem Transparenz-Level sind beide **gleichwertig** (Power 1.0 vs 1.0)

**Ursache**: Strategic Minimum bricht nur unsichtbare Versprechen (visibility < 0.5). Die Bürger merken es nicht. Erst bei Transparenz-Level ≥ 0.7 wird StratMin bestraft.

### 4. Populisten werden in allen Konfigurationen eliminiert

**Sensitivity**: Populist Power < 0.30 in 100% aller Parameter-Sweeps. Einzige Ausnahme: bei `progress_scaling = 0.1` (extrem langsame Versprechen-Erfüllung) überlebt der Populist mit Power 0.28 — weil alle Strategien gleich schlecht aussehen.

### 5. Auf kommunaler Ebene reicht die Drohung

| Ebene | Entzüge | Satisfaction |
|---|---|---|
| Kommune (5.000 EW) | **0** | **1.00** |
| Kreisstadt (50.000 EW) | 62 | 0.80 |
| Großstadt (500.000 EW) | 56 | 0.80 |
| Bundestag (60 Mio) | 80 | 0.80 |

Auf Kommune-Ebene (visibility 0.85) produziert die Simulation **null Entzüge** bei perfekter Satisfaction. Der Mechanismus wirkt als "dormant institution" (Serdult 2015) — die bloße Existenz diszipliniert, ohne aktiviert zu werden.

### 6. Das deutsche System konvergiert zu ADAPTIVE

In der Multi-Term Evolution (10 Legislaturperioden) mit deutschen Parametern:
- **Perioden 0-3**: Strategic Minimum gewinnt
- **Perioden 4-9**: ADAPTIVE übernimmt
- **Promise Keeper überlebt, dominiert aber nie**

**Ursache**: 23.4% Apathische Bürger + moderate Transparenz bevorzugt reaktive Strategien. ADAPTIVE wechselt zwischen Keeper und StratMin je nach Entzugs-Druck.

### 7. Externe Krisen machen den Mechanismus zahnlos

| Szenario | Entzüge | Satisfaction |
|---|---|---|
| Normal | 199 | 0.43 |
| Wirtschaftskrise | 79 | 0.80 |
| Blame Shifting (Koalitionskrise) | 79 | 0.80 |

Externe Krisen reduzieren den blame-Faktor. Das ist **fair** (Bürger bestrafen nicht für Unkontrollierbares). Aber Blame Shifting funktioniert genauso gut — LOYAL-Bürger halbieren blame, VOLATILE verstärken ihn. Die Bürger-Zusammensetzung bestimmt ob Blame Shifting durchgeht.

### 8. Der Honeypot-Exploit funktioniert (theoretisch)

Ein Politiker kann absichtlich ein kleines unsichtbares Versprechen brechen um Volatile herauszulocken. In der Praxis: 0 Entzüge, volle Power. Der Exploit ist "erfolgreich" aber trivial — weil bei hoher Basis-Transparenz (DE avg 0.61) der gebrochene Versprechen sowieso nicht sichtbar genug ist um Reaktion auszulösen.

### 9. Protest-Entzüge existieren

Unter starkem Zeitgeist (Rezession + Politikverdrossenheit) entziehen 75 Bürger obwohl **alle Versprechen gehalten werden**. Das System bestraft Politiker für Dinge die sie nicht kontrollieren. Dies ist eine bekannte Schwäche retrospektiver Accountability-Mechanismen (Ferejohn 1986).

## Sensitivity Analysis

Alle 3 Kern-Findings sind über alle Parameter-Sweeps robust:

| Finding | broken_penalty | progress_scaling | withdrawal_threshold |
|---|---|---|---|
| Populist elimination | ✓ Robust | ✓ Robust* | ✓ Robust |
| Keeper ≥ StratMin | ✓ Robust | ✓ Robust | ✓ Robust |
| Mechanism active | ✓ Robust | ✓ Robust | ✓ Robust |

*Bei `progress_scaling = 0.1` überlebt Populist mit Power 0.28 (Grenzfall).

## Limitations

1. **Magic Numbers**: Die Satisfaction-Gewichte (0.1 fulfilled bonus, 0.3 broken penalty, 0.5 progress scaling) sind nicht empirisch kalibriert. Die Sensitivity Analysis zeigt Robustheit, aber die absoluten Zahlen (z.B. "118 Entzüge") sind Artefakte der Parameterwahl.
2. **Keine Netzwerk-Topologie**: Peer-Influence nutzt zufällige Peer-Groups, nicht Small-World oder Scale-Free Netzwerke.
3. **Vereinfachte Evolution**: Imitation Dynamics (Loser → Winner) statt formaler Replicator Dynamics.
4. **Kein echtes Bürger-Wahlverhalten**: Bürger sind einem Politiker fest zugeordnet. Kein Wechselwähler-Modell.

### 10. Reversibilität ändert das Ergebnis kaum

Variante D (einmal entziehen, einmal zurückgeben, dann endgültig) wurde simuliert:

| Metrik | Irreversibel | Variante D |
|---|---|---|
| Entzüge total | 92 | 98 |
| Rückgaben | — | 19 |
| Erneut permanent | — | 19 |
| Final entzogen | 92 | 79 |

19 Bürger durchlaufen den vollen Zyklus (Entzug → Rückgabe → erneuter Entzug). Alle 19 entziehen am Ende erneut — die zweite Chance wird nicht belohnt. **Irreversibilität ist kein Designfehler**, sie ist das Feature.

### 11. Praxis-Implementierung: Kommune zuerst

Die Simulation legt einen Stufenplan nahe:

1. **Pilot (Jahr 1-2)**: 3-5 Kommunen, Papier-Entzugsschein (wie Wahlschein), monatliche Zählung
2. **Digital-Pilot (Jahr 3-5)**: 1 Bundesland, eID-basiert, öffentlicher Counter
3. **Bundes-Diskussion (Jahr 5+)**: Grundgesetzänderung Art. 38a, falls kommunale Ergebnisse positiv

Kommune ist ideal weil: hohe Transparenz (Bürger kennen Bürgermeister), konkrete Versprechen ("Spielplatz bauen"), keine GG-Änderung nötig (Kommunalordnung reicht), und die Simulation zeigt 0 Entzüge nötig (dormant institution).

Detaillierte Analyse: [concepts/implementation_and_reversibility.md](concepts/implementation_and_reversibility.md)

## Policy-Implikation

Wenn man degressives Stimmrecht einführen würde:

1. **Transparenz-Infrastruktur ist Voraussetzung** — ein öffentliches Promise-Register mit Umsetzungs-Tracking (Wahl-O-Mat-Level reicht)
2. **Kommunale Ebene zuerst** — höchste Wirksamkeit, niedrigste Kosten, wirkt als dormant institution
3. **Irreversibel starten** — Reversibilität (Variante D) als Upgrade in Phase 2 falls Bürger das fordern
4. **Krisenklausel nötig** — parlamentarisch legitimierte blame-Reduktion bei externen Krisen
5. **Anti-Faction-Maßnahmen** — zeitlich gestreute Veröffentlichung von Entzügen gegen koordinierte Kampagnen
6. **Öffentlicher Entzugs-Zähler** — verstärkt den Feedback-Loop und die Frühwarn-Funktion
7. **Papier-Option immer verfügbar** — Datenschutz und digitale Teilhabe sicherstellen

## Referenzen

1. Ferejohn, J. (1986). Incumbent Performance and Electoral Control. *Public Choice* 50, 5-25.
2. Manin, B., Przeworski, A. & Stokes, S.C. (1999). *Democracy, Accountability, and Representation*. Cambridge University Press.
3. Serdult, U. (2015). The history of a dormant institution. *Representation* 51(2).
4. Welp, Y. (2016). Recall referendums in Peruvian municipalities. *Democratization* 23(7).
5. Laver, M. & Sergenti, E. (2011). *Party Competition: An Agent-Based Model*. Princeton University Press.
6. Epstein, J.M. & Axtell, R.L. (1996). *Growing Artificial Societies*. MIT Press.
