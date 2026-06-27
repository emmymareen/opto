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
def eval(full: bool = typer.Option(False, help="(reserved) run against a model; "
                                               "default is a savings-only dry run.")):
    """Run the accuracy harness on the bundled sample tasks.

    Without a model wired in, this reports token savings per task (dry run). To
    measure accuracy delta, use the EvalHarness API with a ModelClient."""
    from opto.evals import EvalHarness, load_sample_tasks

    tasks = load_sample_tasks()
    res = EvalHarness().dry_run(tasks)
    table = Table(title="Opto eval (dry run — savings only)")
    table.add_column("Task")
    table.add_column("Category")
    table.add_column("Saved", justify="right")
    for t in res.per_task:
        table.add_row(t["id"], t["category"], f"{t['saved_fraction']*100:.0f}%")
    console.print(table)
    console.print(f"Overall: {res.saved_fraction*100:.1f}% tokens saved "
                  f"across {res.n} tasks.")
    if not full:
        console.print("[dim]Wire a ModelClient to also measure accuracy delta.[/]")


@app.command()
def retrieve(cache_id: str = typer.Argument(..., help="Cache id from a drop marker.")):
    """Recover an original (pre-compression) span from the reversible cache."""
    from opto.cache import ReversibleCache

    cfg = get_config()
    cache = ReversibleCache(cfg.cache_dir, cfg.cache_ttl_s)
    original = cache.retrieve(cache_id)
    if original is None:
        console.print("[red]Not found or expired.[/]")
        raise typer.Exit(code=1)
    console.print(original)


@app.command(name="copilot-auth")
def copilot_auth():
    """Check the Copilot auth bridge: discover the OAuth token, exchange it, and
    report the resolved endpoint. No API key required — uses your Copilot licence."""
    from opto.copilot_auth import build_session_from_environment
    from opto.config import get_config

    cfg = get_config()
    session = build_session_from_environment(cfg.github_host)
    if session is None:
        console.print("[red]No GitHub Copilot OAuth token found.[/]")
        console.print("Sign in via the Copilot CLI / editor, or set "
                      "OPTO_COPILOT_GITHUB_TOKEN.")
        raise typer.Exit(code=1)
    try:
        base = session.api_base()
    except Exception as exc:
        console.print(f"[red]Token exchange failed:[/] {exc}")
        raise typer.Exit(code=1)
    console.print("[green]Copilot auth OK[/] — no API key needed.")
    console.print(f"  resolved endpoint: {base}")
    console.print(f"  integration id:    {session.integration_id}")


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
