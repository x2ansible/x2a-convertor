"""Tests for AdversarialAgentManager loading and phase execution."""

import json
from unittest.mock import Mock

import pytest

from src.adversarial.adversarial_agent_manager import AdversarialAgentManager
from src.adversarial.findings_reporter import AdversarialFinding, AdversarialReport
from src.types.base_state import BaseState


@pytest.fixture
def mock_model():
    return Mock()


@pytest.fixture
def state():
    return BaseState(user_message="", path="/tmp")


@pytest.fixture
def agents_config():
    return [
        {
            "name": "checklist-auditor",
            "prompt": "Check completeness",
            "phases": ["analyze"],
        },
        {
            "name": "privilege-gate",
            "prompt": "Check privileges",
            "phases": ["migrate"],
            "critical": True,
        },
        {
            "name": "multi-phase",
            "prompt": "Check both",
            "phases": ["analyze", "migrate"],
        },
    ]


@pytest.fixture
def config_file(tmp_path, agents_config):
    path = tmp_path / "agents.json"
    path.write_text(json.dumps(agents_config))
    return path


class TestAdversarialAgentManager:
    def test_loads_agents_for_matching_phase(self, config_file, mock_model):
        manager = AdversarialAgentManager(
            phase="analyze", config_path=str(config_file), model=mock_model
        )
        names = [a.agent_name for a in manager.agents]
        assert "checklist-auditor" in names
        assert "multi-phase" in names
        assert "privilege-gate" not in names

    def test_loads_agents_for_migrate_phase(self, config_file, mock_model):
        manager = AdversarialAgentManager(
            phase="migrate", config_path=str(config_file), model=mock_model
        )
        names = [a.agent_name for a in manager.agents]
        assert "privilege-gate" in names
        assert "multi-phase" in names
        assert "checklist-auditor" not in names

    def test_returns_empty_list_when_no_config(self, mock_model):
        manager = AdversarialAgentManager(
            phase="analyze", config_path=None, model=mock_model
        )
        assert manager.agents == []

    def test_returns_empty_list_when_file_missing(self, tmp_path, mock_model):
        manager = AdversarialAgentManager(
            phase="analyze",
            config_path=str(tmp_path / "nonexistent.json"),
            model=mock_model,
        )
        assert manager.agents == []

    def test_returns_empty_list_when_no_phase_match(self, config_file, mock_model):
        config = [{"name": "a", "prompt": "p", "phases": ["migrate"]}]
        config_file.write_text(json.dumps(config))
        manager = AdversarialAgentManager(
            phase="analyze", config_path=str(config_file), model=mock_model
        )
        assert manager.agents == []

    def test_run_phase_returns_empty_when_no_agents(self, state, mock_model):
        manager = AdversarialAgentManager(
            phase="analyze", config_path=None, model=mock_model
        )
        assert manager.run_phase(state=state) == []

    def test_run_phase_returns_reports_from_agents(
        self, config_file, state, mock_model, monkeypatch
    ):
        stub_report = AdversarialReport(
            findings=[
                AdversarialFinding(
                    severity="WARNING",
                    location="main.yml",
                    description="issue",
                    evidence="evidence",
                )
            ],
            summary="done",
        )
        manager = AdversarialAgentManager(
            phase="analyze", config_path=str(config_file), model=mock_model
        )
        for agent in manager.agents:
            agent._report = stub_report
            monkeypatch.setattr(agent, "execute", lambda s, m, a=agent: a._report and s)

        reports = manager.run_phase(state=state)
        assert len(reports) == 2  # checklist-auditor + multi-phase
        assert all(r.summary == "done" for r in reports)

    def test_run_phase_appends_to_report_file(
        self, config_file, state, mock_model, monkeypatch, tmp_path
    ):
        stub_report = AdversarialReport(findings=[], summary="clean")
        manager = AdversarialAgentManager(
            phase="analyze", config_path=str(config_file), model=mock_model
        )
        for agent in manager.agents:
            agent._report = stub_report
            monkeypatch.setattr(agent, "execute", lambda s, m, a=agent: a._report and s)

        report_path = tmp_path / "report.md"
        manager.run_phase(state=state, report_path=report_path)

        assert report_path.exists()
        content = report_path.read_text()
        assert "checklist-auditor" in content or "multi-phase" in content

    def test_run_phase_does_not_write_without_report_path(
        self, config_file, state, mock_model, monkeypatch, tmp_path
    ):
        stub_report = AdversarialReport(findings=[], summary="clean")
        manager = AdversarialAgentManager(
            phase="analyze", config_path=str(config_file), model=mock_model
        )
        for agent in manager.agents:
            agent._report = stub_report
            monkeypatch.setattr(agent, "execute", lambda s, m, a=agent: a._report and s)

        manager.run_phase(state=state, report_path=None)
        assert not (tmp_path / "report.md").exists()

    def test_run_phase_passes_metrics_via_telemetry_context(
        self, config_file, state, mock_model, monkeypatch
    ):
        from src.types.telemetry import AgentMetrics, Telemetry

        stub_report = AdversarialReport(findings=[], summary="")
        captured_metrics: list[AgentMetrics | None] = []

        manager = AdversarialAgentManager(
            phase="analyze", config_path=str(config_file), model=mock_model
        )
        for agent in manager.agents:
            agent._report = stub_report

            def fake_execute(s, m, a=agent):
                captured_metrics.append(m)
                return s

            monkeypatch.setattr(agent, "execute", fake_execute)

        telemetry = Telemetry(phase="adversarial-analyze")
        manager.run_phase(state=state, telemetry=telemetry)

        assert all(m is not None for m in captured_metrics)
        assert all(isinstance(m, AgentMetrics) for m in captured_metrics)
