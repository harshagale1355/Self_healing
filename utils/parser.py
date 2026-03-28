"""
Regex-based parsing for stack traces and log lines (Python, Node, Java).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# Python: File "/path/to/file.py", line 42, in func_name
_PY_FILE_LINE = re.compile(
    r'File\s+"(?P<file>[^"]+)",\s*line\s+(?P<line>\d+)(?:,\s*in\s+(?P<func>[^\s]+))?'
)
# Python traceback header
_PY_TRACEBACK = re.compile(r"Traceback\s*\(most recent call last\)")

# Node: at func (/path/file.js:10:5) or at /path/file.js:10:5
_NODE_AT = re.compile(
    r"\s+at\s+(?:(?P<func>[^\s(]+)\s*)?\(?(?P<file>[^\s():]+):(?P<line>\d+)(?::(?P<col>\d+))?\)?"
)

# Java: at com.foo.Bar.method(Bar.java:123)
_JAVA_AT = re.compile(
    r"at\s+(?P<class>[\w$.]+)\.(?P<method>[\w$]+)\((?P<file>[^:]+):(?P<line>\d+)\)"
)
_JAVA_CAUSED = re.compile(r"Caused by:\s*(?P<msg>.+)")

# Go: panic often prints "main.go:123 +0x..."
_GO_FILE_LINE = re.compile(
    r"(?P<file>[/\w.\-]+\.go):(?P<line>\d+)",
)

# Generic file:line (Python / Node / Java / Go / Rust-style paths)
_GENERIC_FILE_LINE = re.compile(
    r"(?P<file>[/\w.\-]+\.(?:py|js|ts|tsx|jsx|java|go|rb|rs|kt))(?:\s*|:)(?:line\s*)?(?P<line>\d+)",
    re.IGNORECASE,
)


def guess_language_from_path(path: str) -> str:
    suf = Path(path).suffix.lower()
    if suf == ".py":
        return "python"
    if suf in (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"):
        return "javascript"
    if suf == ".java":
        return "java"
    if suf == ".go":
        return "go"
    if suf == ".rs":
        return "rust"
    return "unknown"


def parse_stack_line(line: str) -> dict[str, Any]:
    """
    Extract file, line, optional function/column from a single log line.
    Returns keys: file, line, function, language (when inferable).
    """
    line = line.strip()
    out: dict[str, Any] = {}

    m = _PY_FILE_LINE.search(line)
    if m:
        out["file"] = m.group("file")
        out["line"] = int(m.group("line"))
        if m.groupdict().get("func"):
            out["function"] = m.group("func")
        out["language"] = "python"
        return out

    m = _NODE_AT.search(line)
    if m:
        out["file"] = m.group("file")
        out["line"] = int(m.group("line"))
        if m.groupdict().get("func"):
            out["function"] = m.group("func")
        if m.groupdict().get("col"):
            out["column"] = int(m.group("col"))
        out["language"] = "javascript"
        return out

    m = _JAVA_AT.search(line)
    if m:
        out["file"] = m.group("file")
        out["line"] = int(m.group("line"))
        out["function"] = f"{m.group('class')}.{m.group('method')}"
        out["language"] = "java"
        return out

    m = _GO_FILE_LINE.search(line)
    if m:
        out["file"] = m.group("file")
        out["line"] = int(m.group("line"))
        out["language"] = "go"
        return out

    m = _GENERIC_FILE_LINE.search(line)
    if m:
        out["file"] = m.group("file")
        out["line"] = int(m.group("line"))
        out["language"] = guess_language_from_path(out["file"])
        return out

    return out


def is_traceback_start(line: str) -> bool:
    return bool(_PY_TRACEBACK.search(line))


def extract_java_caused(line: str) -> str | None:
    m = _JAVA_CAUSED.match(line.strip())
    return m.group("msg").strip() if m else None
