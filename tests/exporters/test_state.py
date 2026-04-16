"""Tests for ExportState report_status and related methods."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.exporters.state import ExportState
from src.exporters.types import MigrationCategory
from src.types import AnsibleModule, Checklist, DocumentFile


class TestExportStateReportStatus:
    """Tests for report_status(), _failure_report(), and _success_report()."""

    @pytest.fixture()
    def checklist(self):
        """Create a Checklist with a few items in mixed statuses."""
        cl = Checklist("test_module", MigrationCategory)
        cl.add_task(
            category=MigrationCategory.RECIPES,
            source_path="recipes/default.rb",
            target_path="tasks/main.yml",
            status="complete",
        )
        cl.add_task(
            category=MigrationCategory.TEMPLATES,
            source_path="templates/config.erb",
            target_path="templates/config.j2",
            status="pending",
        )
        return cl

    @pytest.fixture()
    def base_state(self, tmp_path, checklist):
        """Create a minimal successful ExportState."""
        return ExportState(
            user_message="migrate this",
            path=str(tmp_path),
            module=AnsibleModule("test_module"),
            module_migration_plan=DocumentFile(path=Path("plan.md"), content="# Plan"),
            high_level_migration_plan=DocumentFile(path=Path("hl.md"), content="# HL"),
            directory_listing=["recipes/default.rb"],
            current_phase="complete",
            write_attempt_counter=2,
            validation_attempt_counter=1,
            validation_report="All checks passed",
            last_output="",
            checklist=checklist,
        )

    # -- report_status dispatching --

    def test_success_report_contains_module_name(self, base_state):
        report = base_state.report_status()
        assert "Migration Summary for test_module:" in report

    def test_failure_report_contains_failure_header(self, base_state):
        state = base_state.mark_failed("Lint errors")
        report = state.report_status()
        assert "MIGRATION FAILED for test_module" in report

    def test_report_status_asserts_on_none_checklist(self, base_state):
        state = base_state.update(checklist=None)
        with pytest.raises(AssertionError, match="Checklist must be initialized"):
            state.report_status()

    # -- success report content --

    def test_success_report_includes_stats(self, base_state):
        report = base_state.report_status()
        assert "Total items: 2" in report
        assert "Completed: 1" in report
        assert "Pending: 1" in report

    def test_success_report_includes_attempt_counters(self, base_state):
        report = base_state.report_status()
        assert "Write attempts: 2" in report
        assert "Validation attempts: 1" in report

    def test_success_report_includes_validation_report(self, base_state):
        report = base_state.report_status()
        assert "Final Validation Report:" in report
        assert "All checks passed" in report

    def test_success_report_includes_checklist_markdown(self, base_state):
        report = base_state.report_status()
        assert "Final checklist:" in report
        assert "tasks/main.yml" in report

    def test_success_report_omits_review_when_empty(self, base_state):
        report = base_state.report_status()
        assert "Review Report:" not in report

    def test_success_report_includes_review_when_present(self, base_state):
        state = base_state.update(review_report="Found 2 issues, fixed 2")
        report = state.report_status()
        assert "Review Report:" in report
        assert "Found 2 issues, fixed 2" in report

    # -- failure report content --

    def test_failure_report_includes_reason(self, base_state):
        state = base_state.mark_failed("Max retries exceeded")
        report = state.report_status()
        assert "Failure Reason:" in report
        assert "Max retries exceeded" in report

    def test_failure_report_includes_stats(self, base_state):
        state = base_state.mark_failed("error")
        report = state.report_status()
        assert "Migration Summary:" in report
        assert "Total items: 2" in report

    def test_failure_report_shows_partial_labels(self, base_state):
        state = base_state.mark_failed("error")
        report = state.report_status()
        assert "Partial Validation Report:" in report
        assert "Partial Checklist:" in report

    def test_failure_report_shows_not_run_when_no_validation(self, base_state):
        state = base_state.update(validation_report="").mark_failed("early fail")
        report = state.report_status()
        assert "Not run" in report

    def test_failure_report_includes_review_when_present(self, base_state):
        state = base_state.update(review_report="Some findings").mark_failed("err")
        report = state.report_status()
        assert "Review Report:" in report
        assert "Some findings" in report

    def test_failure_report_omits_review_when_empty(self, base_state):
        state = base_state.mark_failed("err")
        report = state.report_status()
        assert "Review Report:" not in report

    # -- telemetry section --

    def test_report_includes_telemetry_when_present(self, base_state):
        mock_telemetry = MagicMock()
        mock_telemetry.to_summary.return_value = "Duration: 42s"
        state = base_state.update(telemetry=mock_telemetry)

        report = state.report_status()
        assert "Telemetry:" in report
        assert "Duration: 42s" in report

    def test_report_omits_telemetry_when_none(self, base_state):
        report = base_state.report_status()
        assert "Telemetry:" not in report

    def test_failure_report_includes_telemetry(self, base_state):
        mock_telemetry = MagicMock()
        mock_telemetry.to_summary.return_value = "Duration: 10s"
        state = base_state.update(telemetry=mock_telemetry).mark_failed("boom")

        report = state.report_status()
        assert "MIGRATION FAILED" in report
        assert "Telemetry:" in report
        assert "Duration: 10s" in report

    # -- empty checklist edge case --

    def test_success_report_with_empty_checklist(self, base_state):
        empty_cl = Checklist("test_module", MigrationCategory)
        state = base_state.update(checklist=empty_cl)
        report = state.report_status()
        assert "Total items: 0" in report
        assert "Completed: 0" in report
