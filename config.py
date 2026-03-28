"""
Central configuration: LLM providers, paths, and runtime flags.
Loads `.env` from the project root (if present), then reads environment variables.
Existing shell env vars override `.env` (override=False).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    """Load GROQ_API_KEY / OPENAI_API_KEY from a local `.env` file when python-dotenv is installed."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    except ImportError:
        pass


_load_dotenv()

# Keys from environment / `.env` (loaded above)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Provider: explicit LLM_PROVIDER wins; else prefer Groq when GROQ_API_KEY is set (typical `.env` setup)
_explicit_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
if _explicit_provider in ("openai", "groq"):
    LLM_PROVIDER: Literal["openai", "groq"] = _explicit_provider  # type: ignore[assignment]
elif GROQ_API_KEY:
    LLM_PROVIDER = "groq"  # type: ignore[assignment]
elif OPENAI_API_KEY:
    LLM_PROVIDER = "openai"  # type: ignore[assignment]
else:
    LLM_PROVIDER = "openai"  # type: ignore[assignment] — no keys; has_llm_credentials() is False

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
# Lines around error line (total window ≈ before + 1 + after, capped by MAX_CODE_CONTEXT_CHARS)
CODE_CONTEXT_LINES_BEFORE = int(os.getenv("CODE_CONTEXT_LINES_BEFORE", "5"))
CODE_CONTEXT_LINES_AFTER = int(os.getenv("CODE_CONTEXT_LINES_AFTER", "5"))


def has_llm_credentials() -> bool:
    if LLM_PROVIDER == "groq":
        return bool(GROQ_API_KEY)
    return bool(OPENAI_API_KEY)
