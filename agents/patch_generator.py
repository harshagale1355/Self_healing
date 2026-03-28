"""
Generate unified-diff style patches from suggested code vs surrounding context (LLM + safe fallback).
"""
from __future__ import annotations

from typing import Any

import config
from prompts.prompts import PATCH_SYSTEM, build_patch_user_prompt
from utils.llm_client import invoke_json


def generate_patch(
    error_line: str,
    validated_solution: dict[str, Any],
    codebase_snippet: str | None,
) -> str:
    """
    Returns a unified diff or explanatory text. Never raises — empty patch on total failure.
    """
    suggested = (validated_solution.get("code") or "").strip()
    if not suggested and not codebase_snippet:
        return ""

    if not config.has_llm_credentials():
        return _fallback_patch(suggested)

    user = build_patch_user_prompt(
        error_line=error_line,
        fix_description=validated_solution.get("fix", ""),
        suggested_code=suggested,
        codebase_snippet=codebase_snippet,
    )
    try:
        data = invoke_json(PATCH_SYSTEM, user)
        patch = (data.get("patch") or "").strip()
        if patch and not data.get("unsafe", False):
            return patch
        if data.get("unsafe"):
            return (
                "# Patch withheld: model flagged change as potentially unsafe.\n"
                "# Apply the suggested code manually after review.\n"
                + (suggested or "")
            )
    except Exception:
        pass
    return _fallback_patch(suggested)


def _fallback_patch(suggested: str) -> str:
    if not suggested:
        return "# No patch generated (insufficient context or LLM unavailable)."
    return (
        "# Suggested new code (review before applying — not a unified diff):\n"
        + suggested
    )
