"""
Figure generator for the Layered LLM Defense paper / showcase.

Produces four publication-quality PNG figures matching the convention
of other showcase projects in this repository:

  fig_1_architecture.png       — Four-layer defense stack (system overview)
  fig_2_ablation.png           — Vanilla / Bio-Off / Full ablation bars
  fig_3_baseline_comparison.png — LLD vs Undefended / LlamaGuard / RAIN
  fig_4_layer_latency.png      — Per-layer latency breakdown

All figures use the academic style preset from viz_engine.

Run:
    cd /workspaces/Claude\\ Code/content/public_showcase/layered-llm-defense
    python3 scripts/generate_figures.py
    # → outputs to figures/
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add tools/ to path so we can import viz_engine
_REPO_ROOT = Path("/workspaces/Claude Code")
sys.path.insert(0, str(_REPO_ROOT / "tools"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from viz_engine.architecture import system_overview
from viz_engine.paper_charts import (
    benchmark_bars,
    comparison_bars,
    metric_strip,
)
from viz_engine.styles import set_style, apply_style, get_color


# ── Output directory ─────────────────────────────────────────────────────────

FIG_DIR = Path(__file__).resolve().parent.parent / "figures"
FIG_DIR.mkdir(exist_ok=True)


def _draw_ablation_chart() -> None:
    """
    Custom ablation chart for the headline result.

    Standard benchmark_bars hides the 0.0% Full bar visually because
    the bar height is zero pixels. We draw it manually with explicit
    value labels above every bar plus delta arrows showing the
    transferable +18.6 pp gain (Vanilla → Bio-Off) and the further
    gain to Full (with the artifact caveat).
    """
    apply_style()

    systems = ["Vanilla\n(L1 + L3)", "Bio-Off\n(+ engineering)", "Full\n(+ bio primitives)"]
    values = [89.8, 71.2, 0.0]
    colors = ["#c0392b", "#e67e22", "#27ae60"]

    fig, ax = plt.subplots(figsize=(9.0, 5.5))

    x = list(range(len(systems)))
    bars = ax.bar(x, values, color=colors, alpha=0.88, width=0.55, edgecolor="white", linewidth=1.5)

    # Value labels above each bar (including the 0.0% one)
    for i, (xi, v) in enumerate(zip(x, values)):
        # For 0% bar, draw the label slightly above the axis
        y_label = max(v + 2.5, 4.0)
        ax.text(xi, y_label, f"{v:.1f}%", ha="center", va="bottom",
                fontsize=14, fontweight="bold", color=colors[i])

    # Annotation arrows for the deltas
    # Vanilla → Bio-Off: -18.6 pp (transferable)
    ax.annotate(
        "", xy=(1, 71.2 + 6), xytext=(0, 89.8 + 6),
        arrowprops=dict(arrowstyle="->", lw=1.8, color="#34495e"),
    )
    ax.text(0.5, 95, "−18.6 pp\ntransferable", ha="center", va="bottom",
            fontsize=10, fontweight="bold", color="#34495e",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#34495e", lw=1))

    # Bio-Off → Full: further drop (partly artifact)
    ax.annotate(
        "", xy=(2, 8), xytext=(1, 71.2 + 6),
        arrowprops=dict(arrowstyle="->", lw=1.8, color="#7f8c8d", linestyle="dashed"),
    )
    ax.text(1.55, 50, "further drop\n(partly artifact)", ha="center", va="center",
            fontsize=9, fontstyle="italic", color="#7f8c8d",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#7f8c8d", lw=1))

    ax.set_xticks(x)
    ax.set_xticklabels(systems, fontsize=10)
    ax.set_ylabel("Attack Success Rate (%)", fontsize=11)
    ax.set_ylim(0, 110)
    ax.set_title("Ablation Study — 510-vector Simulated Benchmark",
                 fontweight="bold", pad=14)

    # Light grid on y-axis only
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(str(FIG_DIR / "fig_2_ablation.png"), dpi=300,
                facecolor="white", edgecolor="none")
    plt.close(fig)


def _draw_baseline_comparison() -> None:
    """Custom baseline comparison with explicit value labels and a
    note that LLD's number is on a much smaller sample."""
    apply_style()

    systems = [
        "Undefended\n(public HarmBench)",
        "LlamaGuard\n(Inan et al.)",
        "RAIN\n(Li et al.)",
        "LLD live-LLM\n(refusal-corrected)",
    ]
    values = [78.0, 12.0, 11.0, 1.0]
    colors = ["#c0392b", "#e67e22", "#e67e22", "#27ae60"]

    fig, ax = plt.subplots(figsize=(10.0, 5.5))
    x = list(range(len(systems)))
    bars = ax.bar(x, values, color=colors, alpha=0.88, width=0.55,
                  edgecolor="white", linewidth=1.5)

    for xi, v, col in zip(x, values, colors):
        ax.text(xi, v + 1.5, f"{v:.0f}%", ha="center", va="bottom",
                fontsize=13, fontweight="bold", color=col)

    # Caveat note inside the plot area
    ax.text(
        3, 35,
        "n = 100 vectors\nvs published numbers\non larger samples",
        ha="center", va="center",
        fontsize=8, fontstyle="italic", color="#7f8c8d",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor="#bdc3c7", lw=1),
    )

    ax.set_xticks(x)
    ax.set_xticklabels(systems, fontsize=10)
    ax.set_ylabel("Attack Success Rate (%)", fontsize=11)
    ax.set_ylim(0, 95)
    ax.set_title("Live-LLM ASR vs Published Defenses (small sample)",
                 fontweight="bold", pad=14)
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(str(FIG_DIR / "fig_3_baseline_comparison.png"), dpi=300,
                facecolor="white", edgecolor="none")
    plt.close(fig)


def main() -> None:
    set_style("academic")

    print(f"writing figures to {FIG_DIR}")

    # ── Figure 1: Architecture (4-layer defense stack) ──────────────────────
    print("  fig_1_architecture.png")
    system_overview(
        layers=[
            {
                "name": "L4 — MTD",
                "components": ["Endpoint rotation", "Model rotation", "Prompt rotation"],
            },
            {
                "name": "L3 — InfoSec",
                "components": ["Input sanitize", "Error masking", "DP noise"],
            },
            {
                "name": "L2 — Antifragile",
                "components": ["Immune memory", "Pattern learner", "Hormesis cap"],
            },
            {
                "name": "L1 — Proven core",
                "components": ["Pydantic schema", "Invariants", "Jailbreak detector"],
            },
        ],
        title="Layered LLM Defense — Four-Layer Architecture",
        output_path=str(FIG_DIR / "fig_1_architecture.png"),
    )

    # ── Figure 2: Ablation result (the headline) ────────────────────────────
    print("  fig_2_ablation.png")
    _draw_ablation_chart()

    # ── Figure 3: Baseline comparison (LLD vs published numbers) ────────────
    print("  fig_3_baseline_comparison.png")
    _draw_baseline_comparison()

    # ── Figure 4: Per-layer latency breakdown ───────────────────────────────
    print("  fig_4_layer_latency.png")
    benchmark_bars(
        systems=[
            "fragmenter",
            "microbiome",
            "L1 formal",
            "L2 antifragile",
            "L4 MTD",
            "response strategy",
            "OODA",
            "L3 infosec",
            "correlation",
            "fever check",
        ],
        metrics={"Mean latency (ms)": [0.87, 0.51, 0.15, 0.16, 0.09, 0.04, 0.06, 0.01, 0.01, 0.01]},
        title="Per-Layer Latency Breakdown — Full Pipeline ≈ 2.22 ms",
        ylabel="Latency (ms)",
        horizontal=True,
        output_path=str(FIG_DIR / "fig_4_layer_latency.png"),
        figsize=(9.0, 5.5),
    )

    print()
    print("done. Generated files:")
    for p in sorted(FIG_DIR.glob("*.png")):
        size_kb = p.stat().st_size / 1024
        print(f"  {p.name}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
