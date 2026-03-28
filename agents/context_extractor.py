"""
Context Extractor Agent: file, line, function, message from log lines.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from utils.parser import extract_java_caused, guess_language_from_path, parse_stack_line

# Optional bracket prefix from log_reader: [relative/path.log] content
_PREFIX = re.compile(r"^\[[^\]]+\]\s*")


def _strip_prefix(line: str) -> str:
    return _PREFIX.sub("", line, count=1)


def extract_context(error_line: str, project_path: str | Path | None = None) -> dict[str, Any]:
    """
    Build structured context for one error line.
    Attempts to read a snippet from project_path if file path is resolved.
    """
    raw = error_line
    line = _strip_prefix(error_line)
    ctx: dict[str, Any] = {
        "message": line.strip(),
        "file": None,
        "line": None,
        "function": None,
        "language": None,
        "column": None,
    }

    parsed = parse_stack_line(line)
    ctx.update({k: v for k, v in parsed.items() if k in ctx})

    jc = extract_java_caused(line)
    if jc:
        ctx["java_caused_by"] = jc

    # If still no file, try last path-like token
    if ctx.get("file") is None:
        m = re.search(r"([\w/.\-]+\.(?:py|js|ts|java))", line)
        if m:
            ctx["file"] = m.group(1)
            ctx["language"] = ctx.get("language") or guess_language_from_path(ctx["file"])

    snippet = None
    if project_path and ctx.get("file") and ctx.get("line"):
        snippet = _read_file_snippet(project_path, str(ctx["file"]), int(ctx["line"]))

    ctx["codebase_snippet"] = snippet
    return {"raw_line": raw, "context": ctx}


def _read_file_snippet(project_root: str | Path, file_ref: str, line_no: int, radius: int = 12) -> str | None:
    """Read lines around line_no from file under project if it exists."""
    import config

    root = Path(project_root).resolve()
    candidates = [root / file_ref, (root / file_ref).resolve() if not Path(file_ref).is_absolute() else Path(file_ref)]
    path = None
    for c in candidates:
        try:
            if c.is_file():
                path = c
                break
        except OSError:
            continue
    if path is None:
        # try basename match under root (shallow)
        base = Path(file_ref).name
        for p in root.rglob(base):
            if p.is_file():
                path = p
                break
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    i = max(0, line_no - 1)
    lo = max(0, i - radius)
    hi = min(len(lines), i + radius + 1)
    chunk = lines[lo:hi]
    out = [f"{j+1:5d} | {chunk[j - lo]}" for j in range(lo, hi)]
    text = "\n".join(out)
    return text[: config.MAX_CODE_CONTEXT_CHARS]
