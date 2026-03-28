"""
Optional RAG: store error embeddings in ChromaDB and retrieve similar past errors.
"""
from __future__ import annotations

import hashlib
from typing import Any

import config


def _embed(text: str) -> list[float]:
    """Prefer local Chroma default embeddings; fall back to OpenAI if configured."""
    try:
        import chromadb.utils.embedding_functions as ef

        fn = ef.DefaultEmbeddingFunction()
        vec = fn([text])
        if vec is not None and len(vec) > 0:
            return list(vec[0])
    except Exception:
        pass
    if config.OPENAI_API_KEY:
        try:
            from langchain_openai import OpenAIEmbeddings

            emb = OpenAIEmbeddings(api_key=config.OPENAI_API_KEY)
            return list(emb.embed_query(text))
        except Exception:
            pass
    return []


class ErrorRAGRetriever:
    """
    Thin wrapper around Chroma persistent client.
    If chromadb or embeddings fail, methods become no-ops and return empty lists.
    """

    def __init__(self, collection_name: str = "log_errors", enabled: bool | None = None) -> None:
        self._collection = None
        self._collection_name = collection_name
        self._enabled = config.ENABLE_RAG if enabled is None else enabled
        if not self._enabled:
            return
        try:
            import chromadb
            from chromadb.config import Settings

            config.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(
                path=str(config.CHROMA_PERSIST_DIR),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(name=collection_name)
        except Exception:
            self._collection = None

    def add_error(self, error_line: str, metadata: dict[str, Any] | None = None) -> None:
        if self._collection is None:
            return
        meta = metadata or {}
        uid = hashlib.sha256(error_line.encode("utf-8", errors="replace")).hexdigest()[:32]
        emb = _embed(error_line)
        if not emb:
            return
        # Chroma metadata: flat strings only
        flat: dict[str, str] = {str(k): str(v)[:4000] for k, v in meta.items()}
        try:
            self._collection.upsert(
                ids=[uid],
                embeddings=[emb],
                documents=[error_line[:8000]],
                metadatas=[flat],
            )
        except Exception:
            pass

    def similar(self, error_line: str, k: int = 4) -> list[str]:
        if self._collection is None:
            return []
        emb = _embed(error_line)
        if not emb:
            return []
        try:
            res = self._collection.query(query_embeddings=[emb], n_results=k)
            docs = (res or {}).get("documents") or []
            if docs and docs[0]:
                return [d for d in docs[0] if d]
        except Exception:
            pass
        return []
