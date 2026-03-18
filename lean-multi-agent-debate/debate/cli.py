"""
Lean Multi-Agent Debate Engine v1.4
Usage: debate --problem "YOUR PROBLEM HERE"
       debate --problem "..." --mode deep
       debate stats | list | resolve
"""

import argparse
import asyncio
import sys
import time
import uuid

from rich.console import Console

from .debate_manager import (
    DebateManager,
    calculate_agreement_score,
    compute_calibration_stats,
    load_calibration_history,
    save_calibration_history,
)
from .models import DebateResult
from .output_formatter import OutputFormatter

console = Console()


# ── Mode presets ──────────────────────────────────────────────────────────────

_PRESETS: dict[str, dict] = {
    "quick": {
        "rounds": 1, "adversarial": False, "grounded": False, "multi_turn": False,
        "judge": False, "moa": False, "fact_check": False, "decompose": False,
        "arg_graph": False, "delphi_rounds": 0, "calibrate": False,
        "_label": "quick (~30s, ~$0.03)",
    },
    "standard": {
        "rounds": 1, "adversarial": False, "grounded": False, "multi_turn": False,
        "judge": True, "moa": False, "fact_check": True, "decompose": False,
        "arg_graph": False, "delphi_rounds": 0, "calibrate": False,
        "_label": "standard (~60s, ~$0.08)",
    },
    "deep": {
        "rounds": 2, "adversarial": False, "grounded": False, "multi_turn": True,
        "judge": True, "moa": False, "fact_check": True, "decompose": True,
        "arg_graph": True, "delphi_rounds": 0, "calibrate": True,
        "_label": "deep (~120s, ~$0.25)",
    },
}


def _apply_preset(args: "argparse.Namespace") -> "argparse.Namespace":
    """Override flag defaults with preset values (only if flag not explicitly set)."""
    if not hasattr(args, "mode") or not args.mode:
        return args
    preset = _PRESETS.get(args.mode, {})
    for key, val in preset.items():
        if key.startswith("_"):
            continue
        if not getattr(args, key, False):  # only override if still at default
            setattr(args, key, val)
    return args


# ── Cost estimate ─────────────────────────────────────────────────────────────

def _estimate_cost(
    rounds: int = 1, moa: bool = False, fact_check: bool = False,
    decompose: bool = False, arg_graph: bool = False, delphi_rounds: int = 0,
    judge: bool = False, calibrate: bool = False, **_kwargs,
) -> tuple[float, int]:
    """Returns (estimated_usd, estimated_seconds). Very rough."""
    # Base: Phase 1 (Gemini) + Phase 2 (Claude) + Phase 3 (Claude)
    base_usd = 0.04
    base_s = 30
    if rounds > 1:
        base_usd += (rounds - 1) * 0.01
        base_s += (rounds - 1) * 10
    if moa:          base_usd += 0.01; base_s += 5
    if fact_check:   base_usd += 0.02; base_s += 15
    if decompose:    base_usd += 0.01; base_s += 10
    if arg_graph:    base_usd += 0.02; base_s += 15
    if delphi_rounds > 0:
        base_usd += delphi_rounds * 0.03; base_s += delphi_rounds * 20
    if judge:        base_usd += 0.02; base_s += 15
    if calibrate:    base_usd += 0.01; base_s += 10
    return round(base_usd, 3), base_s


async def run_debate(
    problem: str,
    mock_gemini: bool = False,
    save: bool = False,
    rounds: int = 1,
    thinking_model: str | None = None,
    pro_model: str | None = None,
    # v1.2
    adversarial: bool = False,
    grounded: bool = False,
    multi_turn: bool = False,
    judge: bool = False,
    # v1.3 Tier-1
    moa: bool = False,
    fact_check: bool = False,
    decompose: bool = False,
    # v1.3 Tier-2
    arg_graph: bool = False,
    delphi_rounds: int = 0,
    calibrate: bool = False,
    # v1.4
    context_text: str = "",
    # v1.6
    persona: str = "",
    # v1.9
    debate_format: str = "prose",
) -> None:
    debate_id = f"debate-{uuid.uuid4().hex[:8]}"

    # Show cost estimate
    est_usd, est_s = _estimate_cost(
        rounds=rounds, moa=moa, fact_check=fact_check, decompose=decompose,
        arg_graph=arg_graph, delphi_rounds=delphi_rounds, judge=judge, calibrate=calibrate,
    )
    mock_note = " [dim](mock — no real API costs)[/dim]" if mock_gemini else ""
    console.print(f"  [dim]Estimated: ~{est_s}s · ~${est_usd:.2f}{'' if not mock_gemini else ' (mock)'}[/dim]")

    mgr = DebateManager(
        mock_gemini=mock_gemini,
        max_rounds=rounds,
        thinking_model=thinking_model,
        pro_model=pro_model,
        adversarial=adversarial,
        grounded=grounded,
        multi_turn=multi_turn,
        judge=judge,
        moa=moa,
        fact_check=fact_check,
        decompose=decompose,
        arg_graph=arg_graph,
        delphi_rounds=delphi_rounds,
        calibrate=calibrate,
        context_text=context_text,
        persona=persona,
        debate_format=debate_format,
    )
    fmt = OutputFormatter()

    fmt.print_header(problem)
    start = time.monotonic()

    # ── Feature flags display ─────────────────────────────────────────────────
    flags = []
    if adversarial:    flags.append("[red]adversarial[/red]")
    if grounded:       flags.append("[cyan]grounded[/cyan]")
    if multi_turn:     flags.append("[yellow]multi-turn[/yellow]")
    if judge:          flags.append("[red]judge[/red]")
    if moa:            flags.append("[magenta]MoA[/magenta]")
    if fact_check:     flags.append("[yellow]fact-check[/yellow]")
    if decompose:      flags.append("[cyan]decompose[/cyan]")
    if arg_graph:      flags.append("[blue]arg-graph[/blue]")
    if delphi_rounds:  flags.append(f"[cyan]delphi×{delphi_rounds}[/cyan]")
    if calibrate:      flags.append("[magenta]calibrate[/magenta]")
    if flags:
        console.print(f"  [dim]Active extensions: {' · '.join(flags)}[/dim]\n")

    # ── Phase 0: Problem Decomposition (optional) ─────────────────────────────
    decomposition = None
    if decompose:
        console.print("[dim]  Running Phase 0: Claude Opus problem decomposition...[/dim]")
        decomposition = await mgr.decompose_problem(problem)
        fmt.print_decomposition(decomposition)

    # ── Phase 1: Initial Thesis ───────────────────────────────────────────────
    delphi_process = None
    if delphi_rounds > 0:
        console.print(f"[dim]  Running Phase 1: Delphi iterative refinement ({delphi_rounds} rounds)...[/dim]")
        logical, factual, delphi_process = await mgr.run_delphi(problem, decomposition=decomposition)
        fmt.print_delphi_process(delphi_process)
        fmt.print_phase1(logical, factual)
    else:
        phase1_label = "PRO/CONTRA (adversarial)" if adversarial else "Gemini Thinking + Pro"
        moa_note = " [MoA ×2 + Claude aggregation]" if moa else ""
        grounded_note = " + Google Search grounding" if grounded else ""
        console.print(f"[dim]  Running Phase 1: {phase1_label}{moa_note}{grounded_note} in parallel...[/dim]")
        logical, factual = await mgr.get_initial_takes(problem, decomposition=decomposition)
        fmt.print_phase1(logical, factual)

    # ── Phase 1.5: Claim-Level Fact-Check (optional) ─────────────────────────
    fact_check_result = None
    if fact_check:
        console.print("[dim]  Running Phase 1.5: Claude Opus claim-level fact-check...[/dim]")
        fact_check_result = await mgr.run_fact_check(problem, logical, factual)
        fmt.print_fact_check(fact_check_result)

    # ── Phase 1.6: Argument Graph (optional) ─────────────────────────────────
    argument_graph = None
    if arg_graph:
        console.print("[dim]  Running Phase 1.6: Claude Opus structured argument graph...[/dim]")
        argument_graph = await mgr.build_argument_graph(problem, logical, factual)
        fmt.print_argument_graph(argument_graph)

    # ── Calibration: Extract probabilistic claims (optional) ─────────────────
    calibration_record = None
    if calibrate:
        console.print("[dim]  Extracting calibration claims...[/dim]")
        calibration_record = await mgr.extract_calibration(
            debate_id, problem, logical, factual, fact_check=fact_check_result
        )
        history = load_calibration_history()
        history_stats = compute_calibration_stats(history) if history else None
        fmt.print_calibration(calibration_record, history_stats=history_stats)
        save_calibration_history(calibration_record)

    # ── Phase 2: Adversarial Critique Loop ───────────────────────────────────
    rounds_label = f"{rounds} round{'s' if rounds > 1 else ''}"
    multi_turn_note = " + Gemini rebuttal" if multi_turn else ""
    console.print(f"[dim]  Running Phase 2: Claude Opus adversarial critique ({rounds_label}, converges at 0.8){multi_turn_note}...[/dim]")
    synthesis, rebuttal, verification = await mgr.run_critique_loop(
        problem, logical, factual, fact_check=fact_check_result
    )

    fmt.print_contradictions(synthesis.contradictions)
    if rebuttal is not None:
        fmt.print_rebuttal(rebuttal)
    fmt.print_critique(synthesis, verification)

    # ── Phase 3: Final Consensus ──────────────────────────────────────────────
    console.print("[dim]  Running Phase 3: Claude Opus final consensus answer...[/dim]")
    final = await mgr.get_final_answer(
        problem, logical, factual, synthesis, verification,
        rebuttal=rebuttal, fact_check=fact_check_result
    )
    fmt.print_final(final)

    elapsed = time.monotonic() - start
    console.print(f"  [dim]Total latency: {elapsed:.1f}s[/dim]\n")

    # ── Phase 4: Skeptical Judge (optional) ──────────────────────────────────
    judge_verdict = None
    if judge:
        console.print("[dim]  Running Phase 4: Claude Opus skeptical judge...[/dim]")
        judge_verdict = await mgr.get_judge_verdict(
            problem, logical, factual, synthesis, verification, final,
            rebuttal=rebuttal, fact_check=fact_check_result
        )
        fmt.print_judge(judge_verdict)

    result = DebateResult(
        problem=problem,
        decomposition=decomposition,
        logical_analysis=logical,
        factual_context=factual,
        fact_check=fact_check_result,
        argument_graph=argument_graph,
        delphi_process=delphi_process,
        calibration=calibration_record,
        critique=synthesis,
        rebuttal=rebuttal,
        verification=verification,
        final_answer=final,
        judge=judge_verdict,
    )

    if save:
        report_path = fmt.save_report(result, elapsed)
        console.print(f"  [green]Report saved:[/green] [dim]{report_path}[/dim]\n")


def _cmd_resolve(debate_id: str, claim_idx: int, outcome: bool, note: str = "") -> None:
    """Mark a calibration claim as resolved (outcome known)."""
    import json
    from pathlib import Path

    history_file = Path("output/calibration_history.jsonl")
    if not history_file.exists():
        print(json.dumps({"error": "No calibration_history.jsonl found."}))
        return

    lines = history_file.read_text().splitlines()
    updated = 0
    new_lines = []
    for line in lines:
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("debate_id") == debate_id:
            claims = record.get("claims", [])
            if 0 <= claim_idx < len(claims):
                claims[claim_idx]["outcome"] = outcome
                claims[claim_idx]["outcome_note"] = note
                updated += 1
            record["claims"] = claims
        new_lines.append(json.dumps(record))

    history_file.write_text("\n".join(new_lines) + "\n")
    if updated:
        print(json.dumps({"status": "updated", "debate_id": debate_id, "claim_idx": claim_idx, "outcome": outcome}))
    else:
        print(json.dumps({"error": f"Claim {claim_idx} in debate {debate_id} not found."}))


def _cmd_stats() -> None:
    """Print calibration history statistics."""
    import json
    from .debate_manager import load_calibration_history, compute_calibration_stats
    history = load_calibration_history()
    if not history:
        print(json.dumps({"total_debates": 0, "total_claims": 0, "message": "No calibration history found."}))
        return
    stats = compute_calibration_stats(history)
    print(json.dumps(stats, indent=2))


def _cmd_list() -> None:
    """List saved debate reports in output/."""
    import json
    from pathlib import Path
    output_dir = Path("output")
    if not output_dir.exists():
        print(json.dumps([]))
        return
    reports = []
    for report_file in sorted(output_dir.rglob("*_report.md"), reverse=True):
        reports.append({
            "path": str(report_file),
            "name": report_file.name,
            "folder": report_file.parent.name,
            "size_bytes": report_file.stat().st_size,
        })
    print(json.dumps(reports, indent=2))


def _cmd_compare(argv: list[str]) -> None:
    """
    Run sycophancy comparison: Gemini×Claude vs Claude×Claude (mock).
    Passes remaining argv directly to benchmarks/sycophancy_compare.py.

    Usage:
      debate compare [--mock-only] [--problems N] [--ids f01,c02] [--all]
                     [--problem "..."] [--output path.json]
    """
    import subprocess
    from pathlib import Path
    script = Path(__file__).parent.parent / "benchmarks" / "sycophancy_compare.py"
    result = subprocess.run(
        [sys.executable, str(script)] + argv,
        cwd=Path(__file__).parent.parent,
    )
    sys.exit(result.returncode)


def main() -> None:
    # Handle special subcommands before full argument parsing
    if len(sys.argv) > 1 and sys.argv[1] == "compare":
        _cmd_compare(sys.argv[2:])
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("stats", "list"):
        {"stats": _cmd_stats, "list": _cmd_list}[sys.argv[1]]()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        # debate resolve <debate_id> <claim_idx> <true|false> [note]
        if len(sys.argv) < 5:
            print('Usage: debate resolve <debate_id> <claim_index> <true|false> ["optional note"]')
            sys.exit(1)
        outcome_str = sys.argv[4].lower()
        if outcome_str not in ("true", "false", "1", "0", "yes", "no"):
            print("outcome must be: true/false/yes/no/1/0")
            sys.exit(1)
        outcome_bool = outcome_str in ("true", "1", "yes")
        note = sys.argv[5] if len(sys.argv) > 5 else ""
        _cmd_resolve(sys.argv[2], int(sys.argv[3]), outcome_bool, note)
        return

    parser = argparse.ArgumentParser(
        description="Lean Multi-Agent Debate Engine v1.4 — Gemini × Claude Opus adversarial discourse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  debate --problem "Is RSA-2048 a quantum threat in 5 years?"
  debate --problem "..." --mode standard
  debate --problem "..." --mode deep --save
  debate --problem "..." --context "Our company uses RSA-2048 for internal PKI."
  debate --problem "..." --adversarial --grounded --multi-turn --judge --moa --fact-check

Subcommands:
  debate stats                              Show calibration history stats
  debate list                               List saved reports
  debate resolve <id> <idx> <true|false>    Mark a calibration claim as resolved

Required environment variables (in .env file):
  ANTHROPIC_API_KEY=sk-ant-...
  GOOGLE_API_KEY=AIza...

Note: --mode overrides individual flags with sensible presets.
      --delphi and --moa are alternative Phase 1 modes.
        """,
    )
    parser.add_argument("--problem", required=True, help="The problem or question to debate")
    parser.add_argument("--mock-gemini", action="store_true", help="Replace Gemini with Claude for testing")
    parser.add_argument("--save", action="store_true", help="Save full debate report as Markdown")
    parser.add_argument("--rounds", type=int, default=1, metavar="N",
                        help="Max critique-verification rounds in Phase 2 (default: 1)")
    parser.add_argument("--thinking-model", default=None, metavar="MODEL_ID")
    parser.add_argument("--pro-model", default=None, metavar="MODEL_ID")

    # v1.2 flags
    parser.add_argument("--adversarial", action="store_true",
                        help="[v1.2] Force PRO/CONTRA role-locked positions")
    parser.add_argument("--grounded", action="store_true",
                        help="[v1.2] Google Search grounding for Gemini Pro")
    parser.add_argument("--multi-turn", action="store_true",
                        help="[v1.2] Gemini rebuttal after Claude critique (Phase 2b)")
    parser.add_argument("--judge", action="store_true",
                        help="[v1.2] Independent skeptical judge (Phase 4)")

    # v1.3 Tier-1 flags
    parser.add_argument("--moa", action="store_true",
                        help="[T1] Mixture of Agents: both Gemini models per role, Claude aggregates")
    parser.add_argument("--fact-check", action="store_true",
                        help="[T1] Claim-level fact-checking after Phase 1 (Phase 1.5)")
    parser.add_argument("--decompose", action="store_true",
                        help="[T1] Automatic problem decomposition into sub-questions (Phase 0)")

    # v1.3 Tier-2 flags
    parser.add_argument("--arg-graph", action="store_true",
                        help="[T2] Structured argument graph with formal logic mapping (Phase 1.6)")
    parser.add_argument("--delphi", type=int, default=0, metavar="N",
                        help="[T2] Delphi iterative refinement: N rounds (1-5, replaces standard Phase 1)")
    parser.add_argument("--calibrate", action="store_true",
                        help="[T2] Extract probabilistic claims, persist to calibration_history.jsonl")

    # v1.4 flags
    parser.add_argument("--mode", choices=["quick", "standard", "deep"], default=None,
                        help="[v1.4] Preset: quick (~30s), standard (~60s), deep (~120s). Overrides individual flags.")
    parser.add_argument("--context", type=str, default="", metavar="TEXT",
                        help="[v1.4] Additional context/document text injected into all prompts")
    parser.add_argument("--persona", type=str, default="", metavar="DOMAIN",
                        help="[v1.6] Domain expert persona for Gemini agents (e.g. cybersecurity, finance, medicine, technology, policy, science, or any free-form domain)")
    parser.add_argument("--format", choices=["prose", "toulmin"], default="prose",
                        help="[v1.9] Phase 1 argument format: prose (default) or toulmin (structured Claim/Grounds/Warrant/Qualifier/Rebuttal)")

    args = parser.parse_args()
    args = _apply_preset(args)

    if not args.problem.strip():
        console.print("[red]Error: --problem cannot be empty.[/red]")
        sys.exit(1)
    if args.rounds < 1 or args.rounds > 5:
        console.print("[red]Error: --rounds must be between 1 and 5.[/red]")
        sys.exit(1)
    if args.delphi < 0 or args.delphi > 5:
        console.print("[red]Error: --delphi must be between 0 and 5.[/red]")
        sys.exit(1)

    try:
        asyncio.run(run_debate(
            args.problem.strip(),
            mock_gemini=args.mock_gemini,
            save=args.save,
            rounds=args.rounds,
            thinking_model=args.thinking_model,
            pro_model=args.pro_model,
            adversarial=args.adversarial,
            grounded=args.grounded,
            multi_turn=args.multi_turn,
            judge=args.judge,
            moa=args.moa,
            fact_check=args.fact_check,
            decompose=args.decompose,
            arg_graph=args.arg_graph,
            delphi_rounds=args.delphi,
            calibrate=args.calibrate,
            context_text=args.context,
            persona=args.persona,
            debate_format=args.format,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Debate interrupted.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
