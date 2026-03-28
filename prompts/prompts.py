"""
Prompt templates for error analysis and validation (strict JSON outputs) — v3.

New fields requested from LLM:
  reason        : {immediate, root, why_fix_works}
  confidence    : {overall, pattern_match, llm_reasoning, context_match}
  root_cause    : {level_1, level_2, level_3}
  fix_risk      : {level, reason}
  similar_cases : injected from RAG into user prompt
"""
from __future__ import annotations

import json
from typing import Any

import config as app_config

ERROR_TYPES = [
    "syntax",
    "runtime",
    "memory",
    "file_system",
    "network",
    "database",
    "api",
    "dependency",
    "config",
    "unknown",
]

ERROR_ANALYSIS_SYSTEM = (
    "You are an expert software debugger and root-cause analyst.\n"
    "Analyze the provided log error line and structured context.\n"
    "You MUST respond with a single JSON object only — no markdown fences, no extra text.\n\n"
    "Required schema (all fields mandatory):\n"
    "{\n"
    '  "type": one of ' + json.dumps(ERROR_TYPES) + ",\n"
    '  "cause": "short immediate cause explanation",\n'
    '  "fix": "actionable fix description",\n'
    '  "code": "corrected code snippet or empty string",\n'
    '  "reason": {\n'
    '    "immediate": "what triggered the error right now",\n'
    '    "root": "underlying design or code issue causing this",\n'
    '    "why_fix_works": "explain why the proposed fix resolves it"\n'
    "  },\n"
    '  "confidence": {\n'
    '    "overall": 0.0-1.0,\n'
    '    "pattern_match": 0.0-1.0,\n'
    '    "llm_reasoning": 0.0-1.0,\n'
    '    "context_match": 0.0-1.0\n'
    "  },\n"
    '  "root_cause": {\n'
    '    "level_1": "immediate error (e.g., division by zero)",\n'
    '    "level_2": "code issue (e.g., missing validation)",\n'
    '    "level_3": "system/design issue (e.g., lack of input checks)"\n'
    "  },\n"
    '  "fix_risk": {\n'
    '    "level": "low | medium | high",\n'
    '    "reason": "explain why this risk level was assigned"\n'
    "  }\n"
    "}\n\n"
    "Rules:\n"
    "- type must be the best matching category from the list.\n"
    "- code should be minimal, correct, and language-appropriate.\n"
    "- fix_risk.level = low for small local changes, medium for dependency/config changes, high for system-wide changes.\n"
    "- confidence scores must reflect your actual certainty — do not default everything to 0.9.\n"
    "- If information is insufficient, set type to 'unknown', lower confidence, and explain in cause.\n"
    "- Return the JSON object ONLY — no prose before or after."
)


def build_error_analysis_user_prompt(
    error_line: str,
    classification_hint: dict[str, Any],
    context: dict[str, Any],
    codebase_snippet: str | None,
    rag_snippets: list[str] | None,
) -> str:
    parts = [
        "Error line:",
        error_line,
        "\nClassifier hint (may be wrong):",
        json.dumps(classification_hint, ensure_ascii=False, indent=2),
        "\nStructured context:",
        json.dumps(context, ensure_ascii=False, indent=2),
    ]
    if codebase_snippet:
        cap = app_config.MAX_CODE_CONTEXT_CHARS
        parts.extend(["\nRelevant project file excerpt:\n", codebase_snippet[:cap]])
    if rag_snippets:
        parts.extend(
            [
                "\nSimilar past errors from memory (use to improve accuracy):",
                "\n---\n".join(rag_snippets[:8]),
            ]
        )
    parts.append(
        "\nReturn only the JSON object. Include all required fields: "
        "type, cause, fix, code, reason, confidence, root_cause, fix_risk."
    )
    return "\n".join(parts)


VALIDATION_SYSTEM = (
    "You are a strict code-review assistant. Given an error and a proposed solution JSON, verify plausibility.\n"
    "Respond with a single JSON object only:\n"
    "{\n"
    '  "approved": true or false,\n'
    '  "confidence": 0-1,\n'
    '  "improved_fix": "use original fix if nothing to improve",\n'
    '  "improved_code": "use original code if nothing to improve",\n'
    '  "notes": "brief rationale"\n'
    "}\n"
    "If approved is false, improve improved_fix / improved_code when possible."
)


def build_validation_user_prompt(
    error_line: str,
    proposed: dict[str, Any],
) -> str:
    # Strip heavy fields to keep token count manageable
    slim = {
        k: proposed[k]
        for k in ("error", "type", "cause", "fix", "code", "confidence")
        if k in proposed
    }
    return (
        "Original error line:\n"
        f"{error_line}\n\n"
        "Proposed solution JSON:\n"
        f"{json.dumps(slim, ensure_ascii=False, indent=2)}\n\n"
        "Validate and return only the validation JSON."
    )


PATCH_SYSTEM = (
    "You produce a minimal, safe unified-diff style patch OR a clear code replacement block.\n"
    "Respond with a single JSON object only:\n"
    "{\n"
    '  "patch": "unified diff (preferred) or commented replacement block",\n'
    '  "unsafe": false,\n'
    '  "notes": "brief note if patch is abbreviated"\n'
    "}\n"
    "Rules:\n"
    "- Prefer unified diff format (---/+++ lines, @@ hunk headers) when old/new lines are clear.\n"
    "- If you cannot form a safe diff, set patch to the exact new code block with a short comment prefix and unsafe=false.\n"
    "- Set unsafe=true only if applying the change could delete data, expose secrets, or break production.\n"
    "- Do not include markdown fences."
)


def build_patch_user_prompt(
    error_line: str,
    fix_description: str,
    suggested_code: str,
    codebase_snippet: str | None,
) -> str:
    parts = [
        "Log error line:",
        error_line,
        "\nFix description:",
        fix_description,
        "\nModel-suggested corrected code:",
        suggested_code or "(none)",
    ]
    if codebase_snippet:
        parts.extend(
            [
                "\nSurrounding file context (line numbers may help build diff):\n",
                codebase_snippet[: app_config.MAX_CODE_CONTEXT_CHARS],
            ]
        )
    parts.append("\nReturn only the JSON object with patch and unsafe fields.")
    return "\n".join(parts)
