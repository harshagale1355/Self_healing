"""
Code context: load 5–10 lines around the error line from the project tree.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import config


def resolve_source_path(project_root: str | Path, file_ref: str) -> Path | None:
    """Resolve a path from log (relative, absolute, or basename search)."""
    root = Path(project_root).resolve()
    candidates: list[Path] = []
    p = Path(file_ref)
    if p.is_absolute() and p.is_file():
        return p
    candidates.append(root / file_ref)
    try:
        c2 = (root / file_ref).resolve()
        if c2.is_file():
            return c2
    except OSError:
        pass
    base = Path(file_ref).name
    for found in root.rglob(base):
        try:
            if found.is_file():
                return found
        except OSError:
            continue
    return None


def read_code_window(
    project_root: str | Path,
    file_ref: str,
    line_no: int,
    lines_before: int | None = None,
    lines_after: int | None = None,
) -> str | None:
    """
    Read lines_before + 1 + lines_after lines centered on line_no (1-based).
    Returns numbered snippet or None if file missing.
    """
    before = lines_before if lines_before is not None else config.CODE_CONTEXT_LINES_BEFORE
    after = lines_after if lines_after is not None else config.CODE_CONTEXT_LINES_AFTER

    path = resolve_source_path(project_root, file_ref)
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None

    i = max(0, line_no - 1)
    lo = max(0, i - before)
    hi = min(len(lines), i + after + 1)
    chunk = lines[lo:hi]
    out = [f"{j + 1:5d} | {chunk[j - lo]}" for j in range(lo, hi)]
    text = "\n".join(out)
    return text[: config.MAX_CODE_CONTEXT_CHARS]


def enrich_code_context(project_path: str | Path, context_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Attach codebase_snippet and code_window metadata to context_payload["context"].
    """
    ctx = dict(context_payload.get("context") or {})
    file_ref = ctx.get("file")
    line_no = ctx.get("line")

    if file_ref and line_no is not None:
        try:
            ln = int(line_no)
        except (TypeError, ValueError):
            ln = None
        if ln is not None:
            snippet = read_code_window(project_path, str(file_ref), ln)
            ctx["codebase_snippet"] = snippet
            ctx["code_window_lines"] = {
                "before": config.CODE_CONTEXT_LINES_BEFORE,
                "after": config.CODE_CONTEXT_LINES_AFTER,
                "center_line": ln,
            }
            rp = resolve_source_path(project_path, str(file_ref))
            if rp:
                ctx["resolved_path"] = str(rp.relative_to(Path(project_path).resolve()))

    return {**context_payload, "context": ctx}
