"""Opto command-line interface."""

from __future__ import annotations

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from opto.config import get_config
from opto.telemetry import Telemetry
from opto._version import __version__

app = typer.Typer(help="Opto — local context-compression proxy for GitHub Copilot.")
console = Console()


@app.command()
def version():
    """Print the Opto version."""
    console.print(f"opto {__version__}")


@app.command()
def proxy(
    host: str = typer.Option(None, help="Bind host (overrides config)."),
    port: int = typer.Option(None, help="Bind port (overrides config)."),
):
    """Start the compression proxy."""
    cfg = get_config()
    cfg.ensure_dirs()
    h = host or cfg.host
    p = port or cfg.port
    console.print(f"[bold green]Opto[/] proxy on http://{h}:{p}  →  {cfg.upstream_base_url}")
    console.print(f"compression={'on' if cfg.enabled else 'off'} "
                  f"target_ratio={cfg.target_ratio} quality_gate={cfg.quality_gate_enabled}")
    uvicorn.run("opto.proxy.server:create_app", host=h, port=p, factory=True)


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8800),
):
    """Start the transparency dashboard."""
    console.print(f"[bold cyan]Opto[/] dashboard on http://{host}:{port}")
    uvicorn.run("opto.dashboard.server:create_dashboard", host=host, port=port, factory=True)


@app.command()
def stats():
    """Show cumulative savings from telemetry."""
    cfg = get_config()
    tel = Telemetry(cfg.telemetry_db, cfg.audit_log_path, redact=cfg.redact_content_in_logs)
    s = tel.summary()
    table = Table(title="Opto — cumulative savings")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Requests", str(s["requests"]))
    table.add_row("Original tokens", f"{s['original_tokens']:,}")
    table.add_row("Compressed tokens", f"{s['compressed_tokens']:,}")
    table.add_row("Saved tokens", f"{s['saved_tokens']:,}")
    table.add_row("Saved fraction", f"{s['saved_fraction'] * 100:.1f}%")
    table.add_row("Backed off (quality)", str(s["backed_off"]))
    table.add_row("Held out (control)", str(s["held_out"]))
    console.print(table)


@app.command()
def wrap(agent: str = typer.Argument(..., help="Agent to wrap, e.g. 'copilot'.")):
    """Print the config needed to route an agent through Opto."""
    cfg = get_config()
    base = f"http://{cfg.host}:{cfg.port}"
    if agent.lower() == "copilot":
        console.print("[bold]Route GitHub Copilot through Opto:[/]")
        console.print(f"  export OPENAI_BASE_URL={base}")
        console.print(f"  export COPILOT_PROVIDER_API_URL={base}")
        console.print("Then start Copilot CLI as usual. For VS Code, set the Copilot")
        console.print(f"  advanced 'debug.overrideProxyUrl' / endpoint override to {base}.")
    else:
        console.print(f"Point {agent}'s OpenAI-compatible base URL at: {base}")


if __name__ == "__main__":
    app()
