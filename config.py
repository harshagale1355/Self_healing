"""
Central configuration: LLM providers, paths, and runtime flags.
Reads from environment variables with sensible defaults.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

# LLM provider: "openai" | "groq"
LLM_PROVIDER: Literal["openai", "groq"] = os.getenv("LLM_PROVIDER", "openai").lower()  # type: ignore[assignment]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Temperature for analysis (lower = more deterministic JSON)
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# Max retries for transient LLM failures
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))

# RAG / Chroma
CHROMA_PERSIST_DIR = Path(os.getenv("CHROMA_PERSIST_DIR", str(Path.home() / ".ai_debugger_chroma")))
ENABLE_RAG = os.getenv("ENABLE_RAG", "false").lower() in ("1", "true", "yes")

# Log discovery
LOG_EXTENSIONS = tuple(
    x.strip()
    for x in os.getenv("LOG_EXTENSIONS", ".log,.txt,.out,.err").split(",")
    if x.strip()
)
MAX_LOG_FILE_BYTES = int(os.getenv("MAX_LOG_FILE_BYTES", str(5 * 1024 * 1024)))  # 5 MB per file

# Codebase context: max chars read from a referenced project file
MAX_CODE_CONTEXT_CHARS = int(os.getenv("MAX_CODE_CONTEXT_CHARS", "8000"))

# Project root (for imports when running as script)
PROJECT_ROOT = Path(__file__).resolve().parent


def has_llm_credentials() -> bool:
    if LLM_PROVIDER == "groq":
        return bool(GROQ_API_KEY)
    return bool(OPENAI_API_KEY)
