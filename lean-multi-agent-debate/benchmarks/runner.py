"""
Benchmark runner for the Lean Multi-Provider Debate Engine.

Usage:
    # API-free run using mock Gemini (Claude substitutes):
    python benchmarks/runner.py --problems 5 --mock

    # Specific category:
    python benchmarks/runner.py --category factual --mock

    # Full benchmark (requires API keys):
    python benchmarks/runner.py --all

    # Specific problem IDs:
    python benchmarks/runner.py --ids f01,f02,t01 --mock
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmarks.datasets import BENCHMARK_PROBLEMS, get_problems_by_category, get_problem_by_id
from benchmarks.metrics import BenchmarkReport, DebateMetrics
from debate.debate_manager import DebateManager


async def run_single(problem_spec: dict, mock: bool) -> DebateMetrics:
    """Run a single benchmark debate and collect metrics."""
    mgr = DebateManager(mock_gemini=mock)
    start = time.monotonic()

    logical, factual = await mgr.get_initial_takes(problem_spec["problem"])
    synthesis, rebuttal, verification = await mgr.run_critique_loop(
        problem_spec["problem"], logical, factual
    )
    final = await mgr.get_final_answer(
        problem_spec["problem"], logical, factual, synthesis, verification
    )

    elapsed = time.monotonic() - start

    return DebateMetrics(
        problem_id=problem_spec["id"],
        problem=problem_spec["problem"],
        category=problem_spec["category"],
        latency_s=elapsed,
        consensus_score=final.consensus_score,
        agreement_score=synthesis.agreement_score,
        confidence=final.confidence,
        verification_passed=verification.verified,
        n_contradictions=len(synthesis.contradictions),
        mock=mock,
    )


async def run_benchmark(problems: list[dict], mock: bool) -> BenchmarkReport:
    """Run all problems sequentially (to avoid rate limits) and collect metrics."""
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn

    console = Console()
    report = BenchmarkReport()

    console.print(f"\n[bold]Running {len(problems)} benchmark problems[/bold]"
                  f" [dim]({'mock' if mock else 'live API'})[/dim]\n")

    for i, prob in enumerate(problems, 1):
        console.print(f"  [{i}/{len(problems)}] [{prob['category']}] {prob['problem'][:70]}...")
        try:
            metrics = await run_single(prob, mock=mock)
            report.add(metrics)
            console.print(
                f"         [green]✓[/green] consensus={metrics.consensus_score:.1%}"
                f"  agreement={metrics.agreement_score:.1%}"
                f"  latency={metrics.latency_s:.1f}s"
            )
        except Exception as e:
            console.print(f"         [red]✗ Error: {e}[/red]")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Debate Engine Benchmark Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmarks/runner.py --problems 5 --mock
  python benchmarks/runner.py --category factual --mock
  python benchmarks/runner.py --ids f01,t01,c02 --mock
  python benchmarks/runner.py --all  # requires API keys
        """,
    )
    parser.add_argument("--mock", action="store_true", default=False,
                        help="Use mock Gemini (Claude substitutes) — no GOOGLE_API_KEY needed")
    parser.add_argument("--problems", type=int, default=0, metavar="N",
                        help="Run first N problems from the dataset")
    parser.add_argument("--category", choices=["factual", "controversial", "technical"],
                        help="Run only problems from a specific category")
    parser.add_argument("--ids", type=str, default="",
                        help="Comma-separated problem IDs (e.g. f01,t02,c03)")
    parser.add_argument("--all", action="store_true",
                        help="Run all 15 benchmark problems")
    parser.add_argument("--output", type=str, default="",
                        help="Save JSON results to this file path")

    args = parser.parse_args()

    # Select problems
    if args.ids:
        ids = [i.strip() for i in args.ids.split(",")]
        problems = [p for pid in ids if (p := get_problem_by_id(pid)) is not None]
        if not problems:
            print(f"No matching problem IDs: {ids}", file=sys.stderr)
            sys.exit(1)
    elif args.category:
        problems = get_problems_by_category(args.category)
    elif args.all:
        problems = BENCHMARK_PROBLEMS
    elif args.problems > 0:
        problems = BENCHMARK_PROBLEMS[:args.problems]
    else:
        # Default: 3 problems (one per category)
        problems = [BENCHMARK_PROBLEMS[0], BENCHMARK_PROBLEMS[5], BENCHMARK_PROBLEMS[10]]

    report = asyncio.run(run_benchmark(problems, mock=args.mock))
    report.print_summary()

    if args.output:
        results = {
            "summary": report.summary(),
            "runs": [m.to_dict() for m in report.runs],
        }
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"\nResults saved: {args.output}")


if __name__ == "__main__":
    main()
