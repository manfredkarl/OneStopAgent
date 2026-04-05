"""Shared utility helpers used across agents and services."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code-fence lines from LLM output.

    Handles both ````json`` and plain ```` ``` ```` delimiters.
    """
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (e.g. ```json\n or ```\n)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # Remove closing fence
        text = text.rsplit("```", 1)[0]
    return text.strip()


def parse_leading_int(s: str) -> int:
    """Parse the leading integer from a string like '3 live' → 3.

    Returns 0 if no leading integer is found.
    """
    m = re.match(r"\s*(\d+)", s)
    return int(m.group(1)) if m else 0


def parse_llm_json(
    response_content: str,
    fallback: Any = None,
    *,
    label: str = "LLM",
) -> Any:
    """Strip markdown fences and parse JSON from an LLM response.

    This replaces the repeated pattern:
        text = strip_markdown_fences(response.content)
        result = json.loads(text)

    Parameters
    ----------
    response_content:
        The raw ``.content`` string from an LLM response.
    fallback:
        Value returned when parsing fails.  Defaults to ``None``.
    label:
        Short label used in warning messages (e.g. agent name).

    Returns
    -------
    The parsed Python object, or *fallback* on any parse error.
    """
    try:
        text = strip_markdown_fences(response_content)
        return json.loads(text)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("%s: JSON parse failed — %s (content[:200]: %s)", label, exc, response_content[:200])
        return fallback
