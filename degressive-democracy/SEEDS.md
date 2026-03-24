# Seed Registry — Reproducibility

All findings in this project are deterministic given their seed.
To reproduce any result, use the documented seed below.

## CLI Report
```bash
python3 -m degressive_democracy 42
```

## Key Seeds

| Scenario | Seed | Module | Function |
|----------|------|--------|----------|
| All CLI scenarios | 42 | `__main__` | `run_report(seed=42)` |
| Germany 7 variants | 42 | `germany` | `run_full_germany_comparison(seed=42)` |
| Evolution (generic) | 42 | `evolution` | `run_evolution(seed=42)` |
| Evolution (DE) | 42 | `germany` | `run_german_evolution(seed=42)` |
| Municipal comparison | 42 | `municipal` | `run_municipal_comparison(seed=42)` |
| Exploit analysis | 42 | `exploits` | `run_exploit_analysis(seed=42)` |
| Robust comparison | 1-20 | `robust` | `run_robust_comparison(n_seeds=20)` |
| Sensitivity analysis | 100-104 | `sensitivity` | `run_full_sensitivity(n_seeds=5)` |
| Model comparison | 42 | `satisfaction_models` | `run_model_comparison(seed=42)` |
| Empirical validation | 42 | `empirical` | `validate_against_merkel_iv(seed=42)` |
| Reversibility | 42 | `reversible` | `run_reversibility_comparison(seed=42)` |
| Dashboard | 42 | `dashboard` | `generate_dashboard(seed=42)` |

## Reproducing the Robust Analysis

The robust analysis runs seeds 1-20 (base_seed=1):
```python
from degressive_democracy.robust import run_robust_comparison
results = run_robust_comparison(n_seeds=20)
```

## Reproducing the Sensitivity Analysis

Sensitivity uses seeds 100-104 (base 100, 5 seeds per parameter value):
```python
from degressive_democracy.sensitivity import run_full_sensitivity
results = run_full_sensitivity(n_seeds=5)
```
