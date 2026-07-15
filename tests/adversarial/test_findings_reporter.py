"""Tests for findings_reporter formatting and file output functions."""

import pytest

from src.adversarial.findings_reporter import (
    AdversarialFinding,
    AdversarialReport,
    append_to_report,
    format_markdown,
    has_findings,
)


@pytest.fixture
def finding():
    return AdversarialFinding(
        severity="CRITICAL",
        location="roles/nginx/tasks/main.yml",
        description="Privilege escalation without become_user",
        evidence="- name: restart nginx\n  shell: systemctl restart nginx",
    )


@pytest.fixture
def report_with_findings(finding):
    return AdversarialReport(findings=[finding], summary="One critical issue found")


@pytest.fixture
def empty_report():
    return AdversarialReport(findings=[], summary="All clear")


class TestFindingsReporter:
    def test_has_findings_returns_true_when_present(self, finding):
        assert has_findings([finding]) is True

    def test_has_findings_returns_false_for_empty_list(self):
        assert has_findings([]) is False

    def test_format_includes_agent_name(self, report_with_findings):
        output = format_markdown("my-agent", report_with_findings)
        assert "my-agent" in output

    def test_format_includes_summary(self, report_with_findings):
        output = format_markdown("agent", report_with_findings)
        assert "One critical issue found" in output

    def test_format_includes_severity_in_heading(self, report_with_findings):
        output = format_markdown("agent", report_with_findings)
        assert "[CRITICAL]" in output

    def test_format_includes_location_in_heading(self, report_with_findings):
        output = format_markdown("agent", report_with_findings)
        assert "roles/nginx/tasks/main.yml" in output

    def test_format_includes_description(self, report_with_findings):
        output = format_markdown("agent", report_with_findings)
        assert "Privilege escalation without become_user" in output

    def test_format_includes_evidence_in_code_fence(self, report_with_findings):
        output = format_markdown("agent", report_with_findings)
        assert "```" in output
        assert "systemctl restart nginx" in output

    def test_format_no_findings_outputs_clean_message(self, empty_report):
        output = format_markdown("agent", empty_report)
        assert "No findings detected" in output
        assert "[CRITICAL]" not in output
        assert "[WARNING]" not in output

    def test_format_warning_severity_rendered(self):
        report = AdversarialReport(
            findings=[
                AdversarialFinding(
                    severity="WARNING",
                    location="site.yml",
                    description="Deprecated module",
                    evidence="- include:",
                )
            ]
        )
        output = format_markdown("agent", report)
        assert "[WARNING]" in output

    def test_format_includes_horizontal_rule_at_end(self, report_with_findings):
        output = format_markdown("agent", report_with_findings)
        assert "---" in output

    def test_append_creates_file_when_missing(self, tmp_path, report_with_findings):
        report_path = tmp_path / "findings.md"
        append_to_report(report_path, "agent", report_with_findings)
        assert report_path.exists()

    def test_append_to_existing_file_preserves_content(
        self, tmp_path, report_with_findings
    ):
        report_path = tmp_path / "findings.md"
        report_path.write_text("# Existing content\n")
        append_to_report(report_path, "agent", report_with_findings)
        content = report_path.read_text()
        assert "# Existing content" in content
        assert "agent" in content

    def test_multiple_appends_accumulate(self, tmp_path):
        report_path = tmp_path / "findings.md"
        report1 = AdversarialReport(findings=[], summary="First agent")
        report2 = AdversarialReport(findings=[], summary="Second agent")
        append_to_report(report_path, "agent-1", report1)
        append_to_report(report_path, "agent-2", report2)
        content = report_path.read_text()
        assert "agent-1" in content
        assert "agent-2" in content
        assert "First agent" in content
        assert "Second agent" in content
