"""
Discover log files under a project directory with safe size limits.
"""
from __future__ import annotations

import os
from pathlib import Path

import config


def discover_log_files(
    project_root: str | Path,
    extensions: tuple[str, ...] | None = None,
    max_bytes_per_file: int | None = None,
) -> list[Path]:
    """
    Recursively find files whose suffix matches known log extensions.
    Skips common heavy dirs (venv, .git, node_modules, __pycache__).
    """
    root = Path(project_root).resolve()
    exts = extensions if extensions is not None else config.LOG_EXTENSIONS
    max_b = max_bytes_per_file if max_bytes_per_file is not None else config.MAX_LOG_FILE_BYTES

    skip_dirs = {
        ".git",
        "venv",
        ".venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".tox",
    }

    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            p = Path(dirpath) / name
            try:
                if not p.is_file():
                    continue
                suf = p.suffix.lower()
                if suf not in exts and not name.lower().endswith(".log"):
                    continue
                if p.stat().st_size > max_b:
                    continue
                found.append(p)
            except OSError:
                continue
    return sorted(found)
