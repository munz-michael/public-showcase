"""
Ablation Study Harness for Layered LLM Defense.

Compares three defense configurations on the same attack suite to isolate
the contribution of biologically-inspired components:

  1. LLD-Vanilla    — only Layer 1 (Pydantic + InvariantMonitor) + Layer 3 (sanitize)
                      No bio components, no correlation, no anomaly score, no fragmenter,
                      no response strategy, no fever, no microbiome, no SAL, no ooda.
  2. LLD-Bio-Off    — full pipeline EXCEPT bio components (Microbiome, Fever, Hormesis,
                      HerdImmunity, AutoHealing). Keeps correlation, fragmenter, OODA,
                      response strategy, watermark.
  3. LLD-Full       — everything enabled (current production config).

The differences in ASR / FPR / latency / token-savings between these three
configs measure the actual contribution of each architectural choice.

Run:
    python3 -m lld.ablation
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from .benchmark_harmbench import (
    AttackVector,
    HarmBenchReport,
    HarmBenchRunner,
    SimulatedLLMJudge,
    build_clean_dataset,
    build_harmbench_dataset,
)
from .extended_attacks import build_extended_dataset
from .integrated_defense import IntegratedDefense, LayerTiming


# ===========================================================================
# Ablation configurations
# ===========================================================================

# Components disabled per ablation level.
ABLATION_VANILLA = {
    "microbiome", "fever", "correlation", "response_strategy",
    "fragmenter", "ooda", "fatigue", "watermark",
    "herd_immunity", "auto_healing", "startle", "layer2_anomaly",
}

ABLATION_BIO_OFF = {
    "microbiome", "fever",
    "herd_immunity", "auto_healing",
}

ABLATION_FULL: set[str] = set()


def make_defense(mode: str) -> IntegratedDefense:
    """Construct an IntegratedDefense with the given ablation level."""
    if mode == "vanilla":
        disabled = ABLATION_VANILLA
    elif mode == "bio_off":
        disabled = ABLATION_BIO_OFF
    elif mode == "full":
        disabled = ABLATION_FULL
    else:
        raise ValueError(f"Unknown ablation mode: {mode}")
    return IntegratedDefense(disabled_components=disabled)


# ===========================================================================
# Telemetry aggregation
# ===========================================================================

@dataclass
class AblationMetrics:
    """Aggregated metrics for one ablation config."""
    mode: str
    asr: float = 0.0
    blocks: int = 0
    bypasses: int = 0
    fpr: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_tokens_saved: int = 0
    asr_by_category: dict = field(default_factory=dict)
    blocks_by_layer: dict = field(default_factory=dict)
    layer_latency_avg: dict = field(default_factory=dict)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * pct / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def run_one_ablation(
    mode: str,
    attacks: list[AttackVector],
    clean: list[tuple[str, str]],
) -> AblationMetrics:
    """Run one ablation config end-to-end with telemetry."""
    defense = make_defense(mode)
    # Warmup
    warmup_responses = [out for _, out in clean[:20]] * 3
    defense.warmup(warmup_responses)

    judge = SimulatedLLMJudge()
    metrics = AblationMetrics(mode=mode)

    cat_total: dict[str, int] = {}
    cat_success: dict[str, int] = {}
    latencies: list[float] = []
    layer_latencies: dict[str, list[float]] = {}

    for i, attack in enumerate(attacks):
        sim_response = judge.respond(attack)
        result = defense.process(
            input_text=attack.input_text,
            output_text=sim_response,
            session_id=f"abl_{mode}_{i // 5}",
            request_id=f"req_{i}",
        )

        cat_total[attack.category] = cat_total.get(attack.category, 0) + 1
        latencies.append(result.timing.total)
        for fld in (
            "fever_check", "fragmenter", "layer4_mtd", "layer3_infosec",
            "layer2_antifragile", "layer1_formal", "microbiome", "correlation",
            "response_strategy", "fatigue", "ooda", "bookkeeping",
        ):
            layer_latencies.setdefault(fld, []).append(getattr(result.timing, fld))

        metrics.total_tokens_saved += result.estimated_tokens_saved

        if result.allowed:
            if judge.is_harmful(sim_response, attack.category):
                metrics.bypasses += 1
                cat_success[attack.category] = cat_success.get(attack.category, 0) + 1
        else:
            metrics.blocks += 1
            layer = result.blocked_by or "unknown"
            metrics.blocks_by_layer[layer] = metrics.blocks_by_layer.get(layer, 0) + 1

    metrics.asr = metrics.bypasses / max(len(attacks), 1)
    for cat, total in cat_total.items():
        metrics.asr_by_category[cat] = cat_success.get(cat, 0) / total

    metrics.avg_latency_ms = sum(latencies) / max(len(latencies), 1)
    metrics.p95_latency_ms = _percentile(latencies, 95)
    metrics.layer_latency_avg = {
        k: sum(v) / max(len(v), 1) for k, v in layer_latencies.items()
    }

    # FPR with FRESH defense (post-attack hormesis would skew it)
    fp_defense = make_defense(mode)
    warmup = [out for _, out in clean[:20]] * 3
    fp_defense.warmup(warmup)

    fp = 0
    for i, (inp, out) in enumerate(clean):
        r = fp_defense.process(
            input_text=inp,
            output_text=out,
            session_id=f"fpr_{mode}_{i}",
        )
        if not r.allowed:
            fp += 1
    metrics.fpr = fp / max(len(clean), 1)

    return metrics


# ===========================================================================
# Reporting
# ===========================================================================

def format_ablation_report(results: list[AblationMetrics]) -> str:
    lines = [
        "=" * 78,
        "Ablation Study — Contribution of Biological Components",
        "=" * 78,
        "",
        f"{'Config':<14}{'ASR':>8}{'Blocks':>8}{'FPR':>8}{'Avg ms':>10}{'p95 ms':>10}{'Tok saved':>12}",
        "-" * 78,
    ]
    for m in results:
        lines.append(
            f"{m.mode:<14}{m.asr*100:>7.1f}%{m.blocks:>8d}{m.fpr*100:>7.1f}%"
            f"{m.avg_latency_ms:>9.2f}{m.p95_latency_ms:>9.2f}{m.total_tokens_saved:>12d}"
        )
    lines.append("")
    lines.append("Per-category ASR:")
    cats: list[str] = []
    if results:
        cats = sorted(results[0].asr_by_category.keys())
    header = f"{'category':<25}" + "".join(f"{m.mode:>14}" for m in results)
    lines.append(header)
    lines.append("-" * len(header))
    for c in cats:
        row = f"{c:<25}"
        for m in results:
            row += f"{m.asr_by_category.get(c, 0)*100:>13.1f}%"
        lines.append(row)
    lines.append("")
    lines.append("Per-layer average latency (ms):")
    if results:
        layers = list(results[0].layer_latency_avg.keys())
        header = f"{'layer':<22}" + "".join(f"{m.mode:>14}" for m in results)
        lines.append(header)
        lines.append("-" * len(header))
        for layer in layers:
            row = f"{layer:<22}"
            for m in results:
                row += f"{m.layer_latency_avg.get(layer, 0):>14.3f}"
            lines.append(row)
    lines.append("")
    lines.append("=" * 78)
    return "\n".join(lines)


def _main():
    import sys
    use_extended = "--extended" in sys.argv or "--full" in sys.argv
    if use_extended:
        print("Building EXTENDED dataset (510 vectors incl. GCG/AutoDAN/PAIR)...")
        attacks = build_extended_dataset()
    else:
        print("Building HarmBench dataset (100 vectors)...")
        attacks = build_harmbench_dataset()
    clean = build_clean_dataset()
    print(f"  {len(attacks)} attacks, {len(clean)} clean inputs")
    print()

    results = []
    for mode in ("vanilla", "bio_off", "full"):
        print(f"Running ablation: {mode}")
        t = time.monotonic()
        m = run_one_ablation(mode, attacks, clean)
        elapsed = time.monotonic() - t
        print(f"  ASR={m.asr*100:.1f}%  FPR={m.fpr*100:.1f}%  "
              f"avg={m.avg_latency_ms:.2f}ms  ({elapsed:.1f}s)")
        results.append(m)

    print()
    print(format_ablation_report(results))

    return results


if __name__ == "__main__":
    _main()
