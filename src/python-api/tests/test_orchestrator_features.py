"""Tests for orchestrator features: @mentions, conversation mode, assumption updates."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAgentMentionParsing:
    """Test @mention regex parsing via MAFOrchestrator._parse_agent_mention."""

    @pytest.fixture(autouse=True)
    def _orch(self):
        from maf_orchestrator import MAFOrchestrator
        self.orch = MAFOrchestrator.__new__(MAFOrchestrator)

    def test_parse_architect_mention(self):
        agent, cleaned = self.orch._parse_agent_mention("@architect add CDN")
        assert agent == "architect"
        assert cleaned == "add CDN"

    def test_parse_cost_mention(self):
        agent, cleaned = self.orch._parse_agent_mention("@cost consider reserved instances")
        assert agent == "cost"
        assert "reserved instances" in cleaned

    def test_parse_bv_alias(self):
        agent, cleaned = self.orch._parse_agent_mention("@bv check value drivers")
        assert agent == "business_value"

    def test_parse_roi_mention(self):
        agent, cleaned = self.orch._parse_agent_mention("@roi check the numbers")
        assert agent == "roi"
        assert "numbers" in cleaned

    def test_parse_presentation_mention(self):
        agent, cleaned = self.orch._parse_agent_mention("@presentation update the slides")
        assert agent == "presentation"

    def test_no_mention(self):
        agent, cleaned = self.orch._parse_agent_mention("just a normal message")
        assert agent is None
        assert cleaned == "just a normal message"

    def test_mention_stripped_from_cleaned(self):
        """The @agent prefix must be removed from the cleaned message."""
        _, cleaned = self.orch._parse_agent_mention("@architect redesign everything")
        assert not cleaned.startswith("@")
        assert "redesign everything" in cleaned


class TestConversationMode:
    """Test conversation mode regex matching."""

    def test_chat_with_architect(self):
        from maf_orchestrator import _CHAT_WITH_RE
        match = _CHAT_WITH_RE.search("chat with architect")
        assert match is not None
        assert match.group(1).lower() == "architect"

    def test_talk_to_cost(self):
        from maf_orchestrator import _CHAT_WITH_RE
        match = _CHAT_WITH_RE.search("talk to cost")
        assert match is not None

    def test_discuss_with_roi(self):
        from maf_orchestrator import _CHAT_WITH_RE
        match = _CHAT_WITH_RE.search("discuss with roi")
        assert match is not None

    def test_no_match_regular_text(self):
        from maf_orchestrator import _CHAT_WITH_RE
        match = _CHAT_WITH_RE.search("I want to discuss the architecture")
        assert match is None


class TestApprovalGateKeywords:
    """Test approval-gate keyword detection (Section 5 of checklist)."""

    @pytest.fixture(autouse=True)
    def _orch(self):
        from maf_orchestrator import MAFOrchestrator
        self.orch = MAFOrchestrator.__new__(MAFOrchestrator)

    # ── Approval keywords ───────────────────────────────────────────────────

    def test_proceed_is_approval(self):
        assert self.orch._is_approval_keyword("proceed") is True

    def test_skip_is_approval(self):
        assert self.orch._is_approval_keyword("skip") is True

    def test_yes_is_approval(self):
        assert self.orch._is_approval_keyword("yes") is True

    def test_ok_is_approval(self):
        assert self.orch._is_approval_keyword("ok") is True

    def test_continue_is_approval(self):
        assert self.orch._is_approval_keyword("continue") is True

    def test_approval_case_insensitive(self):
        assert self.orch._is_approval_keyword("PROCEED") is True
        assert self.orch._is_approval_keyword("Skip") is True

    def test_free_text_not_approval(self):
        assert self.orch._is_approval_keyword("make it cheaper") is False

    # ── Bare refine keywords (Section 5.2: click Refine → ask for feedback) ─

    def test_refine_is_refine_keyword(self):
        assert self.orch._is_refine_keyword("refine") is True

    def test_redo_is_refine_keyword(self):
        assert self.orch._is_refine_keyword("redo") is True

    def test_again_is_refine_keyword(self):
        assert self.orch._is_refine_keyword("again") is True

    def test_retry_is_refine_keyword(self):
        assert self.orch._is_refine_keyword("retry") is True

    def test_refine_case_insensitive(self):
        assert self.orch._is_refine_keyword("REFINE") is True

    def test_refine_with_details_not_bare(self):
        """'refine: focus on cost savings' contains extra text — not a bare keyword."""
        assert self.orch._is_refine_keyword("refine: focus on cost savings") is False

    def test_free_text_not_refine_keyword(self):
        assert self.orch._is_refine_keyword("make it cheaper please") is False

    def test_approval_keyword_with_trailing_text_not_approval(self):
        """'proceed with changes' is free text, not a bare approval keyword."""
        assert self.orch._is_approval_keyword("proceed with changes") is False

    def test_skip_with_trailing_text_not_approval(self):
        assert self.orch._is_approval_keyword("skip this one for now") is False
