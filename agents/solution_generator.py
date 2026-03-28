"""
Solution Generator Agent — v3.

LLM produces: cause, fix, code, confidence (dict), reason, root_cause, fix_risk.
Falls back to heuristic stubs when no API key is configured.
"""
from __future__ import annotations

from typing import Any

import config
from prompts.prompts import ERROR_ANALYSIS_SYSTEM, build_error_analysis_user_prompt
from utils.llm_client import invoke_json

# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val: Any, default: float = 0.5) -> float:
    try:
        f = float(val)
        return max(0.0, min(1.0, f))
    except (TypeError, ValueError):
        return default


def _normalize_confidence(raw: Any) -> dict[str, float]:
    """Accept either a float (legacy) or the new dict form."""
    if isinstance(raw, dict):
        return {
            "overall": _safe_float(raw.get("overall", 0.5)),
            "pattern_match": _safe_float(raw.get("pattern_match", 0.5)),
            "llm_reasoning": _safe_float(raw.get("llm_reasoning", 0.5)),
            "context_match": _safe_float(raw.get("context_match", 0.5)),
        }
    v = _safe_float(raw, 0.5)
    return {"overall": v, "pattern_match": v, "llm_reasoning": v, "context_match": v}


def _normalize_reason(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {
            "immediate": str(raw.get("immediate", "")),
            "root": str(raw.get("root", "")),
            "why_fix_works": str(raw.get("why_fix_works", "")),
        }
    return {"immediate": str(raw or ""), "root": "", "why_fix_works": ""}


def _normalize_root_cause(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {
            "level_1": str(raw.get("level_1", "")),
            "level_2": str(raw.get("level_2", "")),
            "level_3": str(raw.get("level_3", "")),
        }
    return {"level_1": str(raw or ""), "level_2": "", "level_3": ""}


def _normalize_fix_risk(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        level = str(raw.get("level", "medium")).lower()
        if level not in ("low", "medium", "high"):
            level = "medium"
        return {"level": level, "reason": str(raw.get("reason", ""))}
    return {"level": "medium", "reason": ""}


# ── Public API ────────────────────────────────────────────────────────────────

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
    return {
        "error": error_line,
        "type": data.get("type") or classification.get("type", "unknown"),
        "cause": data.get("cause", ""),
        "fix": data.get("fix", ""),
        "code": data.get("code", "") or "",
        # v3 structured fields
        "confidence": _normalize_confidence(data.get("confidence", 0.5)),
        "reason": _normalize_reason(data.get("reason")),
        "root_cause": _normalize_root_cause(data.get("root_cause")),
        "fix_risk": _normalize_fix_risk(data.get("fix_risk")),
        # pass-through for downstream nodes
        "context": ctx,
    }


def _fallback_solution(
    error_line: str,
    classification: dict[str, Any],
    ctx: dict[str, Any],
) -> dict[str, Any]:
    err_type = classification.get("type", "unknown")
    return {
        "error": error_line,
        "type": err_type,
        "cause": "LLM not configured. Enable OPENAI_API_KEY or GROQ_API_KEY for full analysis.",
        "fix": "Set environment variables and re-run. Check the error message and stack trace manually.",
        "code": "",
        "confidence": {
            "overall": 0.2,
            "pattern_match": 0.5,
            "llm_reasoning": 0.0,
            "context_match": 0.2,
        },
        "reason": {
            "immediate": error_line[:200],
            "root": "Unable to perform deep analysis without LLM credentials.",
            "why_fix_works": "Rule-based fallback — configure an LLM provider for explanations.",
        },
        "root_cause": {
            "level_1": error_line[:200],
            "level_2": "Code-level cause requires LLM analysis.",
            "level_3": "System-level cause requires LLM analysis.",
        },
        "fix_risk": {
            "level": "medium",
            "reason": "Risk cannot be assessed without LLM analysis.",
        },
        "context": ctx,
    }
