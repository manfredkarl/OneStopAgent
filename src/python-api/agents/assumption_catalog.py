"""Assumption question dedup catalog.

Prevents downstream agents (Cost, BV) from re-asking questions whose
answers are already available in the shared assumptions collected by the
orchestrator.  Works by matching LLM-generated question IDs against a
set of known canonical names and semantic aliases.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Canonical field names from SharedAssumptions
SHARED_ASSUMPTION_IDS: set[str] = {
    "current_annual_spend",
    "hourly_labor_rate",
    "total_users",
    "concurrent_users",
    "data_volume_gb",
    "timeline_months",
    "monthly_revenue",
}

# LLM-generated aliases that semantically overlap with shared fields.
# If an agent question uses any of these IDs, it's asking for something
# the shared assumptions already cover.
SEMANTIC_OVERLAPS: set[str] = {
    # Spend aliases
    "annual_it_budget",
    "annual_spend",
    "annual_it_spend",
    "monthly_it_spend",
    "monthly_spend",
    "current_spend",
    "yearly_cost",
    "total_annual_spend",
    "current_annual_engineering_toolchain_spend",
    "current_annual_engineering_spend",
    "current_annual_toolchain_spend",
    "current_annual_operational_spend",
    "current_annual_platform_spend",
    "it_budget",
    # Labor rate aliases
    "labor_rate",
    "hourly_rate",
    "fully_loaded_engineering_labor_rate",
    "fully_loaded_hourly_rate",
    "loaded_labor_rate",
    "cost_per_hour",
    "engineer_hourly_rate",
    # User count aliases
    "employees",
    "headcount",
    "total_employees",
    "num_users",
    "active_users",
    "active_rd_engineering_users",
    "platform_users",
    "number_of_users",
    "team_size",
    # Concurrent users aliases
    "peak_users",
    "peak_concurrent_users",
    "simultaneous_users",
    "max_concurrent",
    # Data volume aliases
    "data_storage_gb",
    "storage_gb",
    "data_size",
    "data_volume",
}

# Combined blocklist — questions with these IDs are filtered out
BLOCKED_IDS: set[str] = SHARED_ASSUMPTION_IDS | SEMANTIC_OVERLAPS


def filter_already_answered(
    questions: list[dict[str, Any]],
    state: Any,
) -> list[dict[str, Any]]:
    """Remove questions whose answers are already in shared assumptions.

    Args:
        questions: List of question dicts, each with an ``"id"`` key.
        state: AgentState instance (reads ``shared_assumptions`` keys).

    Returns:
        Filtered list with redundant questions removed.
    """
    if not questions:
        return []

    # Build the set of IDs to block: canonical + aliases + whatever
    # keys are already present in the raw shared_assumptions dict
    sa_keys = set(state.shared_assumptions.keys()) if state.shared_assumptions else set()
    blocked = BLOCKED_IDS | sa_keys

    filtered: list[dict[str, Any]] = []
    for q in questions:
        qid = q.get("id", "")
        if qid in blocked:
            logger.debug("Dedup: filtered question %r (already answered)", qid)
            continue
        filtered.append(q)

    if len(filtered) < len(questions):
        logger.info(
            "Dedup: filtered %d/%d questions (already in shared assumptions)",
            len(questions) - len(filtered), len(questions),
        )

    return filtered
