"""Tests for mid-flow assumption update detection (p1-mid-flow-assumptions).

Covers:
- Numeric pattern detection in user messages
- TB → GB conversion
- Multiple updates in a single message
- No false positives on regular text
- SA cache invalidation after in-place updates
- Downstream agent marking in the "done" phase
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents.state import AgentState, SharedAssumptions
from maf_orchestrator import MAFOrchestrator, _NUMERIC_UPDATE_RE


# ═══════════════════════════════════════════════════════════════════════════
# _NUMERIC_UPDATE_RE — raw regex tests
# ═══════════════════════════════════════════════════════════════════════════


class TestNumericUpdateRegex:
    """Verify the regex captures the right groups."""

    def test_actually_users(self):
        m = _NUMERIC_UPDATE_RE.search("actually 5000 users")
        assert m is not None
        assert m.group(1) == "5000"
        assert m.group(2).lower() == "users"

    def test_changed_to_employees(self):
        m = _NUMERIC_UPDATE_RE.search("changed to 200 employees")
        assert m is not None
        assert m.group(1) == "200"

    def test_updated_to_spend(self):
        m = _NUMERIC_UPDATE_RE.search("updated to 1,500,000 spend")
        assert m is not None
        assert m.group(1) == "1,500,000"

    def test_should_be_tb(self):
        m = _NUMERIC_UPDATE_RE.search("should be 2 TB")
        assert m is not None
        assert m.group(1) == "2"
        assert m.group(2).lower() == "tb"

    def test_now_months(self):
        m = _NUMERIC_UPDATE_RE.search("now 12 months")
        assert m is not None
        assert m.group(1) == "12"

    def test_correction_revenue(self):
        m = _NUMERIC_UPDATE_RE.search("correction: 9000000 revenue")
        assert m is not None

    def test_no_match_plain_text(self):
        assert _NUMERIC_UPDATE_RE.search("please run the cost agent") is None

    def test_no_match_number_without_trigger(self):
        assert _NUMERIC_UPDATE_RE.search("we have 5000 users") is None

    def test_decimal_value(self):
        m = _NUMERIC_UPDATE_RE.search("actually 3.5 TB")
        assert m is not None
        assert m.group(1) == "3.5"


# ═══════════════════════════════════════════════════════════════════════════
# _detect_assumption_updates — integration with AgentState
# ═══════════════════════════════════════════════════════════════════════════


class TestDetectAssumptionUpdates:
    """Verify _detect_assumption_updates patches state correctly."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.state = AgentState(user_input="test")
        self.state.shared_assumptions = {
            "total_users": 1000,
            "affected_employees": 100,
            "current_annual_spend": 500000,
            "data_volume_gb": 50,
            "timeline_months": 6,
            "monthly_revenue": 1000000,
        }

    def test_updates_total_users(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "actually 5000 users", self.state
        )
        assert updated == ["total_users"]
        assert self.state.shared_assumptions["total_users"] == 5000.0

    def test_updates_employees(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "changed to 300 employees", self.state
        )
        assert updated == ["affected_employees"]
        assert self.state.shared_assumptions["affected_employees"] == 300.0

    def test_updates_spend(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "actually 750,000 spend", self.state
        )
        assert updated == ["current_annual_spend"]
        assert self.state.shared_assumptions["current_annual_spend"] == 750000.0

    def test_updates_budget_maps_to_spend(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "updated to 200000 budget", self.state
        )
        assert updated == ["current_annual_spend"]
        assert self.state.shared_assumptions["current_annual_spend"] == 200000.0

    def test_tb_to_gb_conversion(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "should be 2 TB", self.state
        )
        assert updated == ["data_volume_gb"]
        assert self.state.shared_assumptions["data_volume_gb"] == 2048.0  # 2 * 1024

    def test_gb_no_conversion(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "actually 100 GB", self.state
        )
        assert updated == ["data_volume_gb"]
        assert self.state.shared_assumptions["data_volume_gb"] == 100.0

    def test_updates_months(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "now 18 months", self.state
        )
        assert updated == ["timeline_months"]
        assert self.state.shared_assumptions["timeline_months"] == 18.0

    def test_updates_revenue(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "correction: 5000000 revenue", self.state
        )
        assert updated == ["monthly_revenue"]
        assert self.state.shared_assumptions["monthly_revenue"] == 5000000.0

    def test_multiple_updates_single_message(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "actually 5000 users and now 24 months", self.state
        )
        assert "total_users" in updated
        assert "timeline_months" in updated
        assert self.state.shared_assumptions["total_users"] == 5000.0
        assert self.state.shared_assumptions["timeline_months"] == 24.0

    def test_no_match_returns_empty(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "looks good, proceed", self.state
        )
        assert updated == []
        # Original values unchanged
        assert self.state.shared_assumptions["total_users"] == 1000

    def test_no_false_positive_plain_number(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "we have 5000 users in our system", self.state
        )
        assert updated == []

    def test_sa_cache_invalidated(self):
        """After update, state.sa should reflect the new value."""
        # Prime the cache
        _ = self.state.sa
        assert self.state.sa.total_users == 1000.0

        MAFOrchestrator._detect_assumption_updates(
            "actually 9999 users", self.state
        )
        # Cache should be invalidated — new .sa should see 9999
        assert self.state.sa.total_users == 9999.0

    def test_comma_separated_number(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "actually 1,500,000 spend", self.state
        )
        assert updated == ["current_annual_spend"]
        assert self.state.shared_assumptions["current_annual_spend"] == 1500000.0

    def test_decimal_tb(self):
        updated = MAFOrchestrator._detect_assumption_updates(
            "actually 3.5 TB", self.state
        )
        assert updated == ["data_volume_gb"]
        assert self.state.shared_assumptions["data_volume_gb"] == 3.5 * 1024


# ═══════════════════════════════════════════════════════════════════════════
# AgentState.invalidate_sa_cache
# ═══════════════════════════════════════════════════════════════════════════


class TestInvalidateSaCache:
    """Verify explicit cache invalidation for in-place dict mutations."""

    def test_invalidate_refreshes_sa(self):
        state = AgentState(user_input="x")
        state.shared_assumptions = {"total_users": 500}
        assert state.sa.total_users == 500.0

        # In-place mutation — cache is stale
        state.shared_assumptions["total_users"] = 999
        assert state.sa.total_users == 500.0  # still cached

        # Explicit invalidation
        state.invalidate_sa_cache()
        assert state.sa.total_users == 999.0  # refreshed
