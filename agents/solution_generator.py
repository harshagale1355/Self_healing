"""
Solution Generator Agent: LLM produces cause, fix, code, confidence as JSON.
"""
from __future__ import annotations

from typing import Any

import config
from prompts.prompts import ERROR_ANALYSIS_SYSTEM, build_error_analysis_user_prompt
from utils.llm_client import invoke_json


def generate_solution(
    error_line: str,
    classification: dict[str, Any],
    context_payload: dict[str, Any],
    rag_snippets: list[str] | None = None,
) -> dict[str, Any]:
    """
    Call LLM with structured prompts. Falls back to heuristic if no API key.
    """
    ctx = context_payload.get("context", {})
    snippet = ctx.get("codebase_snippet")

    if not config.has_llm_credentials():
        return _fallback_solution(error_line, classification, ctx)

    user = build_error_analysis_user_prompt(
        error_line=error_line,
        classification_hint=classification,
        context=ctx,
        codebase_snippet=snippet,
        rag_snippets=rag_snippets or [],
    )
    try:
        data = invoke_json(ERROR_ANALYSIS_SYSTEM, user)
        return _normalize_solution(data, error_line, classification, ctx)
    except Exception as e:
        out = _fallback_solution(error_line, classification, ctx)
        out["llm_error"] = str(e)
        return out


def _normalize_solution(
    data: dict[str, Any],
    error_line: str,
    classification: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    conf = data.get("confidence", 0.5)
    try:
        conf = float(conf)
    except (TypeError, ValueError):
        conf = 0.5
    conf = max(0.0, min(1.0, conf))
    return {
        "error": error_line,
        "type": data.get("type") or classification.get("type", "unknown"),
        "cause": data.get("cause", ""),
        "fix": data.get("fix", ""),
        "code": data.get("code", "") or "",
        "confidence": conf,
        "context": ctx,
    }


def _fallback_solution(error_line: str, classification: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "error": error_line,
        "type": classification.get("type", "unknown"),
        "cause": "LLM not configured. Enable OPENAI_API_KEY or GROQ_API_KEY for full analysis.",
        "fix": "Set environment variables and re-run. Check the error message and stack location manually.",
        "code": "",
        "confidence": 0.2,
        "context": ctx,
    }
