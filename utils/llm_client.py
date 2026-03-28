"""
Shared LLM factory and JSON chat helper with retries.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

import config

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def get_chat_model():
    """Return a LangChain chat model based on config.LLM_PROVIDER."""
    if config.LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq

        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not set.")
        return ChatGroq(
            model=config.GROQ_MODEL,
            temperature=config.LLM_TEMPERATURE,
            api_key=config.GROQ_API_KEY,
        )
    from langchain_openai import ChatOpenAI

    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return ChatOpenAI(
        model=config.OPENAI_MODEL,
        temperature=config.LLM_TEMPERATURE,
        api_key=config.OPENAI_API_KEY,
    )


def invoke_json(
    system: str,
    user: str,
    *,
    max_retries: int | None = None,
) -> dict[str, Any]:
    """
    Invoke chat model and parse JSON from response (handles optional ```json fences).
    """
    retries = max_retries if max_retries is not None else config.LLM_MAX_RETRIES
    model = get_chat_model()
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = model.invoke(messages)
            text = (resp.content or "").strip()
            parsed = _parse_json_loose(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception as e:
            last_err = e
        time.sleep(0.4 * (attempt + 1))
    if last_err:
        raise last_err
    raise ValueError("Failed to obtain valid JSON from LLM")


def parse_json_from_text(text: str) -> Any:
    """Strip optional markdown fences and parse JSON."""
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    return json.loads(text)


def _parse_json_loose(text: str) -> Any:
    return parse_json_from_text(text)
