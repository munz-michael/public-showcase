"""
Benchmark metrics for the debate engine.

Collected per debate run:
  - LatencyMetric: wall-clock seconds per debate
  - AgreementMetric: consensus_score, agreement_score, confidence
  - CategoryMetrics: aggregate stats grouped by problem category
"""

from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Optional


@dataclass
class DebateMetrics:
    """Metrics captured from a single debate run."""
    problem_id: str
    problem: str
    category: str
    latency_s: float
    consensus_score: float
    agreement_score: float
    confidence: float
    verification_passed: bool
    n_contradictions: int
    mock: bool

    @property
    def passed_consensus_threshold(self) -> bool:
        return self.consensus_score >= 0.5

    def to_dict(self) -> dict:
        return {
            "problem_id": self.problem_id,
            "category": self.category,
            "latency_s": round(self.latency_s, 2),
            "consensus_score": round(self.consensus_score, 3),
            "agreement_score": round(self.agreement_score, 3),
            "confidence": round(self.confidence, 3),
            "verification_passed": self.verification_passed,
            "n_contradictions": self.n_contradictions,
            "mock": self.mock,
        }


@dataclass
class BenchmarkReport:
    """Aggregated report across multiple debate runs."""
    runs: list[DebateMetrics] = field(default_factory=list)

    def add(self, m: DebateMetrics) -> None:
        self.runs.append(m)

    @property
    def n(self) -> int:
        return len(self.runs)

    @property
    def avg_latency(self) -> float:
        return mean(r.latency_s for r in self.runs) if self.runs else 0.0

    @property
    def avg_consensus(self) -> float:
        return mean(r.consensus_score for r in self.runs) if self.runs else 0.0

    @property
    def avg_agreement(self) -> float:
        return mean(r.agreement_score for r in self.runs) if self.runs else 0.0

    @property
    def verification_pass_rate(self) -> float:
        if not self.runs:
            return 0.0
        return sum(1 for r in self.runs if r.verification_passed) / len(self.runs)

    def by_category(self) -> dict[str, "BenchmarkReport"]:
        cats: dict[str, "BenchmarkReport"] = {}
        for r in self.runs:
            cats.setdefault(r.category, BenchmarkReport()).add(r)
        return cats

    def summary(self) -> dict:
        if not self.runs:
            return {"n": 0}

        latencies = [r.latency_s for r in self.runs]
        consensuses = [r.consensus_score for r in self.runs]

        result: dict = {
            "n_runs": self.n,
            "avg_latency_s": round(self.avg_latency, 2),
            "max_latency_s": round(max(latencies), 2),
            "avg_consensus": round(self.avg_consensus, 3),
            "avg_agreement": round(self.avg_agreement, 3),
            "verification_pass_rate": round(self.verification_pass_rate, 3),
            "consensus_stddev": round(stdev(consensuses), 3) if len(consensuses) > 1 else 0.0,
        }

        # Per-category breakdown
        result["by_category"] = {
            cat: {
                "n": len(rep.runs),
                "avg_consensus": round(rep.avg_consensus, 3),
                "avg_latency_s": round(rep.avg_latency, 2),
            }
            for cat, rep in self.by_category().items()
        }

        return result

    def print_summary(self) -> None:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        s = self.summary()

        console.print(f"\n[bold cyan]Benchmark Results — {s['n_runs']} runs[/bold cyan]")
        console.print(f"  Avg latency:      [cyan]{s['avg_latency_s']:.1f}s[/cyan]")
        console.print(f"  Avg consensus:    [green]{s['avg_consensus']:.1%}[/green]")
        console.print(f"  Avg agreement:    [green]{s['avg_agreement']:.1%}[/green]")
        console.print(f"  Verification ✓:   [green]{s['verification_pass_rate']:.1%}[/green]")

        if "by_category" in s:
            table = Table(header_style="bold", border_style="dim")
            table.add_column("Category")
            table.add_column("N", justify="right")
            table.add_column("Avg Consensus", justify="right")
            table.add_column("Avg Latency", justify="right")
            for cat, stats in s["by_category"].items():
                table.add_row(
                    cat,
                    str(stats["n"]),
                    f"{stats['avg_consensus']:.1%}",
                    f"{stats['avg_latency_s']:.1f}s",
                )
            console.print(table)
