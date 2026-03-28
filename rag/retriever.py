"""
RAG Retriever — v3.

similar()              → list[str]        (plain text for prompt injection)
similar_structured()   → list[dict]       (full records, normalised similarity)
similar_cases_for_output() → list[dict]   (slim format for JSON result output)
"""
from __future__ import annotations

from typing import Any

import config

from rag.vector_store import ErrorVectorStore


class ErrorRAGRetriever:
    """
    Backwards-compatible API: similar() returns text lines for LLM;
    similar_structured() returns dicts for richer prompts.
    similar_cases_for_output() returns the slim JSON-ready list for UI.
    """

    def __init__(self, collection_name: str = "error_solutions", enabled: bool | None = None) -> None:
        self._store = ErrorVectorStore(collection_name=collection_name, enabled=enabled)

    # ── Write ────────────────────────────────────────────────────────────────

    def add_error(self, error_line: str, metadata: dict[str, Any] | None = None) -> None:
        """Legacy: map flat metadata to structured add when possible."""
        meta = metadata or {}
        self._store.add(
            error_line=error_line,
            cause=str(meta.get("cause", "")),
            fix=str(meta.get("fix", "")),
            code=str(meta.get("code", "")),
            err_type=str(meta.get("type", "unknown")),
        )

    def add_resolution(
        self,
        *,
        error_line: str,
        cause: str,
        fix: str,
        code: str,
        err_type: str,
    ) -> None:
        self._store.add(
            error_line=error_line,
            cause=cause,
            fix=fix,
            code=code,
            err_type=err_type,
        )

    # ── Read ─────────────────────────────────────────────────────────────────

    def similar(self, error_line: str, k: int = 4) -> list[str]:
        """Plain-text lines for prompt inclusion."""
        rows = self.similar_structured(error_line, k=k)
        lines: list[str] = []
        for i, r in enumerate(rows, 1):
            chunk = (
                f"[Past {i}] type={r.get('type', '')}\n"
                f"cause: {r.get('cause', '')[:500]}\n"
                f"fix: {r.get('fix', '')[:500]}\n"
            )
            if r.get("code"):
                chunk += f"code: {r['code'][:400]}\n"
            lines.append(chunk)
        return lines

    def similar_structured(self, error_line: str, k: int = 5) -> list[dict[str, Any]]:
        """Full records from vector store with normalised similarity score."""
        rows = self._store.query_similar(error_line, k=k)
        out: list[dict[str, Any]] = []
        for r in rows:
            dist = float(r.get("distance", 1.0))
            # normalise L2/cosine distance → [0,1] similarity
            similarity = round(max(0.0, min(1.0, 1.0 - dist)), 3)
            out.append({**r, "similarity": similarity})
        return out

    def similar_cases_for_output(self, error_line: str, k: int = 3) -> list[dict[str, Any]]:
        """
        Slim list suitable for embedding in the final JSON result and UI display.
        Each item: {error, fix, similarity}
        """
        rows = self.similar_structured(error_line, k=k)
        return [
            {
                "error": r.get("error", "")[:300],
                "fix": r.get("fix", "")[:300],
                "similarity": r.get("similarity", 0.0),
            }
            for r in rows
        ]
