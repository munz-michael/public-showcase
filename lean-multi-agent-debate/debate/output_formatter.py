"""
Lean Multi-Agent Debate Engine — Rich Terminal Output

Display order (per spec: contradictions before final answer):
  1. Header
  2. Phase 1: Logical vs. Factual panels (with known_unknowns)
  3. CONTRADICTIONS  ← prominent, before final answer
  4. Claude's synthesis + [optional Gemini rebuttal] + Gemini verification
  5. Final answer + consensus score bar
  6. [Optional] Skeptical Judge verdict (Phase 4)
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .models import (
    ArgumentGraph,
    AtomicClaim,
    CalibrationRecord,
    ClaudeSynthesis,
    Contradiction,
    DebateResult,
    DelphiProcess,
    FactCheckResult,
    FinalAnswer,
    GeminiRebuttal,
    GeminiVerification,
    InitialTake,
    JudgeVerdict,
    ProblemDecomposition,
    RubricScore,
)

console = Console()


class OutputFormatter:

    def print_decomposition(self, decomposition: ProblemDecomposition) -> None:
        """Display Phase 0 problem decomposition."""
        console.print(Rule("[bold cyan]Phase 0 — Problem Decomposition[/bold cyan]"))
        console.print()

        table = Table(show_header=True, header_style="bold cyan", border_style="cyan", expand=True)
        table.add_column("#", width=3, style="dim")
        table.add_column("Aspect", width=12, style="cyan bold")
        table.add_column("Sub-Question", style="white")

        for i, sq in enumerate(decomposition.sub_questions, 1):
            table.add_row(str(i), sq.aspect.upper(), sq.question)

        complexity_color = {"simple": "green", "moderate": "yellow", "complex": "red"}.get(decomposition.complexity, "white")
        console.print(
            Panel(
                table,
                title=f"[bold cyan]Problem broken into {len(decomposition.sub_questions)} sub-questions[/bold cyan]",
                subtitle=f"[{complexity_color}]Complexity: {decomposition.complexity.upper()}[/{complexity_color}]  [dim]{decomposition.reasoning[:80]}[/dim]",
                border_style="cyan",
                padding=(0, 1),
            )
        )
        console.print()

    def print_fact_check(self, fact_check: FactCheckResult) -> None:
        """Display Phase 1.5 claim-level fact-check results."""
        console.print(Rule("[bold yellow]Phase 1.5 — Claim-Level Fact-Check[/bold yellow]"))
        console.print()

        table = Table(show_header=True, header_style="bold yellow", border_style="yellow", expand=True)
        table.add_column("Status", width=10, style="bold")
        table.add_column("Source", width=12, style="dim")
        table.add_column("Claim", style="white")
        table.add_column("Evidence", style="dim", max_width=40)

        status_styles = {"confirmed": "green", "refuted": "red", "uncertain": "yellow"}
        status_icons = {"confirmed": "✓", "refuted": "✗", "uncertain": "?"}

        for c in fact_check.claims:
            style = status_styles.get(c.status, "white")
            icon = status_icons.get(c.status, "·")
            table.add_row(
                f"[{style}]{icon} {c.status.upper()}[/{style}]",
                c.source_role[:10],
                c.claim,
                c.evidence[:80],
            )

        filled = int(fact_check.overall_reliability * 20)
        rel_bar = f"[green]{'█' * filled}{'░' * (20 - filled)}[/green] {fact_check.overall_reliability:.0%}"

        console.print(
            Panel(
                table,
                title=f"[bold yellow]Fact-Check: {fact_check.confirmed_count}✓ confirmed · {fact_check.refuted_count}✗ refuted · {fact_check.uncertain_count}? uncertain[/bold yellow]",
                border_style="yellow",
                padding=(0, 1),
            )
        )
        console.print(
            Panel(
                f"[bold]Overall Reliability:[/bold] {rel_bar}\n\n{fact_check.summary}",
                border_style="yellow",
                padding=(0, 2),
            )
        )
        console.print()

    def print_argument_graph(self, graph: ArgumentGraph) -> None:
        """Display Phase 1.6 structured argument graph."""
        console.print(Rule("[bold blue]Phase 1.6 — Structured Argument Graph[/bold blue]"))
        console.print()

        # Node table
        node_table = Table(show_header=True, header_style="bold blue", border_style="blue", expand=True)
        node_table.add_column("ID", width=4, style="bold")
        node_table.add_column("Type", width=12)
        node_table.add_column("Source", width=14, style="dim")
        node_table.add_column("Content", style="white")

        type_colors = {"premise": "cyan", "conclusion": "green", "evidence": "yellow", "assumption": "magenta"}
        for n in graph.nodes:
            color = type_colors.get(n.node_type, "white")
            node_table.add_row(n.id, f"[{color}]{n.node_type}[/{color}]", n.source_role[:12], n.content)

        # Edge table
        edge_table = Table(show_header=True, header_style="bold blue", border_style="blue", expand=True)
        edge_table.add_column("From", width=5, style="bold")
        edge_table.add_column("Relation", width=12)
        edge_table.add_column("To", width=5, style="bold")

        edge_colors = {"supports": "green", "derives": "cyan", "contradicts": "red"}
        edge_icons = {"supports": "→", "derives": "⇒", "contradicts": "⚡"}
        for e in graph.edges:
            color = edge_colors.get(e.edge_type, "white")
            icon = edge_icons.get(e.edge_type, "→")
            edge_table.add_row(e.from_id, f"[{color}]{icon} {e.edge_type}[/{color}]", e.to_id)

        n_contradictions = len(graph.contradiction_edges)
        contradiction_note = f"  [red]⚡ {n_contradictions} contradiction(s) in argument chains[/red]" if n_contradictions else "  [green]No structural contradictions[/green]"

        console.print(Panel(node_table, title="[bold blue]Argument Nodes[/bold blue]", border_style="blue", padding=(0, 1)))
        console.print()
        console.print(Panel(edge_table, title="[bold blue]Argument Edges[/bold blue]", border_style="blue", padding=(0, 1)))
        console.print(contradiction_note)
        console.print(f"\n  [dim]{graph.summary}[/dim]")
        console.print()

    def print_delphi_process(self, delphi: DelphiProcess) -> None:
        """Display Delphi iterative refinement process."""
        console.print(Rule("[bold cyan]Phase 1 — Delphi Iterative Refinement[/bold cyan]"))
        console.print()

        table = Table(show_header=True, header_style="bold cyan", border_style="cyan", expand=True)
        table.add_column("Round", width=6, style="bold", justify="center")
        table.add_column("Analysis A Confidence", justify="center")
        table.add_column("Analysis B Confidence", justify="center")
        table.add_column("Δ Delta", width=8, justify="center")
        table.add_column("Status", width=12)

        for rnd in delphi.rounds:
            delta_str = f"{rnd.delta:.3f}" if rnd.round_n > 1 else "—"
            delta_color = "green" if rnd.delta < 0.05 else "yellow" if rnd.delta < 0.15 else "red"
            converged_note = "[green]converged[/green]" if (delphi.convergence_round == rnd.round_n) else ""
            table.add_row(
                str(rnd.round_n),
                f"{rnd.confidence_a:.0%}",
                f"{rnd.confidence_b:.0%}",
                f"[{delta_color}]{delta_str}[/{delta_color}]",
                converged_note,
            )

        status = f"[green]Converged at round {delphi.convergence_round}[/green]" if delphi.converged else f"[yellow]Ran all {len(delphi.rounds)} rounds[/yellow]"
        console.print(Panel(
            table,
            title=f"[bold cyan]Delphi Process — {len(delphi.rounds)} Rounds[/bold cyan]",
            subtitle=status,
            border_style="cyan",
            padding=(0, 1),
        ))
        console.print()

    def print_calibration(self, record: CalibrationRecord, history_stats: dict | None = None) -> None:
        """Display calibration claims and optional historical stats."""
        console.print(Rule("[bold magenta]Calibration Tracking — Probabilistic Claims[/bold magenta]"))
        console.print()

        table = Table(show_header=True, header_style="bold magenta", border_style="magenta", expand=True)
        table.add_column("Model", width=14, style="dim")
        table.add_column("Claim", style="white")
        table.add_column("Prob", width=6, justify="center")
        table.add_column("90% CI", width=14, justify="center", style="dim")
        table.add_column("Horizon", width=10, style="dim")

        for c in record.claims:
            prob_color = "green" if c.probability >= 0.7 else "red" if c.probability <= 0.3 else "yellow"
            table.add_row(
                c.model_id[:12],
                c.claim[:60],
                f"[{prob_color}]{c.probability:.0%}[/{prob_color}]",
                f"[{c.ci_lower:.0%}, {c.ci_upper:.0%}]",
                c.time_horizon,
            )

        alignment_note = ""
        if record.fact_check_alignment is not None:
            alignment_note = f"\n  Fact-check alignment: {record.fact_check_alignment:.0%} of claims consistent"

        console.print(Panel(
            table,
            title=f"[bold magenta]{len(record.claims)} Probabilistic Claims Extracted[/bold magenta]",
            subtitle=f"[dim]Saved to calibration_history.jsonl[/dim]",
            border_style="magenta",
            padding=(0, 1),
        ))
        if alignment_note:
            console.print(alignment_note)

        if history_stats and history_stats.get("total_debates", 0) > 1:
            console.print(f"\n  [dim]Historical calibration: {history_stats['total_debates']} debates, "
                         f"{history_stats['total_claims']} total claims tracked[/dim]")
        console.print()

    def print_header(self, problem: str) -> None:
        console.print()
        console.print(
            Panel(
                f"[bold white]{problem}[/bold white]",
                title="[bold cyan]Lean Multi-Agent Debate Engine v1.2[/bold cyan]",
                subtitle="[dim]Gemini 3 Thinking + Pro  ×  Claude Opus 4.6[/dim]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console.print()

    def print_phase1(self, logical: InitialTake, factual: InitialTake) -> None:
        console.print(Rule("[bold blue]Phase 1 — Initial Thesis (Parallel)[/bold blue]"))
        console.print()

        def _confidence_bar(value: float, color: str) -> str:
            filled = int(value * 20)
            bar = "█" * filled + "░" * (20 - filled)
            return f"[{color}]{bar}[/{color}] {value:.0%}"

        # Build logical panel text
        logical_text = Text()
        logical_text.append(f"{logical.content}\n\n", style="white")
        if logical.chain_of_thought:
            logical_text.append("Chain of Thought:\n", style="bold dim")
            logical_text.append(f"{logical.chain_of_thought}\n\n", style="dim")
        if logical.aggregated_from:
            logical_text.append("MoA Sources:\n", style="bold cyan")
            for m in logical.aggregated_from:
                logical_text.append(f"  · {m}\n", style="cyan dim")
            logical_text.append("\n")
        if logical.known_unknowns:
            logical_text.append("Known Unknowns:\n", style="bold yellow")
            for unk in logical.known_unknowns:
                logical_text.append(f"  ? {unk}\n", style="yellow")
            logical_text.append("\n")
        logical_text.append("Confidence: ", style="bold")
        logical_text.append(_confidence_bar(logical.confidence, "blue"))

        # Build factual panel text
        factual_text = Text()
        factual_text.append(f"{factual.content}\n\n", style="white")
        if factual.chain_of_thought:
            factual_text.append("Reasoning:\n", style="bold dim")
            factual_text.append(f"{factual.chain_of_thought}\n\n", style="dim")
        if factual.aggregated_from:
            factual_text.append("MoA Sources:\n", style="bold cyan")
            for m in factual.aggregated_from:
                factual_text.append(f"  · {m}\n", style="cyan dim")
            factual_text.append("\n")
        if factual.known_unknowns:
            factual_text.append("Known Unknowns:\n", style="bold yellow")
            for unk in factual.known_unknowns:
                factual_text.append(f"  ? {unk}\n", style="yellow")
            factual_text.append("\n")
        if factual.sources:
            factual_text.append("Grounded Sources:\n", style="bold cyan")
            for src in factual.sources[:3]:
                factual_text.append(f"  · {src[:80]}\n", style="cyan dim")
            factual_text.append("\n")
        factual_text.append("Confidence: ", style="bold")
        factual_text.append(_confidence_bar(factual.confidence, "green"))

        # Adjust subtitle to reflect role (adversarial vs standard)
        logical_subtitle = f"[blue]{logical.role.replace('_', ' ').title()}[/blue]"
        factual_subtitle = f"[green]{factual.role.replace('_', ' ').title()}[/green]"

        panels = [
            Panel(
                logical_text,
                title=f"[bold blue]Gemini Thinking[/bold blue] [dim]({logical.model_id})[/dim]",
                subtitle=logical_subtitle,
                border_style="blue",
                padding=(1, 1),
            ),
            Panel(
                factual_text,
                title=f"[bold green]Gemini Pro[/bold green] [dim]({factual.model_id})[/dim]",
                subtitle=factual_subtitle,
                border_style="green",
                padding=(1, 1),
            ),
        ]
        console.print(Columns(panels, equal=True, expand=True))
        console.print()

    def print_contradictions(self, contradictions: list[Contradiction]) -> None:
        """Show contradictions PROMINENTLY before the final answer."""
        console.print(Rule("[bold red]Contradictions Detected[/bold red]"))
        console.print()

        if not contradictions:
            console.print(
                Panel(
                    "[green]No contradictions found — both analyses are broadly consistent.[/green]",
                    border_style="green",
                    padding=(0, 2),
                )
            )
            console.print()
            return

        table = Table(
            show_header=True,
            header_style="bold red",
            border_style="red",
            expand=True,
        )
        table.add_column("Severity", style="bold", width=8)
        table.add_column("Analysis A", style="blue")
        table.add_column("Analysis B", style="green")

        for c in contradictions:
            severity_style = "bold red" if c.severity == "major" else "yellow"
            table.add_row(
                f"[{severity_style}]{c.severity.upper()}[/{severity_style}]",
                c.claim_a,
                c.claim_b,
            )

        console.print(
            Panel(
                table,
                title=f"[bold red]⚠  {len(contradictions)} Contradiction(s) Found[/bold red]",
                border_style="red",
                padding=(0, 1),
            )
        )
        console.print()

    def print_critique(
        self,
        synthesis: ClaudeSynthesis,
        verification: GeminiVerification,
    ) -> None:
        console.print(Rule("[bold magenta]Phase 2 — Adversarial Critique & Verification[/bold magenta]"))
        console.print()

        # Phase 2a: Claude synthesis
        assumptions_text = "\n".join(f"  • {a}" for a in synthesis.assumptions_challenged) or "  (none)"

        # Rubric table
        rubric_table = Table(show_header=True, header_style="bold magenta", border_style="magenta", expand=True)
        rubric_table.add_column("Dimension", style="bold")
        rubric_table.add_column("Analysis A", justify="center", style="blue")
        rubric_table.add_column("Analysis B", justify="center", style="green")
        dims = [
            ("Logical Coherence", synthesis.rubric_logical.logical_coherence, synthesis.rubric_factual.logical_coherence),
            ("Evidence Quality",  synthesis.rubric_logical.evidence_quality,  synthesis.rubric_factual.evidence_quality),
            ("Completeness",      synthesis.rubric_logical.completeness,       synthesis.rubric_factual.completeness),
            ("Reasoning Depth",   synthesis.rubric_logical.reasoning_depth,    synthesis.rubric_factual.reasoning_depth),
        ]
        for label, a, b in dims:
            bar_a = "█" * a + "░" * (5 - a)
            bar_b = "█" * b + "░" * (5 - b)
            rubric_table.add_row(label, f"{bar_a} {a}/5", f"{bar_b} {b}/5")
        rubric_table.add_row(
            "[bold]Average[/bold]",
            f"[bold]{synthesis.rubric_logical.normalized:.0%}[/bold]",
            f"[bold]{synthesis.rubric_factual.normalized:.0%}[/bold]",
        )

        console.print(
            Panel(
                f"[bold]Assumptions challenged:[/bold]\n{assumptions_text}\n\n"
                f"[bold]Synthesis draft:[/bold]\n{synthesis.synthesis_draft}\n\n"
                f"[bold]Agreement score:[/bold] {synthesis.agreement_score:.2f}  "
                f"({'high convergence' if synthesis.agreement_score >= 0.7 else 'significant divergence' if synthesis.agreement_score < 0.4 else 'moderate agreement'})",
                title="[bold magenta]Claude Opus — Adversarial Critique (Phase 2a)[/bold magenta]",
                border_style="magenta",
                padding=(1, 2),
            )
        )
        console.print(Panel(
            rubric_table,
            title="[bold magenta]Rubric Scores (1–5)[/bold magenta]",
            border_style="magenta",
            padding=(0, 1),
        ))
        console.print()

        # Phase 2c: Gemini verification
        errors_text = "\n".join(f"  • {e}" for e in verification.logical_errors) or "  (none)"
        wishful_text = "\n".join(f"  • {w}" for w in verification.wishful_thinking) or "  (none)"
        verified_badge = "[green]✓ VERIFIED[/green]" if verification.verified else "[red]✗ FLAWED[/red]"

        verification_body = (
            f"{verified_badge}\n\n"
            f"[bold]Logical errors:[/bold]\n{errors_text}\n\n"
            f"[bold]Wishful thinking:[/bold]\n{wishful_text}\n\n"
            f"[bold]Notes:[/bold] {verification.verification_notes}"
        )
        console.print(
            Panel(
                verification_body,
                title="[bold blue]Gemini Thinking — Logic Verification (Phase 2c)[/bold blue]",
                border_style="blue",
                padding=(1, 2),
            )
        )
        console.print()

    def print_rebuttal(self, rebuttal: GeminiRebuttal) -> None:
        """Display Phase 2b multi-turn rebuttal."""
        conceded_text = "\n".join(f"  ✓ {p}" for p in rebuttal.points_conceded) or "  (none — position fully maintained)"
        maintained_text = "\n".join(f"  ✗ {p}" for p in rebuttal.points_maintained) or "  (none — position fully conceded)"

        score_color = "green" if rebuttal.rebuttal_score >= 0.6 else "red" if rebuttal.rebuttal_score < 0.4 else "yellow"
        filled = int(rebuttal.rebuttal_score * 20)
        score_bar = f"[{score_color}]{'█' * filled}{'░' * (20 - filled)}[/{score_color}] {rebuttal.rebuttal_score:.0%} maintained"

        body = (
            f"[bold]Rebuttal:[/bold]\n{rebuttal.rebuttal_content}\n\n"
            f"[bold]Points conceded to critic:[/bold]\n{conceded_text}\n\n"
            f"[bold]Points defended:[/bold]\n{maintained_text}\n\n"
            f"[bold]Position strength:[/bold] {score_bar}"
        )
        console.print(
            Panel(
                body,
                title="[bold yellow]Gemini Thinking — Multi-Turn Rebuttal (Phase 2b)[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )
        )
        console.print()

    def print_final(self, final: FinalAnswer) -> None:
        console.print(Rule("[bold green]Phase 3 — Final Consensus Answer[/bold green]"))
        console.print()

        # Remaining disagreements
        if final.key_disagreements:
            disagreements_text = "\n".join(f"  ⚡ {d}" for d in final.key_disagreements)
            console.print(
                Panel(
                    disagreements_text,
                    title="[yellow]Unresolved Disagreements[/yellow]",
                    border_style="yellow",
                    padding=(0, 2),
                )
            )
            console.print()

        # Final answer
        console.print(
            Panel(
                final.content,
                title="[bold green]Final Answer[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
        console.print()

        # v1.4: Action-oriented output
        if final.recommendation:
            console.print(
                Panel(
                    f"[bold white]{final.recommendation}[/bold white]",
                    title="[bold green]Recommendation[/bold green]",
                    border_style="green",
                    padding=(0, 2),
                )
            )
            console.print()

        if final.key_uncertainties:
            unc_text = "\n".join(f"  ? {u}" for u in final.key_uncertainties)
            console.print(
                Panel(unc_text, title="[yellow]Key Uncertainties[/yellow]",
                      border_style="yellow", padding=(0, 2))
            )
            console.print()

        if final.next_steps:
            steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(final.next_steps))
            console.print(
                Panel(steps_text, title="[cyan]Next Steps[/cyan]",
                      border_style="cyan", padding=(0, 2))
            )
            console.print()

        # Consensus score bar
        self._print_score_bar("Consensus Score  C", final.consensus_score)
        self._print_score_bar("Model Confidence", final.confidence)
        console.print()

    def print_judge(self, verdict: JudgeVerdict) -> None:
        """Display Phase 4 skeptical judge verdict."""
        console.print(Rule("[bold red]Phase 4 — Skeptical Judge[/bold red]"))
        console.print()

        # Bias flags
        bias_text = "\n".join(f"  ⚠ {b}" for b in verdict.bias_flags) or "  (no notable biases detected)"
        # Missed perspectives
        missed_text = "\n".join(f"  • {p}" for p in verdict.missed_perspectives) or "  (none identified)"

        score_color = "green" if verdict.reliability_score >= 0.7 else "red" if verdict.reliability_score < 0.4 else "yellow"
        filled = int(verdict.reliability_score * 20)
        score_bar = f"[{score_color}]{'█' * filled}{'░' * (20 - filled)}[/{score_color}] {verdict.reliability_score:.0%} reliability"

        body = (
            f"[bold]Independent Verdict:[/bold]\n{verdict.judgment}\n\n"
            f"[bold]Cognitive biases detected:[/bold]\n{bias_text}\n\n"
            f"[bold]Missed perspectives:[/bold]\n{missed_text}\n\n"
            f"[bold]Reasoning:[/bold] {verdict.reasoning}\n\n"
            f"[bold]Reliability score:[/bold] {score_bar}"
        )
        console.print(
            Panel(
                body,
                title="[bold red]Claude Opus — Skeptical Judge (Phase 4)[/bold red]",
                subtitle="[dim]Independent evaluation — did not participate in the debate[/dim]",
                border_style="red",
                padding=(1, 2),
            )
        )
        console.print()

    def _print_score_bar(self, label: str, value: float) -> None:
        with Progress(
            TextColumn(f"  [bold]{label}:[/bold]"),
            BarColumn(bar_width=40, complete_style="green", finished_style="green"),
            TextColumn(f"[bold]{value:.1%}[/bold]"),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("", total=100)
            progress.update(task, completed=int(value * 100))

    def save_report(self, result: DebateResult, latency_s: float, output_dir: str = "output") -> Path:
        """Save full debate result as CDS-compatible Markdown with YAML frontmatter."""
        ts = datetime.now(timezone.utc)
        date_str = ts.strftime("%Y-%m-%d")
        slug = re.sub(r"[^\w]+", "-", result.problem[:50].lower()).strip("-")
        folder_name = f"{date_str}_{slug}"
        folder = Path(output_dir) / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        report_path = folder / f"{folder_name}_report.md"

        contradictions_md = ""
        if result.critique.contradictions:
            rows = "\n".join(
                f"| {c.severity.upper()} | {c.claim_a} | {c.claim_b} |"
                for c in result.critique.contradictions
            )
            contradictions_md = f"""
## Contradictions Detected

| Severity | Analysis A | Analysis B |
|---|---|---|
{rows}
"""
        else:
            contradictions_md = "\n## Contradictions Detected\n\nNone — both analyses broadly consistent.\n"

        assumptions_md = "\n".join(f"- {a}" for a in result.critique.assumptions_challenged) or "- (none)"
        errors_md = "\n".join(f"- {e}" for e in result.verification.logical_errors) or "- (none)"
        wishful_md = "\n".join(f"- {w}" for w in result.verification.wishful_thinking) or "- (none)"

        rl = result.critique.rubric_logical
        rf = result.critique.rubric_factual
        rubric_md = f"""
## Rubric Scores (Phase 2a)

| Dimension | Analysis A | Analysis B |
|---|---|---|
| Logical Coherence | {rl.logical_coherence}/5 | {rf.logical_coherence}/5 |
| Evidence Quality | {rl.evidence_quality}/5 | {rf.evidence_quality}/5 |
| Completeness | {rl.completeness}/5 | {rf.completeness}/5 |
| Reasoning Depth | {rl.reasoning_depth}/5 | {rf.reasoning_depth}/5 |
| **Average** | **{rl.normalized:.0%}** | **{rf.normalized:.0%}** |
"""
        disagreements_md = "\n".join(f"- {d}" for d in result.final_answer.key_disagreements) or "- (none)"

        # Epistemic uncertainty section
        unknowns_a = "\n".join(f"- {u}" for u in result.logical_analysis.known_unknowns) if result.logical_analysis.known_unknowns else "- (none flagged)"
        unknowns_b = "\n".join(f"- {u}" for u in result.factual_context.known_unknowns) if result.factual_context.known_unknowns else "- (none flagged)"
        sources_b = "\n".join(f"- {s}" for s in result.factual_context.sources) if result.factual_context.sources else "- (no grounded sources)"

        # Problem decomposition section
        decompose_md = ""
        if result.decomposition:
            d = result.decomposition
            rows = "\n".join(f"| {i+1} | {sq.aspect.upper()} | {sq.question} |" for i, sq in enumerate(d.sub_questions))
            decompose_md = f"""
## Phase 0 — Problem Decomposition

**Complexity:** {d.complexity} | **Reasoning:** {d.reasoning}

| # | Aspect | Sub-Question |
|---|---|---|
{rows}

---
"""

        # Fact-check section
        fact_check_md = ""
        if result.fact_check:
            fc = result.fact_check
            fc_rows = "\n".join(
                f"| {'✓' if c.status == 'confirmed' else '✗' if c.status == 'refuted' else '?'} {c.status.upper()} | {c.source_role} | {c.claim} | {c.evidence[:100]} |"
                for c in fc.claims
            )
            fact_check_md = f"""
## Phase 1.5 — Claim-Level Fact-Check

**Overall Reliability:** {fc.overall_reliability:.0%} | **Confirmed:** {fc.confirmed_count} | **Refuted:** {fc.refuted_count} | **Uncertain:** {fc.uncertain_count}

{fc.summary}

| Status | Source | Claim | Evidence |
|---|---|---|---|
{fc_rows}

---
"""

        # Argument graph section (with Mermaid)
        argraph_md = ""
        if result.argument_graph:
            ag = result.argument_graph
            argraph_md = f"""
## Phase 1.6 — Structured Argument Graph

{ag.summary}

```mermaid
{ag.to_mermaid()}
```

**Contradictions in argument chains:** {len(ag.contradiction_edges)}

---
"""

        # Delphi process section
        delphi_md = ""
        if result.delphi_process:
            dp = result.delphi_process
            delphi_rows = "\n".join(
                f"| {r.round_n} | {r.confidence_a:.0%} | {r.confidence_b:.0%} | {r.delta:.3f if r.round_n > 1 else 'N/A'} |"
                for r in dp.rounds
            )
            delphi_md = f"""
## Phase 1 — Delphi Iterative Refinement

**Rounds:** {len(dp.rounds)} | **Converged:** {'Yes (round ' + str(dp.convergence_round) + ')' if dp.converged else 'No'}

| Round | Conf A | Conf B | Δ Delta |
|---|---|---|---|
{delphi_rows}

---
"""

        # Calibration section
        calibration_md = ""
        if result.calibration:
            cal = result.calibration
            cal_rows = "\n".join(
                f"| {c.model_id[:20]} | {c.claim[:80]} | {c.probability:.0%} | [{c.ci_lower:.0%}, {c.ci_upper:.0%}] | {c.time_horizon} |"
                for c in cal.claims
            )
            calibration_md = f"""
## Calibration Tracking

**Debate ID:** {cal.debate_id}{f' | Fact-check alignment: {cal.fact_check_alignment:.0%}' if cal.fact_check_alignment is not None else ''}

| Model | Claim | Probability | 90% CI | Horizon |
|---|---|---|---|---|
{cal_rows}

---
"""

        # Optional rebuttal section
        rebuttal_md = ""
        if result.rebuttal:
            rb = result.rebuttal
            conceded_md = "\n".join(f"- {p}" for p in rb.points_conceded) or "- (none)"
            maintained_md = "\n".join(f"- {p}" for p in rb.points_maintained) or "- (none)"
            rebuttal_md = f"""
---

## Phase 2b — Multi-Turn Rebuttal (Gemini Thinking)

**Rebuttal score:** {rb.rebuttal_score:.2f} (1.0 = position fully maintained)

{rb.rebuttal_content}

**Points conceded:**
{conceded_md}

**Points defended:**
{maintained_md}
"""

        # Optional judge section
        judge_md = ""
        judge_yaml = ""
        if result.judge:
            j = result.judge
            bias_md = "\n".join(f"- {b}" for b in j.bias_flags) or "- (none detected)"
            missed_md = "\n".join(f"- {p}" for p in j.missed_perspectives) or "- (none identified)"
            judge_md = f"""
---

## Phase 4 — Skeptical Judge (Claude Opus)

**Reliability score:** {j.reliability_score:.2f}

**Verdict:** {j.judgment}

**Cognitive biases detected:**
{bias_md}

**Missed perspectives:**
{missed_md}

**Reasoning:** {j.reasoning}
"""
            judge_yaml = f"\nreliability_score: {j.reliability_score:.3f}"

        moa_a = f"\n  aggregated_from_a: {result.logical_analysis.aggregated_from}" if result.logical_analysis.aggregated_from else ""
        moa_b = f"\n  aggregated_from_b: {result.factual_context.aggregated_from}" if result.factual_context.aggregated_from else ""
        fc_yaml = f"\nfact_check_reliability: {result.fact_check.overall_reliability:.3f}" if result.fact_check else ""

        content = f"""---
id: debate-{uuid.uuid4().hex[:8]}
title: "{result.problem[:80]}"
type: debate_report
category: multi_agent_reasoning
tier: 1
retrieved: "{ts.isoformat()}"
models:
  analysis_a: "{result.logical_analysis.model_id}"
  analysis_b: "{result.factual_context.model_id}"
  critique: claude-opus-4-6
  verification: "{result.logical_analysis.model_id}"
  final_answer: claude-opus-4-6{moa_a}{moa_b}
roles:
  analysis_a: "{result.logical_analysis.role}"
  analysis_b: "{result.factual_context.role}"
consensus_score: {result.final_answer.consensus_score:.3f}
confidence: {result.final_answer.confidence:.3f}
agreement_score: {result.critique.agreement_score:.3f}
verification_passed: {str(result.verification.verified).lower()}
latency_s: {latency_s:.1f}{judge_yaml}{fc_yaml}
language: auto
---

# Debate Report

**Problem:** {result.problem}
{decompose_md}

**Date:** {date_str} | **Latency:** {latency_s:.1f}s | **Consensus:** {result.final_answer.consensus_score:.1%} | **Confidence:** {result.final_answer.confidence:.1%}

---

## Phase 1 — Initial Thesis

### Analysis A — {result.logical_analysis.role.replace("_", " ").title()} ({result.logical_analysis.model_id})
**Confidence:** {result.logical_analysis.confidence:.0%}

{result.logical_analysis.content}

**Chain of Thought:**
{result.logical_analysis.chain_of_thought}

**Known Unknowns:**
{unknowns_a}

---

### Analysis B — {result.factual_context.role.replace("_", " ").title()} ({result.factual_context.model_id})
**Confidence:** {result.factual_context.confidence:.0%}

{result.factual_context.content}

**Reasoning:**
{result.factual_context.chain_of_thought}

**Known Unknowns:**
{unknowns_b}

**Grounded Sources:**
{sources_b}

---
{delphi_md}{argraph_md}{fact_check_md}{calibration_md}{contradictions_md}
---

## Phase 2 — Adversarial Critique & Verification
{rubric_md}
### Claude Opus — Adversarial Critique (Phase 2a)
**Agreement Score:** {result.critique.agreement_score:.2f}

**Assumptions challenged:**
{assumptions_md}

**Synthesis draft:**
{result.critique.synthesis_draft}
{rebuttal_md}
---

### Gemini — Logic Verification (Phase 2c)
**Verified:** {"✓ YES" if result.verification.verified else "✗ NO"}

**Logical errors:**
{errors_md}

**Wishful thinking:**
{wishful_md}

**Notes:** {result.verification.verification_notes}

---

## Phase 3 — Final Consensus Answer

**Unresolved disagreements:**
{disagreements_md}

{result.final_answer.content}
{judge_md}
---

## Scores

| Metric | Value |
|---|---|
| Consensus Score C | {result.final_answer.consensus_score:.1%} |
| Model Confidence | {result.final_answer.confidence:.1%} |
| Agreement Score | {result.critique.agreement_score:.1%} |
| Verification | {"PASSED" if result.verification.verified else "FAILED"} |
| Latency | {latency_s:.1f}s |
{f'| Judge Reliability | {result.judge.reliability_score:.1%} |' if result.judge else ''}
"""
        report_path.write_text(content, encoding="utf-8")
        return report_path
