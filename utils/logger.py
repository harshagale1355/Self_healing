"""
Structured logging and pipeline metrics (counts, timings, success rate).
"""
from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any


def get_logger(name: str = "ai_debugger") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    return log


@dataclass
class PipelineMetrics:
    """Cumulative metrics for one analysis run."""

    errors_processed: int = 0
    llm_success: int = 0
    llm_failures: int = 0
    total_processing_seconds: float = 0.0
    started_at: float = field(default_factory=time.perf_counter)
    errors_by_severity: dict[str, int] = field(default_factory=dict)

    def record_error(
        self,
        *,
        duration_s: float,
        llm_ok: bool,
        severity: str | None = None,
    ) -> None:
        self.errors_processed += 1
        self.total_processing_seconds += duration_s
        if llm_ok:
            self.llm_success += 1
        else:
            self.llm_failures += 1
        if severity:
            self.errors_by_severity[severity] = self.errors_by_severity.get(severity, 0) + 1

    def success_rate(self) -> float:
        n = self.llm_success + self.llm_failures
        if n == 0:
            return 1.0
        return self.llm_success / n

    def to_dict(self) -> dict[str, Any]:
        elapsed = time.perf_counter() - self.started_at
        return {
            "errors_processed": self.errors_processed,
            "llm_success": self.llm_success,
            "llm_failures": self.llm_failures,
            "success_rate": round(self.success_rate(), 4),
            "total_processing_seconds": round(self.total_processing_seconds, 4),
            "wall_clock_seconds": round(elapsed, 4),
            "errors_by_severity": dict(self.errors_by_severity),
        }


def merge_metrics_dict(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Reducer for LangGraph state: merge metric increments."""
    o = dict(old or {})
    n = new or {}
    o["errors_processed"] = o.get("errors_processed", 0) + n.get("errors_processed", 0)
    o["llm_success"] = o.get("llm_success", 0) + n.get("llm_success", 0)
    o["llm_failures"] = o.get("llm_failures", 0) + n.get("llm_failures", 0)
    o["total_processing_seconds"] = round(
        float(o.get("total_processing_seconds", 0.0)) + float(n.get("total_processing_seconds", 0.0)),
        4,
    )
    # merge severity histograms
    bs = dict(o.get("errors_by_severity") or {})
    for k, v in (n.get("errors_by_severity") or {}).items():
        bs[k] = bs.get(k, 0) + int(v)
    o["errors_by_severity"] = bs
    return o
