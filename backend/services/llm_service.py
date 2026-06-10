"""Groq LLM service with JSON-mode calls and robust parsing/retries.

Key design points:
* Uses the free Groq API (``GROQ_API_KEY``).
* ``complete_json`` asks the model for strict JSON and retries on parse
  failures (requirement #5 — LLM retry if output JSON parsing fails).
* If the key is missing OR every retry fails, callers receive a clearly
  signalled error so the workflow can degrade gracefully instead of crashing.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

# Lazily-initialised client so importing the module never crashes when the
# key is absent (e.g. during tests or first-time setup).
_client = None


class LLMError(RuntimeError):
    """Raised when the LLM cannot return usable output."""


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not GROQ_API_KEY:
        raise LLMError(
            "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
            "and add a free key from https://console.groq.com/keys"
        )
    from groq import Groq  # imported here so the module loads without the dep

    _client = Groq(api_key=GROQ_API_KEY)
    return _client


def is_configured() -> bool:
    return bool(GROQ_API_KEY)


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> Any:
    """Best-effort extraction of a JSON object/array from an LLM response."""
    text = text.strip()
    # Strip code fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to the first balanced {...} or [...] block.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("No valid JSON found in LLM output")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def complete_json(system: str, user: str, *, max_retries: int = 3,
                  temperature: float = 0.2) -> Any:
    """Call Groq in JSON mode and return the parsed object.

    Retries with an increasingly explicit "return valid JSON only" nudge if
    parsing fails.
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    last_err: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content or ""
            return _extract_json(content)
        except Exception as exc:  # parse error or transient API error
            last_err = exc
            # Reinforce the JSON requirement for the next attempt.
            messages.append({
                "role": "user",
                "content": ("Your previous reply could not be parsed as JSON. "
                            "Reply again with ONLY valid minified JSON, no prose, "
                            "no markdown fences."),
            })

    raise LLMError(f"LLM JSON parsing failed after {max_retries} attempts: {last_err}")
