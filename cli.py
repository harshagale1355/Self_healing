"""
CLI: ai-debugger run | watch | version — pretty terminal output (Rich) + JSON export.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

import config
from utils.log_monitor import watch_log_file
from workflows.graph import run_analysis

console = Console(stderr=False)


@click.group()
@click.version_option(version="2.0.0", prog_name="ai-debugger")
def cli() -> None:
    """AI-Powered Log Error Analyzer — codebase-aware, RAG, patches, metrics."""


@cli.command("run")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--rag/--no-rag", default=None, help="Enable Chroma RAG.")
@click.option("--llm-classifier/--no-llm-classifier", default=False, help="LLM-based classifier.")
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write full JSON (results + metrics) to file.")
@click.option("--indent", type=int, default=2)
@click.option("--json", "as_json", is_flag=True, help="Print raw JSON only (no colors).")
def run_cmd(
    project_path: Path,
    rag: bool | None,
    llm_classifier: bool,
    output: Path | None,
    indent: int,
    as_json: bool,
) -> None:
    """Scan PROJECT_PATH for logs, analyze errors, print results."""
    use_rag = rag if rag is not None else config.ENABLE_RAG
    payload = run_analysis(
        str(project_path.resolve()),
        use_rag=use_rag,
        use_llm_classifier=llm_classifier,
    )
    results = payload["results"]
    metrics = payload.get("metrics") or {}

    if as_json:
        text = json.dumps(payload, ensure_ascii=False, indent=indent if indent > 0 else None)
        click.echo(text)
    else:
        _print_metrics_panel(metrics)
        for i, item in enumerate(results, 1):
            _print_error_card(i, item)
        if not results:
            console.print(Panel("[dim]No errors to display.[/dim]", title="Done", border_style="dim"))

    if output:
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=indent if indent > 0 else None),
            encoding="utf-8",
        )
        console.print(f"[green]Wrote {len(results)} error(s) + metrics → {output}[/green]", file=sys.stderr)


def _severity_style(sev: str) -> str:
    return {"high": "red", "medium": "yellow", "low": "green"}.get((sev or "low").lower(), "white")


def _print_metrics_panel(metrics: dict) -> None:
    t = Table(title="Run metrics", box=box.ROUNDED, show_header=True, header_style="bold cyan")
    t.add_column("Metric", style="dim")
    t.add_column("Value")
    t.add_row("Errors processed", str(metrics.get("errors_processed", 0)))
    t.add_row("LLM successes", str(metrics.get("llm_success", 0)))
    t.add_row("LLM failures", str(metrics.get("llm_failures", 0)))
    sr = metrics.get("llm_success", 0) + metrics.get("llm_failures", 0)
    rate = (
        metrics.get("llm_success", 0) / sr
        if sr
        else 1.0
    )
    t.add_row("LLM success rate", f"{rate:.1%}")
    t.add_row("Post-processing time (s)", str(metrics.get("total_processing_seconds", 0)))
    t.add_row("Wall clock (s)", str(metrics.get("wall_clock_seconds", 0)))
    if metrics.get("errors_by_severity"):
        t.add_row("By severity", json.dumps(metrics["errors_by_severity"]))
    console.print(t)
    console.print()


def _print_error_card(index: int, item: dict) -> None:
    sev = item.get("severity") or "unknown"
    title = Text()
    title.append(f"Error #{index} ", style="bold")
    title.append(f"[{sev.upper()}]", style=_severity_style(sev))

    err = item.get("error", "")[:2000]
    body = Table.grid(padding=(0, 2))
    body.add_column(style="dim", width=12)
    body.add_column()
    body.add_row("Type", str(item.get("type", "")))
    body.add_row("Cause", str(item.get("cause", ""))[:1200])
    body.add_row("Fix", str(item.get("fix", ""))[:1200])
    pri = item.get("priority")
    if pri is not None:
        body.add_row("Priority", str(pri))
    conf = item.get("confidence")
    if conf is not None:
        body.add_row("Confidence", f"{float(conf):.2f}")

    ctx = item.get("context") or {}
    loc = []
    if ctx.get("file"):
        loc.append(ctx["file"])
    if ctx.get("line"):
        loc.append(f":{ctx['line']}")
    if loc:
        body.add_row("Location", "".join(loc))

    console.print(Panel.fit(body, title=title, border_style=_severity_style(sev)))

    code = (item.get("code") or "").strip()
    if code:
        console.print(Syntax(code, "python", theme="monokai", line_numbers=False, word_wrap=True))

    patch = (item.get("patch") or "").strip()
    if patch:
        console.print(Panel(Syntax(patch, "diff", theme="monokai", line_numbers=False, word_wrap=True), title="Patch", border_style="blue"))

    val = item.get("validation") or {}
    if val.get("notes"):
        console.print(f"[dim]Validation: {val.get('notes')}[/dim]")
    console.print()


@cli.command("watch")
@click.argument("log_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--rag/--no-rag", default=None)
@click.option("--interval", type=float, default=1.0, help="Poll interval seconds.")
def watch_cmd(log_file: Path, rag: bool | None, interval: float) -> None:
    """Poll a log file for new lines and analyze each new error line (project = log parent)."""
    use_rag = rag if rag is not None else config.ENABLE_RAG
    project_root = log_file.parent.resolve()

    def on_new_errors(lines: list[str]) -> None:
        # Write chunk to temp dir and run analysis on parent project (includes only new lines in a temp log)
        import tempfile

        d = Path(tempfile.mkdtemp())
        p = d / "watch.log"
        p.write_text("\n".join(lines), encoding="utf-8")
        payload = run_analysis(str(d), use_rag=use_rag)
        for item in payload["results"]:
            _print_error_card(0, item)

    console.print(
        f"[bold]Watching[/bold] {log_file} (project root: {project_root}) — Ctrl+C to stop.",
        style="cyan",
    )
    try:
        watch_log_file(log_file, on_new_errors, poll_interval=interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
