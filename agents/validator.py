"""
Validator Agent — v3.

Calls LLM to critique and optionally improve fix/code.
Passes through all new v3 fields (reason, root_cause, fix_risk, confidence)
without modification so downstream nodes always see a complete record.
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
    All v3 structured fields are preserved unchanged.
    """
    if not config.has_llm_credentials():
        return {**proposed, "validation": {"approved": True, "notes": "skipped_no_llm"}}

    user = build_validation_user_prompt(error_line, proposed)
    try:
        v = invoke_json(VALIDATION_SYSTEM, user)
    except Exception as e:
        return {**proposed, "validation": {"approved": True, "notes": f"validator_error:{e}"}}

    approved = bool(v.get("approved", True))

    # Update confidence.overall from validator if provided; keep other sub-scores
    conf_block = dict(proposed.get("confidence") or {})
    if isinstance(conf_block, dict):
        try:
            vconf = float(v.get("confidence", conf_block.get("overall", 0.5)))
            vconf = max(0.0, min(1.0, vconf))
            conf_block["overall"] = vconf
        except (TypeError, ValueError):
            pass
    else:
        # Legacy flat float — upgrade to dict
        try:
            vconf = float(v.get("confidence", proposed.get("confidence", 0.5)))
        except (TypeError, ValueError):
            vconf = 0.5
        conf_block = {
            "overall": max(0.0, min(1.0, vconf)),
            "pattern_match": 0.5,
            "llm_reasoning": 0.5,
            "context_match": 0.5,
        }

    out = {
        **proposed,
        "fix": v.get("improved_fix") or proposed.get("fix", ""),
        "code": v.get("improved_code") if v.get("improved_code") is not None else proposed.get("code", ""),
        "confidence": conf_block,
        "validation": {
            "approved": approved,
            "notes": v.get("notes", ""),
        },
    }
    return out
