"""
Rule-based severity and priority from error type and log text.
"""
from __future__ import annotations

import re
from typing import Any, Literal

Severity = Literal["low", "medium", "high"]


def assign_severity(
    error_line: str,
    err_type: str,
    classification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    severity: low | medium | high
    priority: 1 (urgent) .. 5 (later), optional
    """
    t = (err_type or "unknown").lower()
    line = error_line.lower()

    # High: crashes, data loss, security, DB down
    if t in ("memory", "database", "runtime"):
        if t == "runtime" and any(
            x in line for x in ("segfault", "panic", "fatal", "abort", "killed")
        ):
            return _out("high", 1)
        if t in ("memory", "database"):
            return _out("high", 1)
        if t == "runtime" and any(
            x in line for x in ("exception", "traceback", "uncaught", "unhandled")
        ):
            return _out("high", 2)

    if any(
        p.search(line)
        for p in (
            re.compile(r"\bpanic\b"),
            re.compile(r"segfault|sigsegv", re.I),
            re.compile(r"out of memory|oom", re.I),
            re.compile(r"connection refused.*db|database.*unavailable", re.I),
        )
    ):
        return _out("high", 1)

    # Medium: config, network flaky, API errors
    if t in ("config", "network", "api", "file_system"):
        return _out("medium", 3)

    if t == "syntax":
        return _out("medium", 2)

    if t == "dependency":
        return _out("medium", 3)

    # Low: warnings-as-errors, unknown
    if "warn" in line:
        return _out("low", 5)

    return _out("medium", 4)


def _out(severity: Severity, priority: int) -> dict[str, Any]:
    return {"severity": severity, "priority": priority}
