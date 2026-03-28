"""
Prompt templates for error analysis and validation (strict JSON outputs).
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

ERROR_ANALYSIS_SYSTEM = """You are an expert software debugger. Analyze log error lines and structured context.
You MUST respond with a single JSON object only, no markdown fences, no extra text.
Schema:
{
  "type": one of """ + json.dumps(ERROR_TYPES) + """,
  "cause": "short root-cause explanation",
  "fix": "actionable fix description",
  "code": "corrected code snippet or empty string if not applicable",
  "confidence": number between 0 and 1
}
Rules:
- "type" must be the best matching category from the list.
- "code" should be minimal, correct, and language-appropriate when the error is code-related.
- If information is insufficient, set type to "unknown", lower confidence, and explain in cause.
"""


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
                "\nSimilar past errors (RAG):",
                "\n---\n".join(rag_snippets[:8]),
            ]
        )
    parts.append("\nReturn only the JSON object.")
    return "\n".join(parts)


VALIDATION_SYSTEM = """You are a strict code review assistant. Given an error and a proposed solution JSON, verify plausibility.
Respond with a single JSON object only:
{
  "approved": true or false,
  "confidence": 0-1,
  "improved_fix": "string — use original fix if nothing to improve",
  "improved_code": "string — use original code if nothing to improve",
  "notes": "brief rationale"
}
If approved is false, you must improve improved_fix / improved_code when possible.
"""


def build_validation_user_prompt(
    error_line: str,
    proposed: dict[str, Any],
) -> str:
    return (
        "Original error line:\n"
        f"{error_line}\n\n"
        "Proposed solution JSON:\n"
        f"{json.dumps(proposed, ensure_ascii=False, indent=2)}\n\n"
        "Validate and return only the validation JSON."
    )


PATCH_SYSTEM = """You produce a minimal, safe unified-diff style patch OR a clear code replacement block.
Respond with a single JSON object only:
{
  "patch": "string — unified diff (preferred) or commented replacement block",
  "unsafe": false,
  "notes": "brief note if patch is abbreviated"
}
Rules:
- Prefer unified diff format (---/+++ lines, @@ hunk headers) when old/new lines are clear.
- If you cannot form a safe diff, set patch to the exact new code block with a short comment prefix and unsafe=false.
- Set unsafe=true only if applying the change could delete data, expose secrets, or break production; then patch should explain why.
- Do not include markdown fences.
"""


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
        parts.extend(["\nSurrounding file context (line numbers may help build diff):\n", codebase_snippet[: app_config.MAX_CODE_CONTEXT_CHARS]])
    parts.append("\nReturn only the JSON object with patch and unsafe fields.")
    return "\n".join(parts)
