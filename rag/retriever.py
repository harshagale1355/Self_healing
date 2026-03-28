"""
RAG: retrieve similar past errors using ErrorVectorStore; legacy string list for prompts.
"""
from __future__ import annotations

from typing import Any

import config

from rag.vector_store import ErrorVectorStore


class ErrorRAGRetriever:
    """
    Backwards-compatible API: similar() returns text lines for LLM;
    similar_structured() returns dicts for richer prompts.
    """

    def __init__(self, collection_name: str = "error_solutions", enabled: bool | None = None) -> None:
        self._store = ErrorVectorStore(collection_name=collection_name, enabled=enabled)

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

    def similar(self, error_line: str, k: int = 4) -> list[str]:
        """Plain-text lines for prompt inclusion (similarity reasoning)."""
        rows = self.similar_structured(error_line, k=k)
        lines: list[str] = []
        for i, r in enumerate(rows, 1):
            chunk = (
                f"[Past {i}] type={r.get('type','')}\n"
                f"cause: {r.get('cause','')[:500]}\n"
                f"fix: {r.get('fix','')[:500]}\n"
            )
            if r.get("code"):
                chunk += f"code: {r['code'][:400]}\n"
            lines.append(chunk)
        return lines

    def similar_structured(self, error_line: str, k: int = 5) -> list[dict[str, Any]]:
        return self._store.query_similar(error_line, k=k)
