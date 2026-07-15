"""Tests for AdversarialAgent construction and properties."""

from unittest.mock import Mock

import pytest

from src.adversarial.adversarial_agent import AdversarialAgent
from src.adversarial.findings_reporter import AdversarialReport
from src.types.base_state import BaseState


@pytest.fixture
def mock_model():
    return Mock()


@pytest.fixture
def agent(mock_model):
    return AdversarialAgent(
        name="test-agent",
        prompt="Check for security issues",
        phases=["analyze"],
        critical=False,
        model=mock_model,
    )


class TestAdversarialAgent:
    def test_constructs_from_full_dict(self, mock_model):
        data = {
            "name": "privilege-gate",
            "prompt": "Find privilege escalation",
            "phases": ["migrate"],
            "critical": True,
        }
        agent = AdversarialAgent.from_dict(data, model=mock_model)
        assert agent.agent_name == "privilege-gate"
        assert agent.prompt == "Find privilege escalation"
        assert agent.phases == ["migrate"]
        assert agent.critical is True

    def test_critical_defaults_to_false(self, mock_model):
        data = {"name": "agent", "prompt": "Check something", "phases": ["analyze"]}
        agent = AdversarialAgent.from_dict(data, model=mock_model)
        assert agent.critical is False

    def test_multiple_phases(self, mock_model):
        data = {
            "name": "multi-phase-agent",
            "prompt": "Check both phases",
            "phases": ["analyze", "migrate"],
        }
        agent = AdversarialAgent.from_dict(data, model=mock_model)
        assert "analyze" in agent.phases
        assert "migrate" in agent.phases

    def test_returns_name_passed_to_constructor(self, agent):
        assert agent.agent_name == "test-agent"

    def test_distinct_agents_have_distinct_names(self, mock_model):
        a1 = AdversarialAgent(
            name="agent-one", prompt="p", phases=["analyze"], model=mock_model
        )
        a2 = AdversarialAgent(
            name="agent-two", prompt="p", phases=["analyze"], model=mock_model
        )
        assert a1.agent_name == "agent-one"
        assert a2.agent_name == "agent-two"

    def test_report_is_none_before_execute(self, agent):
        assert agent.report is None

    def test_report_set_after_execute(self, agent, monkeypatch):
        stub_report = AdversarialReport(findings=[], summary="done")
        monkeypatch.setattr(
            agent, "_collect_evidence", lambda state, metrics: "evidence"
        )
        monkeypatch.setattr(
            agent, "_extract_findings", lambda content, metrics: stub_report
        )
        state = BaseState(user_message="", path="/tmp")
        agent.execute(state, None)
        assert agent.report is stub_report
