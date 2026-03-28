"""
Log Reader Agent: reads discovered log files and returns all lines with metadata.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.file_scanner import discover_log_files


def read_logs(project_path: str | Path) -> dict[str, Any]:
    """
    Discover log files under project_path and read their contents (UTF-8 with replacement).
    Returns dict with keys: log_paths (list of str), raw_lines (list of str),
    lines_by_file (list of {path, lines}).
    """
    root = Path(project_path).resolve()
    paths = discover_log_files(root)
    raw_lines: list[str] = []
    lines_by_file: list[dict[str, Any]] = []

    for p in paths:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        prefixed = [f"[{p.relative_to(root)}] {ln}" for ln in lines]
        raw_lines.extend(prefixed)
        lines_by_file.append({"path": str(p), "lines": lines})

    return {
        "project_path": str(root),
        "log_paths": [str(p) for p in paths],
        "raw_lines": raw_lines,
        "lines_by_file": lines_by_file,
    }
