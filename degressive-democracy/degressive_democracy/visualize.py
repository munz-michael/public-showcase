"""Visualization: Charts for key findings.

Generates publication-quality PNGs for:
1. Power curves over 48 ticks (per strategy)
2. Transparency comparison (bar chart)
3. Withdrawal cascade (stacked area)
4. Evolution timeline (strategy heatmap)
5. Municipal comparison (radar/bar)
6. Sensitivity tornado chart
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap

# Style
plt.rcParams.update({
    "figure.facecolor": "#ffffff",
    "axes.facecolor": "#f0f0f0",
    "text.color": "#000000",
    "axes.labelcolor": "#000000",
    "xtick.color": "#444444",
    "ytick.color": "#444444",
    "axes.edgecolor": "#b0b0b0",
    "grid.color": "#b0b0b0",
    "grid.alpha": 0.5,
    "font.size": 11,
    "axes.titlesize": 14,
    "figure.titlesize": 16,
    "legend.facecolor": "#ffffff",
    "legend.edgecolor": "#b0b0b0",
    "legend.fontsize": 9,
})

COLORS = {
    "promise_keeper": "#16873d",
    "strategic_minimum": "#c47a00",
    "frontloader": "#1a73e8",
    "populist": "#d42020",
    "adaptive": "#7c3aed",
    "keeper": "#16873d",
    "stratmin": "#c47a00",
    "pop": "#d42020",
}

ACCENT = "#1a73e8"
GOOD = "#16873d"
BAD = "#d42020"
WARN = "#c47a00"
NEUTRAL = "#444444"

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _save(fig, name: str) -> str:
    path = OUTPUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return str(path)


# ===================================================================
# 1. POWER CURVES
# ===================================================================

def chart_power_curves(seed: int = 42) -> str:
    """Power curves per politician strategy over 48 ticks."""
    from .simulation import scenario_citizen_mix
    result, metrics = scenario_citizen_mix(seed=seed)

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle("Power Trajectory per Politician Strategy (Citizen Mix)", fontweight="bold")

    strategies = ["promise_keeper", "strategic_minimum", "frontloader", "populist", "adaptive"]
    for i, strat in enumerate(strategies):
        pol_id = f"pol_{i}"
        if pol_id in metrics.power_curves:
            curve = metrics.power_curves[pol_id]
            color = list(COLORS.values())[i % len(COLORS)]
            ax.plot(range(1, len(curve) + 1), curve, linewidth=2, label=strat.replace("_", " ").title(), color=color)

    ax.set_xlabel("Month")
    ax.set_ylabel("Power")
    ax.set_ylim(-0.05, 1.1)
    ax.set_xlim(1, 48)
    ax.legend(loc="upper right")
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0.3, color=BAD, linestyle="--", alpha=0.3, label="_nolegend_")
    ax.text(49, 0.3, "Snap\nElection", fontsize=8, color=BAD, alpha=0.5, va="center")

    return _save(fig, "01_power_curves")


# ===================================================================
# 2. TRANSPARENCY COMPARISON
# ===================================================================

def chart_transparency_comparison(seed: int = 42) -> str:
    """Bar chart: withdrawals and satisfaction across transparency levels."""
    from .germany import run_full_germany_comparison
    results = run_full_germany_comparison(seed=seed, n_citizens=500)

    names = [r.name for r in results]
    withdrawals = [r.metrics.total_withdrawals for r in results]
    satisfactions = [r.metrics.avg_final_satisfaction for r in results]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Germany: Transparency Comparison (7 Scenarios)", fontweight="bold")

    # Withdrawals
    colors_wd = [GOOD if w < 100 else WARN if w < 200 else BAD for w in withdrawals]
    bars1 = ax1.barh(names, withdrawals, color=colors_wd, edgecolor="#b0b0b0")
    ax1.set_xlabel("Vote Withdrawals")
    ax1.set_title("Fewer = Better")
    for bar, val in zip(bars1, withdrawals):
        ax1.text(bar.get_width() + 3, bar.get_y() + bar.get_height()/2, str(val),
                va="center", fontsize=9, color="#111111")

    # Satisfaction
    colors_sat = [GOOD if s > 0.7 else WARN if s > 0.4 else BAD for s in satisfactions]
    bars2 = ax2.barh(names, satisfactions, color=colors_sat, edgecolor="#b0b0b0")
    ax2.set_xlabel("Average Satisfaction")
    ax2.set_xlim(0, 1.1)
    ax2.set_title("Higher = Better")
    for bar, val in zip(bars2, satisfactions):
        ax2.text(bar.get_width() + 0.02, bar.get_y() + bar.get_height()/2, f"{val:.2f}",
                va="center", fontsize=9, color="#111111")

    plt.tight_layout()
    return _save(fig, "02_transparency_comparison")


# ===================================================================
# 3. WITHDRAWAL CASCADE
# ===================================================================

def chart_withdrawal_cascade(seed: int = 42) -> str:
    """Withdrawal velocity (new per tick) as area chart."""
    from .simulation import scenario_citizen_mix, scenario_coordinated_attack
    _, mix_m = scenario_citizen_mix(seed=seed)
    _, attack_m = scenario_coordinated_attack(seed=seed)

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle("Withdrawal Dynamics: Citizen Mix vs. Coordinated Attack", fontweight="bold")

    ticks = range(1, 49)
    mix_vel = mix_m.withdrawal_velocity[:48]
    attack_vel = attack_m.withdrawal_velocity[:48]

    ax.fill_between(ticks, mix_vel, alpha=0.4, color=ACCENT, label="Citizen Mix")
    ax.plot(ticks, mix_vel, color=ACCENT, linewidth=1.5)
    ax.fill_between(ticks, attack_vel, alpha=0.3, color=BAD, label="Coordinated Attack")
    ax.plot(ticks, attack_vel, color=BAD, linewidth=1.5)

    ax.set_xlabel("Month")
    ax.set_ylabel("New Withdrawals per Month")
    ax.set_xlim(1, 48)
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Annotate peak
    peak_tick = attack_m.peak_withdrawal_tick
    if peak_tick > 0 and peak_tick <= len(attack_vel):
        peak_val = attack_vel[peak_tick - 1]
        ax.annotate(f"Peak: {peak_val} withdrawals",
                   xy=(peak_tick, peak_val),
                   xytext=(peak_tick + 5, peak_val + 5),
                   arrowprops=dict(arrowstyle="->", color=BAD),
                   color=BAD, fontsize=9)

    return _save(fig, "03_withdrawal_cascade")


# ===================================================================
# 4. EVOLUTION TIMELINE
# ===================================================================

def chart_evolution(seed: int = 42) -> str:
    """Strategy evolution over 10 terms as colored grid."""
    from .germany import run_german_evolution
    evo = run_german_evolution(n_terms=10, seed=seed, n_citizens=300)

    strategy_to_num = {
        "promise_keeper": 0,
        "strategic_minimum": 1,
        "frontloader": 2,
        "populist": 3,
        "adaptive": 4,
    }
    strategy_colors = [COLORS["promise_keeper"], COLORS["strategic_minimum"],
                       COLORS["frontloader"], COLORS["populist"], COLORS["adaptive"]]

    n_terms = len(evo.term_records)
    n_pols = len(evo.term_records[0].strategies)

    grid = []
    for r in evo.term_records:
        row = [strategy_to_num.get(s.value, 0) for s in r.strategies]
        grid.append(row)

    fig, ax = plt.subplots(figsize=(12, 4))
    fig.suptitle("German Evolution: Strategy Shifts over 10 Legislative Terms", fontweight="bold")

    cmap = LinearSegmentedColormap.from_list("strat", strategy_colors, N=5)
    im = ax.imshow(list(zip(*grid)), cmap=cmap, aspect="auto", vmin=0, vmax=4)

    ax.set_xlabel("Legislative Term")
    ax.set_ylabel("Politician")
    ax.set_xticks(range(n_terms))
    ax.set_yticks(range(n_pols))
    ax.set_yticklabels([f"Pol {i}" for i in range(n_pols)])

    # Winner markers
    for r in evo.term_records:
        winner_idx = int(r.winner.split("_")[1])
        ax.plot(r.term, winner_idx, marker="*", color="white", markersize=12, markeredgecolor="#111111")

    # Legend
    patches = [mpatches.Patch(color=c, label=n.replace("_", " ").title())
               for n, c in COLORS.items() if n in strategy_to_num]
    ax.legend(handles=patches, loc="upper left", bbox_to_anchor=(1.02, 1))

    plt.tight_layout()
    return _save(fig, "04_evolution_timeline")


# ===================================================================
# 5. MUNICIPAL COMPARISON
# ===================================================================

def chart_municipal(seed: int = 42) -> str:
    """Municipal level comparison as grouped bar chart."""
    from .municipal import run_municipal_comparison
    results = run_municipal_comparison(seed=seed, with_factions=False)

    names = [r.level.name.split(" (")[0] for r in results]
    withdrawals = [r.metrics.total_withdrawals for r in results]
    satisfactions = [r.metrics.avg_final_satisfaction for r in results]
    visibilities = [r.level.avg_visibility for r in results]

    fig, ax = plt.subplots(figsize=(10, 6))
    fig.suptitle("Government Levels: Municipality to Federal", fontweight="bold")

    x = range(len(names))
    width = 0.25

    bars1 = ax.bar([i - width for i in x], [w / 5 for w in withdrawals], width,
                   label="Withdrawals (÷5)", color=BAD, alpha=0.8)
    bars2 = ax.bar(x, satisfactions, width,
                   label="Satisfaction", color=GOOD, alpha=0.8)
    bars3 = ax.bar([i + width for i in x], visibilities, width,
                   label="Visibility", color=ACCENT, alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(names)
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.grid(True, alpha=0.2, axis="y")

    # Annotate Kommune
    ax.annotate("0 Withdrawals!\nDormant Institution",
               xy=(0, 1.0), xytext=(0.5, 1.08),
               arrowprops=dict(arrowstyle="->", color=GOOD),
               color=GOOD, fontsize=10, fontweight="bold")

    return _save(fig, "05_municipal_comparison")


# ===================================================================
# 6. SENSITIVITY TORNADO
# ===================================================================

def chart_sensitivity(n_seeds: int = 3) -> str:
    """Tornado chart: parameter sensitivity on withdrawal count."""
    from .sensitivity import run_full_sensitivity
    results = run_full_sensitivity(n_seeds=n_seeds)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle("Sensitivity Analysis: Robustness of Core Findings", fontweight="bold")

    for ax, (name, sr) in zip(axes, results.items()):
        values = [p.value for p in sr.points]
        withdrawals = [p.total_withdrawals_mean for p in sr.points]

        color_wd = [WARN if abs(v - sr.default_value) < 0.001 else NEUTRAL for v in values]
        ax.barh([f"{v:.2f}" for v in values], withdrawals, color=color_wd, edgecolor="#b0b0b0")
        ax.set_xlabel("Withdrawals (avg)")
        ax.set_title(sr.param_name.replace("_", " ").title())
        ax.axvline(x=withdrawals[values.index(sr.default_value)] if sr.default_value in values else 0,
                  color=ACCENT, linestyle="--", alpha=0.5)

        # Mark default
        for i, v in enumerate(values):
            if abs(v - sr.default_value) < 0.001:
                ax.get_yticklabels()[i].set_color(ACCENT)
                ax.get_yticklabels()[i].set_fontweight("bold")

    plt.tight_layout()
    return _save(fig, "06_sensitivity_tornado")


# ===================================================================
# GENERATE ALL
# ===================================================================

def generate_all(seed: int = 42) -> list[str]:
    """Generate all charts and return file paths."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []

    print("Generating charts...", flush=True)

    print("  [1/6] Power curves...", end="", flush=True)
    paths.append(chart_power_curves(seed))
    print(" done")

    print("  [2/6] Transparency comparison...", end="", flush=True)
    paths.append(chart_transparency_comparison(seed))
    print(" done")

    print("  [3/6] Withdrawal cascade...", end="", flush=True)
    paths.append(chart_withdrawal_cascade(seed))
    print(" done")

    print("  [4/6] Evolution timeline...", end="", flush=True)
    paths.append(chart_evolution(seed))
    print(" done")

    print("  [5/6] Municipal comparison...", end="", flush=True)
    paths.append(chart_municipal(seed))
    print(" done")

    print("  [6/6] Sensitivity tornado...", end="", flush=True)
    paths.append(chart_sensitivity())
    print(" done")

    print(f"\n  {len(paths)} charts saved to {OUTPUT_DIR}/")
    return paths
