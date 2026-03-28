"""
Validator Agent: checks LLM solution JSON and optionally improves it.
"""
from __future__ import annotations

from typing import Any

import config
from prompts.prompts import VALIDATION_SYSTEM, build_validation_user_prompt
from utils.llm_client import invoke_json


def validate_solution(
    error_line: str,
    proposed: dict[str, Any],
) -> dict[str, Any]:
    """
    Returns merged result with possibly improved fix/code and adjusted confidence.
    """
    if not config.has_llm_credentials():
        return {**proposed, "validation": {"approved": True, "notes": "skipped_no_llm"}}

    user = build_validation_user_prompt(error_line, proposed)
    try:
        v = invoke_json(VALIDATION_SYSTEM, user)
    except Exception as e:
        return {**proposed, "validation": {"approved": True, "notes": f"validator_error:{e}"}}

    approved = bool(v.get("approved", True))
    conf = proposed.get("confidence", 0.5)
    try:
        vconf = float(v.get("confidence", conf))
        conf = max(0.0, min(1.0, vconf))
    except (TypeError, ValueError):
        pass

    out = {
        **proposed,
        "fix": v.get("improved_fix") or proposed.get("fix", ""),
        "code": v.get("improved_code") if v.get("improved_code") is not None else proposed.get("code", ""),
        "confidence": conf,
        "validation": {
            "approved": approved,
            "notes": v.get("notes", ""),
        },
    }
    return out
