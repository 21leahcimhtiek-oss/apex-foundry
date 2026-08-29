"""Inference kernel — model routing with fallback chain.

Path B greenfield. Every agent inference call goes through `complete()`,
which resolves an intent to a model alias and tries each provider in the
fallback chain until one succeeds.
"""

from __future__ import annotations

import os
from typing import Any

MODEL_MAP: dict[str, str] = {
    "research": "openrouter/auto",
    "code": "openrouter/anthropic/claude-3.5-sonnet",
    "simple": "openrouter/openai/gpt-4o-mini",
    "default": "openrouter/openai/gpt-4o-mini",
}

FALLBACK_CHAIN: list[str] = [
    "openrouter/openai/gpt-4o-mini",
    "openai/gpt-4o-mini",
]


def select_model(intent_type: str | None) -> str:
    """Return the model for an intent type. Pure, testable."""
    return MODEL_MAP.get(intent_type or "", MODEL_MAP["default"])


def extract_intent(message: str) -> str:
    """Heuristic intent extraction used before richer classifiers exist."""
    lowered = message.lower()
    if any(k in lowered for k in ("research", "analyze", "compare", "investigate")):
        return "research"
    if any(k in lowered for k in ("code", "function", "bug", "refactor", "script")):
        return "code"
    if len(lowered.split()) <= 6:
        return "simple"
    return "research"


def _client() -> Any:
    """Build an OpenAI-compatible client against OpenRouter (lazy import)."""
    from openai import OpenAI

    return OpenAI(
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
    )


def complete(
    prompt: str,
    intent_type: str | None = None,
    *,
    system: str | None = None,
) -> str:
    """Run one completion with fallback across the chain. Raises last error."""
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    client = _client()
    last_error: Exception | None = None
    for model in [select_model(intent_type), *FALLBACK_CHAIN]:
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages  # type: ignore[arg-type]
            )
            return str(resp.choices[0].message.content)
        except Exception as exc:  # noqa: BLE001 — fallback is the point
            last_error = exc
    raise RuntimeError(f"All inference providers failed: {last_error}") from last_error
