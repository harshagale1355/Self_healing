"""
RAG Memory Store: clean façade over ErrorVectorStore for the v3 pipeline.

API:
    store  — persist a resolved error: error, cause, fix, code, type.
    recall — retrieve top-k similar cases with normalised similarity scores.
"""
from __future__ import annotations

from typing import Any

from rag.vector_store import ErrorVectorStore


class MemoryStore:
    """
    Persistent memory of past error resolutions backed by ChromaDB.

    Parameters
    ----------
    enabled : override config.ENABLE_RAG when not None.
    """

    def __init__(self, enabled: bool | None = None) -> None:
        self._vs = ErrorVectorStore(enabled=enabled)

    # ── Write ────────────────────────────────────────────────────────────────

    def store(
        self,
        *,
        error: str,
        cause: str,
        fix: str,
        code: str,
        err_type: str,
    ) -> None:
        """Persist a resolved error to vector memory (silently ignores failures)."""
        try:
            self._vs.add(
                error_line=error,
                cause=cause,
                fix=fix,
                code=code,
                err_type=err_type,
            )
        except Exception:
            pass

    # ── Read ─────────────────────────────────────────────────────────────────

    def recall(self, error: str, k: int = 5) -> list[dict[str, Any]]:
        """
        Return top-k similar past cases.

        Each item: {error, cause, fix, code, type, similarity}
        where similarity ∈ [0, 1] (1 = identical).
        """
        rows = self._vs.query_similar(error, k=k)
        out: list[dict[str, Any]] = []
        for r in rows:
            dist = float(r.get("distance", 1.0))
            # distance is L2 or cosine distance; normalise to [0,1] similarity
            sim = max(0.0, min(1.0, 1.0 - dist))
            out.append(
                {
                    "error": r.get("error", ""),
                    "cause": r.get("cause", ""),
                    "fix": r.get("fix", ""),
                    "code": r.get("code", ""),
                    "type": r.get("type", ""),
                    "similarity": round(sim, 3),
                }
            )
        return out
