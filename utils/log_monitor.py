"""
Poll a log file for appended content and invoke a callback with new lines (optional monitoring).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from agents.error_filter import filter_error_lines


def watch_log_file(
    log_path: str | Path,
    on_new_lines: Callable[[list[str]], None],
    *,
    poll_interval: float = 1.0,
) -> None:
    """
    Read new bytes from log_path on each poll; pass new error-filtered lines to callback.
    """
    path = Path(log_path).resolve()
    pos = path.stat().st_size if path.exists() else 0
    seen: set[str] = set()

    while True:
        time.sleep(max(0.2, poll_interval))
        try:
            sz = path.stat().st_size
        except OSError:
            continue
        if sz < pos:
            pos = 0
        if sz <= pos:
            continue
        try:
            with path.open("rb") as f:
                f.seek(pos)
                chunk = f.read().decode("utf-8", errors="replace")
            pos = sz
        except OSError:
            continue
        if not chunk.strip():
            continue
        raw_lines = chunk.splitlines()
        err_lines = filter_error_lines(raw_lines)["error_lines"]
        new_errs = [ln for ln in err_lines if ln not in seen]
        for ln in new_errs:
            seen.add(ln)
        if new_errs:
            on_new_lines(new_errs)
