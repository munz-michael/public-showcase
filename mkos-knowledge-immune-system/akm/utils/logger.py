"""Rich console logging utilities."""

from __future__ import annotations

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()


def log_phase(phase: str, message: str = "") -> None:
    console.print(f"[bold cyan][{phase}][/bold cyan] {message}")


def log_success(message: str) -> None:
    console.print(f"[green]  + {message}[/green]")


def log_warning(message: str) -> None:
    console.print(f"[yellow]  ! {message}[/yellow]")


def log_error(message: str) -> None:
    console.print(f"[bold red]  x {message}[/bold red]")


def log_info(message: str) -> None:
    console.print(f"[dim]  - {message}[/dim]")


def create_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )
