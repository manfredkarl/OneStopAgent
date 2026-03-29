"""Two-phase assumption input handling helpers.

These pure functions parse user-supplied assumption values and build
default-value lists used by business_value and cost agents.

FRD-01 §5 (two-phase inputs).
"""

import json


def parse_assumption_json(message: str) -> list | None:
    """Try to parse *message* as a JSON array of ``{id, value}`` dicts.

    Returns the parsed list on success, or *None* if the message is not
    a valid assumption-value payload.
    """
    try:
        data = json.loads(message)
        if isinstance(data, list) and all(
            isinstance(d, dict) and "id" in d and "value" in d
            for d in data
        ):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def build_default_values(assumptions: list) -> list:
    """Build a list of ``{id, label, value, unit}`` dicts from *assumptions*.

    Each element in *assumptions* is expected to be a dict with at least
    ``id``, ``label``, ``default``, and optionally ``unit`` keys — the
    format produced by the business_value and cost agents when they emit
    an ``assumptions_needed`` list.
    """
    return [
        {
            "id": a["id"],
            "label": a["label"],
            "value": a["default"],
            "unit": a.get("unit", ""),
        }
        for a in assumptions
    ]
