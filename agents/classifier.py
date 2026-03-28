"""
Error Classifier Agent: rule-based + optional LLM refinement for error category.
"""
from __future__ import annotations

import re
from typing import Any

from prompts.prompts import ERROR_TYPES

_RULES: list[tuple[str, list[re.Pattern[str]]]] = [
    (
        "syntax",
        [
            re.compile(r"SyntaxError", re.IGNORECASE),
            re.compile(r"ParseError", re.IGNORECASE),
            re.compile(r"unexpected token", re.IGNORECASE),
        ],
    ),
    (
        "memory",
        [
            re.compile(r"OutOfMemory|MemoryError|heap out of memory", re.IGNORECASE),
            re.compile(r"Cannot allocate memory", re.IGNORECASE),
        ],
    ),
    (
        "dependency",
        [
            re.compile(r"ModuleNotFoundError|ImportError|cannot find module|package not found", re.IGNORECASE),
            re.compile(r"npm ERR!|pip install|No matching distribution", re.IGNORECASE),
        ],
    ),
    (
        "file_system",
        [
            re.compile(r"ENOENT|No such file|not found", re.IGNORECASE),
            re.compile(r"EACCES|Permission denied", re.IGNORECASE),
            re.compile(r"Is a directory|Not a directory", re.IGNORECASE),
        ],
    ),
    (
        "network",
        [
            # Word boundaries avoid matching "eNotFound" inside ModuleNotFoundError
            re.compile(
                r"\bECONNREFUSED\b|\bETIMEDOUT\b|\bENOTFOUND\b|\bECONNRESET\b|\bsocket\b",
                re.IGNORECASE,
            ),
            re.compile(r"NetworkError|fetch failed", re.IGNORECASE),
        ],
    ),
    (
        "database",
        [
            re.compile(r"sql|postgres|mysql|sqlite|mongodb|redis|ORMError|OperationalError", re.IGNORECASE),
        ],
    ),
    (
        "api",
        [
            re.compile(r"\b404\b|\b500\b|\b502\b|\b503\b|HTTP error|status code", re.IGNORECASE),
            re.compile(r"API key|unauthorized|forbidden", re.IGNORECASE),
        ],
    ),
    (
        "config",
        [
            re.compile(r"config|environment variable|missing key|invalid option", re.IGNORECASE),
            re.compile(r"\.env|yaml|json parse", re.IGNORECASE),
        ],
    ),
    (
        "runtime",
        [
            re.compile(r"TypeError|ReferenceError|AttributeError|KeyError|ValueError|NullPointer", re.IGNORECASE),
            re.compile(r"RuntimeError|Exception in thread", re.IGNORECASE),
        ],
    ),
]


def classify_error_line_rules(error_line: str) -> dict[str, Any]:
    """Fast heuristic classification."""
    for etype, pats in _RULES:
        if any(p.search(error_line) for p in pats):
            return {"type": etype, "method": "rules", "scores": {etype: 1.0}}
    return {"type": "unknown", "method": "rules", "scores": {}}


def classify_error(error_line: str, use_llm: bool = False) -> dict[str, Any]:
    """
    Classify a single error line. When use_llm is True and credentials exist, refine type.
    """
    base = classify_error_line_rules(error_line)
    if not use_llm:
        return base
    import config

    if not config.has_llm_credentials():
        return base
    try:
        from utils.llm_client import get_chat_model
        from langchain_core.messages import HumanMessage, SystemMessage

        system = (
            "Classify the log line into exactly one category from "
            + str(ERROR_TYPES)
            + ". Reply with JSON only: {\"type\": \"...\", \"confidence\": 0-1}"
        )
        user = f"Log line:\n{error_line}\n\nPrevious hint: {base.get('type')}"
        model = get_chat_model()
        r = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        text = (r.content or "").strip()
        from utils.llm_client import parse_json_from_text

        data = parse_json_from_text(text)
        t = data.get("type", base["type"])
        if t not in ERROR_TYPES:
            t = base["type"]
        base["type"] = t
        base["method"] = "rules+llm"
        base["llm_confidence"] = float(data.get("confidence", 0.5))
    except Exception:
        base["method"] = "rules"
    return base
