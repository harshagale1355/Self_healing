"""
Context Extractor Agent: file, line, function, message from log lines.
File content is loaded by agents.code_context (5–10 lines around error).
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
    Build structured context for one error line (parsing only — no file IO).
    Use enrich_code_context() next to attach codebase_snippet.
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
        "codebase_snippet": None,
    }

    parsed = parse_stack_line(line)
    ctx.update({k: v for k, v in parsed.items() if k in ctx})

    jc = extract_java_caused(line)
    if jc:
        ctx["java_caused_by"] = jc

    if ctx.get("file") is None:
        m = re.search(r"([\w/.\-]+\.(?:py|js|ts|tsx|jsx|java|go|rb))", line)
        if m:
            ctx["file"] = m.group(1)
            ctx["language"] = ctx.get("language") or guess_language_from_path(ctx["file"])

    return {"raw_line": raw, "context": ctx}
