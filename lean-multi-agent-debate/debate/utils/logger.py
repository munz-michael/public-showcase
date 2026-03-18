"""
Lean Debate Engine — Rich Logger with cost tracking.
Usage:
    from debate.utils.logger import log
    log.phase(1, "Initial Thesis")
    log.info("Running Gemini Thinking...")
    log.cost("claude-opus-4-6", input_tokens=1200, output_tokens=800)
"""

from rich.console import Console
from rich.rule import Rule

_console = Console(stderr=True)

# Anthropic pricing (per 1M tokens, USD) — claude-opus-4-6 rates
_ANTHROPIC_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6":    (15.00, 75.00),
    "claude-sonnet-4-6":  (3.00,  15.00),
    "claude-haiku-4-5":   (0.80,  4.00),
}
_DEFAULT_PRICE = (3.00, 15.00)

_PHASE_COLORS = {
    0: "cyan",
    1: "blue",
    2: "magenta",
    3: "green",
    4: "red",
}


class _Logger:
    def phase(self, n: int, name: str) -> None:
        color = _PHASE_COLORS.get(n, "white")
        _console.print(Rule(f"[bold {color}]Phase {n} — {name}[/bold {color}]"))

    def info(self, msg: str) -> None:
        _console.print(f"  [dim]{msg}[/dim]")

    def warning(self, msg: str) -> None:
        _console.print(f"  [yellow]⚠ {msg}[/yellow]")

    def error(self, msg: str) -> None:
        _console.print(f"  [bold red]✗ {msg}[/bold red]")

    def success(self, msg: str) -> None:
        _console.print(f"  [green]✓ {msg}[/green]")

    def cost(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """Log estimated API cost for a single call."""
        in_price, out_price = _ANTHROPIC_PRICING.get(model, _DEFAULT_PRICE)
        cost_usd = (input_tokens / 1_000_000 * in_price) + (output_tokens / 1_000_000 * out_price)
        _console.print(
            f"  [dim]💰 {model}: {input_tokens:,} in + {output_tokens:,} out"
            f" → [cyan]${cost_usd:.4f}[/cyan][/dim]"
        )

    def latency(self, phase: str, seconds: float) -> None:
        color = "green" if seconds < 10 else "yellow" if seconds < 30 else "red"
        _console.print(f"  [dim]⏱ {phase}: [{color}]{seconds:.1f}s[/{color}][/dim]")


log = _Logger()
