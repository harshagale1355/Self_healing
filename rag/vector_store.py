"""
Chroma-backed vector store for structured error → cause → fix → code records.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import config


def _embed(text: str) -> list[float]:
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


def _doc_text(error: str, cause: str, fix: str, code: str) -> str:
    return (
        f"ERROR:\n{error[:4000]}\n\nCAUSE:\n{cause[:2000]}\n\nFIX:\n{fix[:2000]}\n\nCODE:\n{code[:2000]}"
    )


class ErrorVectorStore:
    """
    Stores and queries error resolutions for RAG. Document = full text; metadata = structured strings.
    """

    def __init__(self, collection_name: str = "error_solutions", enabled: bool | None = None) -> None:
        self._collection = None
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

    def add(
        self,
        *,
        error_line: str,
        cause: str,
        fix: str,
        code: str,
        err_type: str,
    ) -> None:
        if self._collection is None:
            return
        uid = hashlib.sha256(
            (error_line + cause + fix).encode("utf-8", errors="replace")
        ).hexdigest()[:32]
        doc = _doc_text(error_line, cause, fix, code)
        emb = _embed(doc)
        if not emb:
            return
        meta = {
            "error": error_line[:4000],
            "cause": cause[:2000],
            "fix": fix[:2000],
            "code": code[:2000],
            "type": err_type[:200],
        }
        try:
            self._collection.upsert(
                ids=[uid],
                embeddings=[emb],
                documents=[doc],
                metadatas=[{k: str(v)[:4000] for k, v in meta.items()}],
            )
        except Exception:
            pass

    def query_similar(self, error_line: str, k: int = 5) -> list[dict[str, Any]]:
        """Return similar past records with cause/fix/code for prompting."""
        if self._collection is None:
            return []
        emb = _embed(error_line[:8000])
        if not emb:
            return []
        try:
            res = self._collection.query(query_embeddings=[emb], n_results=k)
            out: list[dict[str, Any]] = []
            metas = (res or {}).get("metadatas") or []
            docs = (res or {}).get("documents") or []
            dist = (res or {}).get("distances") or []
            if not metas or not metas[0]:
                return []
            for i, m in enumerate(metas[0]):
                if not m:
                    continue
                rec = {
                    "error": m.get("error", ""),
                    "cause": m.get("cause", ""),
                    "fix": m.get("fix", ""),
                    "code": m.get("code", ""),
                    "type": m.get("type", ""),
                }
                if docs and docs[0] and i < len(docs[0]) and docs[0][i]:
                    rec["document"] = docs[0][i][:6000]
                if dist and dist[0] and i < len(dist[0]):
                    rec["distance"] = float(dist[0][i])
                out.append(rec)
            return out
        except Exception:
            return []
