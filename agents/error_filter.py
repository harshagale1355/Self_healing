"""
Error Filter Agent: keeps lines that look like errors, warnings, or stack traces.
"""
from __future__ import annotations

import re
from typing import Any

from utils.parser import is_traceback_start

# Keywords suggesting error-level output (case-insensitive)
_ERROR_PATTERNS = [
    re.compile(r"\bERROR\b", re.IGNORECASE),
    re.compile(r"\bFATAL\b", re.IGNORECASE),
    re.compile(r"\bCRITICAL\b", re.IGNORECASE),
    re.compile(r"\bException\b", re.IGNORECASE),
    re.compile(r"\bTraceback\b", re.IGNORECASE),
    re.compile(r"\bError:\s", re.IGNORECASE),
    re.compile(r"\bERR!\b", re.IGNORECASE),
    re.compile(r"\bpanic:\b", re.IGNORECASE),
    re.compile(r"\bUnhandledPromiseRejection\b", re.IGNORECASE),
    re.compile(r"\bCaused by:\b", re.IGNORECASE),
    re.compile(r"\bECONNREFUSED\b"),
    re.compile(r"\bETIMEDOUT\b"),
    re.compile(r"\bENOENT\b"),
    re.compile(r"\bSyntaxError\b"),
    re.compile(r"\bReferenceError\b"),
    re.compile(r"\bTypeError\b"),
    re.compile(r"\bImportError\b", re.IGNORECASE),
    re.compile(r"\bModuleNotFoundError\b"),
    re.compile(r"\bOutOfMemoryError\b"),
    re.compile(r"\bStack trace\b", re.IGNORECASE),
]

# Lines that are clearly warnings — include if no errors found, user may want them
_WARN_PATTERNS = [
    re.compile(r"\bWARN\b", re.IGNORECASE),
    re.compile(r"\bWARNING\b", re.IGNORECASE),
]


def filter_error_lines(raw_lines: list[str], include_warnings: bool = True) -> dict[str, Any]:
    """
    Filter raw log lines to error-related lines. Deduplicates while preserving order.
    """
    seen: set[str] = set()
    error_lines: list[str] = []

    def add(line: str) -> None:
        s = line.strip()
        if not s or s in seen:
            return
        seen.add(s)
        error_lines.append(line)

    for line in raw_lines:
        if any(p.search(line) for p in _ERROR_PATTERNS) or is_traceback_start(line):
            add(line)

    if not error_lines and include_warnings:
        for line in raw_lines:
            if any(p.search(line) for p in _WARN_PATTERNS):
                add(line)

    return {"error_lines": error_lines, "count": len(error_lines)}
