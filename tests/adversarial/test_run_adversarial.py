"""Tests for the run_adversarial entry point and _write_summary."""

import json
from unittest.mock import Mock

import pytest

from src.adversarial import _write_summary
from src.adversarial.adversarial_agent import AdversarialAgent
from src.adversarial.findings_reporter import AdversarialFinding, AdversarialReport
from src.const import ADVERSARIAL_REPORT_FILENAME


@pytest.fixture
def mock_model():
    return Mock()


def _make_agent(
    name: str, mock_model, report: AdversarialReport | None = None
) -> AdversarialAgent:
    agent = AdversarialAgent(
        name=name, prompt="p", phases=["analyze"], model=mock_model
    )
    agent._report = report
    return agent


class TestWriteSummary:
    def test_writes_json_file(self, tmp_path, monkeypatch, mock_model):
        monkeypatch.chdir(tmp_path)
        agents = [
            _make_agent(
                "agent-a", mock_model, AdversarialReport(findings=[], summary="clean")
            )
        ]
        _write_summary("analyze", agents)
        assert (tmp_path / ADVERSARIAL_REPORT_FILENAME).exists()

    def test_summary_contains_phase(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_summary("analyze", [])
        data = json.loads((tmp_path / ADVERSARIAL_REPORT_FILENAME).read_text())
        assert data["phase"] == "analyze"

    def test_summary_counts_agents_run(self, tmp_path, monkeypatch, mock_model):
        monkeypatch.chdir(tmp_path)
        agents = [
            _make_agent("a", mock_model, AdversarialReport(findings=[], summary="")),
            _make_agent("b", mock_model, AdversarialReport(findings=[], summary="")),
        ]
        _write_summary("analyze", agents)
        data = json.loads((tmp_path / ADVERSARIAL_REPORT_FILENAME).read_text())
        assert data["agents_run"] == 2

    def test_summary_skips_agents_with_no_report(
        self, tmp_path, monkeypatch, mock_model
    ):
        monkeypatch.chdir(tmp_path)
        agents = [
            _make_agent("a", mock_model, AdversarialReport(findings=[], summary="")),
            _make_agent("b", mock_model, None),
        ]
        _write_summary("analyze", agents)
        data = json.loads((tmp_path / ADVERSARIAL_REPORT_FILENAME).read_text())
        assert data["agents_run"] == 1
        assert data["agents"][0]["name"] == "a"

    def test_summary_totals_findings(self, tmp_path, monkeypatch, mock_model):
        monkeypatch.chdir(tmp_path)
        finding = AdversarialFinding(
            severity="CRITICAL", location="f", description="d", evidence="e"
        )
        agents = [
            _make_agent(
                "a",
                mock_model,
                AdversarialReport(findings=[finding, finding], summary=""),
            ),
            _make_agent(
                "b", mock_model, AdversarialReport(findings=[finding], summary="")
            ),
        ]
        _write_summary("analyze", agents)
        data = json.loads((tmp_path / ADVERSARIAL_REPORT_FILENAME).read_text())
        assert data["total_findings"] == 3
        assert data["total_critical_findings"] == 3

    def test_summary_per_agent_entry(self, tmp_path, monkeypatch, mock_model):
        monkeypatch.chdir(tmp_path)
        finding = AdversarialFinding(
            severity="WARNING", location="f", description="d", evidence="e"
        )
        agents = [
            _make_agent(
                "my-agent",
                mock_model,
                AdversarialReport(findings=[finding], summary="one warning"),
            ),
        ]
        _write_summary("analyze", agents)
        data = json.loads((tmp_path / ADVERSARIAL_REPORT_FILENAME).read_text())
        entry = data["agents"][0]
        assert entry["name"] == "my-agent"
        assert entry["findings"] == 1
        assert entry["critical_findings"] == 0
        assert entry["summary"] == "one warning"

    def test_no_agents_produces_zero_totals(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_summary("migrate", [])
        data = json.loads((tmp_path / ADVERSARIAL_REPORT_FILENAME).read_text())
        assert data["total_findings"] == 0
        assert data["total_critical_findings"] == 0
        assert data["agents"] == []
