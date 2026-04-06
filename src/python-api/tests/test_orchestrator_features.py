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

    def test_no_mention(self):
        agent, cleaned = self.orch._parse_agent_mention("just a normal message")
        assert agent is None
        assert cleaned == "just a normal message"


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

    def test_no_match_regular_text(self):
        from maf_orchestrator import _CHAT_WITH_RE
        match = _CHAT_WITH_RE.search("I want to discuss the architecture")
        assert match is None
