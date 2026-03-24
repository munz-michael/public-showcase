# Game Theory — Degressive Democracy

## Formales Modell

### Akteure
- **Politiker** P mit Strategie s ∈ {keeper, breaker_k, populist, strategic_min}
- **Bürger** C mit Typ τ ∈ {rational, loyal, volatile, peer_influenced, strategic, apathetic}

### Utility-Funktion (Politiker)

```
U(s) = benefit_power × Σ(power(t)) - cost_effort × T + benefit_broken × n_broken
```

Wobei `power(t)` abhängt von der Withdrawal-Rate, die wiederum von der Strategie abhängt.

### Withdrawal-Rate

```
withdrawal_rate(s) = base_rate + withdrawal_rate_per_broken × n_broken(s) × visibility(s)
```

### Nash-Gleichgewicht Bedingung

**Theorem**: Promise-Keeping ist Nash-Gleichgewicht gdw:

```
benefit_power × withdrawal_penalty > benefit_broken
```

Wobei `withdrawal_penalty = withdrawal_rate_per_broken × T / 2` (Integral über die verlorene Power).

### Beweis-Sketch

1. Keeper-Payoff: `U_k = b_p × Σpower_k(t) - c_e × T`
2. Breaker-1-Payoff: `U_b = b_p × Σpower_b(t) - c_e × T + b_br`
3. Nash: `U_k ≥ U_b` ⟺ `b_p × (Σpower_k - Σpower_b) ≥ b_br`
4. Power-Differenz wächst linear mit Withdrawal-Rate × Term-Länge

## Parameter-Regime

| Regime | Bedingung | Dominante Strategie |
|--------|-----------|-------------------|
| Hoher Accountability-Druck | withdrawal_rate > 0.1 | Keeper (Nash) |
| Niedriger Druck | withdrawal_rate < 0.05 | Strategic Minimum |
| Kein Druck | withdrawal_rate = 0 | Breaker (kein Nash) |
| Hoher Broken-Benefit | benefit_broken > 3.0 | Breaker |

## Kritische Schwellenwerte

Aus `parameter_sweep("benefit_broken", ...)`:
- Nash bricht bei `benefit_broken ≈ 1.0-1.5` (abhängig von withdrawal_rate)
- Nash robust bei `withdrawal_rate_per_broken ≥ 0.15`

## Koordinierte Angriffe

Für THRESHOLD Power-Modell:
- **25% Entzug** → Power sinkt von 1.0 auf 0.6 (reduced)
- **50% Entzug** → Power sinkt auf 0.2 (weak)
- **75% Entzug** → Power = 0.0 (powerless)

Implikation: Eine koordinierte Kampagne von 25% der Wähler kann signifikante Machtreduktion erzwingen.

## Vergleich mit realen Mechanismen

| Mechanismus | Frequenz | Irreversibilität | Threshold |
|-------------|----------|-------------------|-----------|
| Reguläre Wahl | 4 Jahre | Reversibel | 50%+1 |
| Degressive Stimme | Kontinuierlich | Irreversibel | Proportional |
| Recall (Kalifornien) | Einmalig | Irreversibel | Supermajority |
| Misstrauensvotum | Parlamentarisch | Reversibel | Absolute Mehrheit |
