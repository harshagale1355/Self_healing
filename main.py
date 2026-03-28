"""
CLI entry: ai-debugger run /path/to/project [--options]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

import config
from workflows.graph import run_analysis


@click.group()
@click.version_option(version="1.0.0", prog_name="ai-debugger")
def cli() -> None:
    """AI-Powered Log Error Analyzer and Auto-Solver."""


@cli.command("run")
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--rag/--no-rag", default=None, help="Enable Chroma RAG (default: env ENABLE_RAG).")
@click.option(
    "--llm-classifier/--no-llm-classifier",
    default=False,
    help="Use LLM to refine error classification (extra API calls).",
)
@click.option("-o", "--output", type=click.Path(path_type=Path), help="Write JSON results to file.")
@click.option("--indent", type=int, default=2, help="JSON indent (default 2).")
def run_cmd(
    project_path: Path,
    rag: bool | None,
    llm_classifier: bool,
    output: Path | None,
    indent: int,
) -> None:
    """Scan PROJECT_PATH for logs, analyze errors, print structured JSON."""
    use_rag = rag if rag is not None else config.ENABLE_RAG
    results = run_analysis(
        str(project_path.resolve()),
        use_rag=use_rag,
        use_llm_classifier=llm_classifier,
    )
    text = json.dumps(results, ensure_ascii=False, indent=indent if indent > 0 else None)
    if output:
        output.write_text(text, encoding="utf-8")
        click.echo(f"Wrote {len(results)} record(s) to {output}", err=True)
    click.echo(text)


def main() -> None:
    """Console script entry for setuptools."""
    cli()


if __name__ == "__main__":
    main()
