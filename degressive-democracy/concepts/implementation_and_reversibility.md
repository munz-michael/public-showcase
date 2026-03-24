# Offene Fragen: Reversibilitaet und Praxis-Implementierung

## 1. Kann man die Stimme zurueckgeben?

### Das Dilemma

Die Irreversibilitaet ist das Kernmerkmal — sie gibt dem Entzug Gewicht. Wenn die Stimme zurueckgegeben werden kann, wird der Entzug zur Umfrage statt zur Konsequenz. Aber: ein Buerger der in Monat 6 entzieht und in Monat 40 sieht dass der Politiker sich gebessert hat, hat keine Moeglichkeit das zu honorieren.

### 5 Varianten der Reversibilitaet

| Variante | Mechanik | Staerke des Drucks | Risiko |
|----------|---------|-------------------|--------|
| **A. Strikt irreversibel** (Status quo) | Einmal weg, immer weg | Maximal | Buerger spart Entzug auf, nutzt ihn evtl. nie |
| **B. Zeitlich begrenzt** | Entzug verfaellt nach 12 Monaten, Stimme kehrt zurueck | Mittel | Wird zur rollierenden Umfrage, weniger Konsequenz |
| **C. Bedingte Rueckgabe** | Stimme kehrt zurueck WENN Politiker ein bestimmtes Versprechen erfuellt | Hoch | Komplex, Politiker koennte Cherry-Picking betreiben |
| **D. Einmal zurueck, einmal weg** | Buerger kann EINMAL zurueckgeben, danach endgueltig | Hoch | Fairster Kompromiss: zweite Chance, aber nicht endlos |
| **E. Liquid-Style** | Jederzeit entziehbar und zurueckgebbar | Minimal | Wird zu Liquid Democracy — verliert Alleinstellungsmerkmal |

### Empfehlung: Variante D

**Einmal entziehen, einmal zurueckgeben, dann endgueltig.**

- Buerger entzieht in Monat 8 (wuetend ueber gebrochenes Versprechen)
- Politiker bessert sich, erfuellt Versprechen in Monat 20
- Buerger gibt Stimme zurueck in Monat 22 (belohnt Besserung)
- Ab jetzt: wenn Buerger nochmal entzieht, ist es endgueltig

Das gibt dem Buerger **2 Aktionen** pro Legislaturperiode statt 1. Aber die zweite Aktion (endgueltiger Entzug) ist die haertere — der Buerger hat schon einmal verziehen und wurde enttaeuscht.

### Simulation: Was aendert Variante D?

**Ergebnis** (500 Buerger, Deutsche Parameter, Seed 42):

| Metrik | Irreversibel | Variante D (threshold 0.3) |
|--------|-------------|---------------------------|
| Entzuege total | 92 | 98 |
| Rueckgaben | — | 19 |
| Erneut permanent entzogen | — | 19 |
| Final entzogen | 92 | 79 |
| Zufriedenheit | 0.80 | 0.80 |

**Erkenntnisse:**

1. **19 Buerger durchlaufen den vollen Zyklus** (Entzug → Rueckgabe → permanenter Entzug). Das zeigt: Variante D erzeugt einen echten Dialog zwischen Buergern und Politikern.

2. **Alle 19 Rueckkehrer entziehen erneut permanent** — die Politiker verbessern sich nicht dauerhaft genug. Die zweite Chance wird verschenkt.

3. **Weniger finale Entzuege (79 vs 92)** — weil einige Buerger ihre Stimme zurueckgeben und im "returned" Zustand bleiben (zufrieden genug um nicht nochmal zu entziehen).

4. **Gleiche Satisfaction (0.80)** — Variante D aendert das Gesamtergebnis kaum. Der Mechanismus wirkt auch ohne Reversibilitaet.

5. **Return-Threshold bestimmt die Dynamik:**
   - threshold=0.3: 19 Rueckgaben, 19 permanente
   - threshold=0.5: 5 Rueckgaben, 5 permanente
   - threshold=0.7: 4 Rueckgaben, 0 permanente

**Fazit:** Variante D ist **fair** (gibt Politikern eine zweite Chance) aber **aendert das Ergebnis kaum**. Das spricht dafuer dass die Irreversibilitaet kein Designfehler ist — das System funktioniert auch ohne Rueckgabe. Die Empfehlung bleibt: **Irreversibel starten** (einfacher), Variante D als **Upgrade in Phase 2** falls Buerger das fordern.

---

## 2. Wie koennte das in der Praxis aussehen?

### Grundgesetz-Kompatibilitaet

Das Grundgesetz regelt Wahlen in Art. 38:
> "Die Abgeordneten des Deutschen Bundestages werden in allgemeiner, unmittelbarer, freier, gleicher und geheimer Wahl gewaehlt."

Ein degressives Stimmrecht waere **keine Wahl** sondern ein **zusaetzliches Kontrollinstrument** — aehnlich wie Petitionen (Art. 17 GG) oder Volksbegehren auf Landesebene. Es wuerde das Wahlrecht nicht ersetzen sondern ergaenzen.

Noetig waere wahrscheinlich:
- Aenderung der Landtags- oder Kommunalordnung (fuer kommunale Ebene, kein GG-Aenderung)
- Oder: Grundgesetzaenderung Art. 38a fuer Bundesebene (2/3 Mehrheit)

### Technische Implementierung

#### Minimal-Version (Kommune, Papier-basiert)

1. Bei der Kommunalwahl erhaelt jeder Buerger einen **Entzugsschein** (wie Wahlschein)
2. Der Entzugsschein hat eine eindeutige Nummer, ist aber anonym (kein Name)
3. Buerger kann den Schein jederzeit beim Rathaus einwerfen (Briefkasten-Modell)
4. Rathaus zaehlt monatlich: "Buergermeister hat 3.247 von 4.100 aktive Stimmen"
5. Ergebnis wird oeffentlich ausgehaengt (Public Counter)

**Vorteile**: Kein IT-System noetig, sofort umsetzbar, analog zum Briefwahl-System.
**Nachteile**: Keine Rueckgabe moeglich (Papier ist weg), Zaehlung aufwaendig.

#### Digital-Version (Landes-/Bundesebene)

1. **Digitale Identitaet**: eID (Personalausweis-Funktion) oder BundID
2. **Plattform**: Aehnlich wie Online-Petition (z.B. epetitionen.bundestag.de)
3. **Ablauf**:
   - Buerger loggt sich mit eID ein
   - Sieht sein Stimmstatus: "Aktiv fuer [Partei/Kandidat]"
   - Kann "Stimme entziehen" klicken → Bestaetigung per 2FA
   - Status wechselt zu "Entzogen am [Datum]"
   - Optional (Variante D): "Stimme zurueckgeben" Button erscheint
4. **Oeffentlicher Counter**: Tagesaktuell auf bundestag.de
   - "SPD: 8.234.000 aktive Stimmen von 11.901.558 (69.2%)"
   - Trend-Anzeige: "+1.200 Entzuege diese Woche"

**Datenschutz**: Nur der Buerger selbst sieht SEINEN Status. Oeffentlich ist nur die aggregierte Zahl. Keine Rueckverfolgung wer entzogen hat.

#### Blockchain-Version (maximal transparent)

- Jede Stimme als Token auf einer permissioned Blockchain
- Entzug = Token-Transfer an ein Null-Wallet
- Oeffentlich verifizierbar ohne Identitaet preiszugeben (ZKP)
- Overkill fuer Kommune, interessant fuer Forschung

### Stufenplan fuer Deutschland

| Phase | Zeitraum | Ebene | Mechanik |
|-------|----------|-------|---------|
| **Pilot** | Jahr 1-2 | 3-5 Kommunen in einem Bundesland | Papier-Entzugsschein, irreversibel |
| **Evaluation** | Jahr 2-3 | Wissenschaftliche Begleitung | Vergleich mit Kontroll-Kommunen ohne Mechanismus |
| **Digital-Pilot** | Jahr 3-5 | 1 Bundesland (Kommunalebene) | eID-basiert, Variante D (1× zurueck) |
| **Bundes-Diskussion** | Jahr 5+ | Bundestag | Grundgesetz-Debatte, falls kommunale Ergebnisse positiv |

### Warum Kommune zuerst?

Die Simulation zeigt:
1. **0 Entzuege noetig** auf kommunaler Ebene (Deterrence reicht)
2. **Hohe Transparenz** (Buerger kennen Buergermeister persoenlich)
3. **Konkrete Versprechen** ("Spielplatz bauen" statt "Digitalisierung")
4. **Niedrige Implementierungskosten** (Papier-Entzugsschein reicht)
5. **Keine Grundgesetzaenderung noetig** (Kommunalordnung reicht)
6. **Reales Testbed** fuer wissenschaftliche Evaluation

### Moegliche Probleme in der Praxis

| Problem | Risiko | Loesung |
|---------|--------|---------|
| Stimmenkauf ("Ich zahle dir 50€ wenn du entziehst") | Mittel | Geheime Entzuege (wie geheime Wahl) |
| Organisierte Kampagnen | Hoch | Zeitverzoegerte Veroeffentlichung (woechentlich statt taeglich) |
| Politische Instrumentalisierung | Hoch | Unabhaengige Wahlbehoerde verwaltet den Mechanismus |
| Buerger verstehen das System nicht | Mittel | Pflicht-Information bei Wahlunterlagen |
| Zu wenig Beteiligung | Niedrig | Simulation zeigt: Deterrence wirkt auch ohne Aktivierung |
| Datenschutz-Bedenken | Hoch | Analog-Option (Papier) muss immer verfuegbar sein |
