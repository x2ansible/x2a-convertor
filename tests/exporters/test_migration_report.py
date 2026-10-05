"""Tests for migration report rendering."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.exporters.migration_report import MigrationReport
from src.exporters.state import ExportState
from src.exporters.types import MigrationCategory, MoleculeStatus
from src.types import AnsibleModule, Checklist, DocumentFile


@pytest.fixture
def base_state(tmp_path: Path) -> ExportState:
    checklist = Checklist("test_module", MigrationCategory)
    checklist.add_task(
        category=MigrationCategory.RECIPES,
        source_path="recipes/default.rb",
        target_path="tasks/main.yml",
        status="complete",
    )
    checklist.add_task(
        category=MigrationCategory.TEMPLATES,
        source_path="templates/config.erb",
        target_path="templates/config.j2",
        status="pending",
    )
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


def test_success_report_includes_stats_validation_and_checklist(base_state):
    report = MigrationReport.from_state(base_state).render()

    assert "# Migration Summary for test_module" in report
    assert "**Total items:** 2" in report
    assert "**Completed:** 1" in report
    assert "**Pending:** 1" in report
    assert "**Write attempts:** 2" in report
    assert "**Validation attempts:** 1" in report
    assert "## Final Validation Report" in report
    assert "All checks passed" in report
    assert "## Checklist: test_module" in report
    assert "tasks/main.yml" in report


def test_failure_report_includes_failure_details_and_partial_sections(base_state):
    state = base_state.mark_failed("Lint errors").update(validation_report="")

    report = MigrationReport.from_state(state).render()

    assert "# MIGRATION FAILED for test_module" in report
    assert "**Failure Reason:** Lint errors" in report
    assert "## Migration Summary" in report
    assert "## Partial Validation Report" in report
    assert "_Not run_" in report
    assert "### Partial Checklist" in report


def test_report_includes_review_and_molecule_status(base_state):
    state = base_state.update(
        review_report="Found 2 issues, fixed 2",
        molecule_status=MoleculeStatus.NOT_EXECUTED,
        molecule_report="Developer/CI execution is required.",
    )

    report = state.report_status()

    assert "### Review Report" in report
    assert "Found 2 issues, fixed 2" in report
    assert "**Status:** statically_validated_not_executed" in report
    assert "Developer/CI execution is required." in report


def test_report_omits_default_molecule_status(base_state):
    report = base_state.report_status()

    assert "Molecule Test Generation" not in report


def test_report_includes_telemetry_when_present(base_state):
    telemetry = MagicMock()
    telemetry.to_summary.return_value = "Duration: 42s"

    report = base_state.update(telemetry=telemetry).report_status()

    assert "## Telemetry" in report
    assert "Duration: 42s" in report


def test_report_requires_initialized_checklist(base_state):
    with pytest.raises(AssertionError, match="Checklist must be initialized"):
        base_state.update(checklist=None).report_status()


def test_empty_checklist_is_reported(base_state):
    state = base_state.update(checklist=Checklist("test_module", MigrationCategory))

    report = MigrationReport.from_state(state).render()

    assert "**Total items:** 0" in report
    assert "**Completed:** 0" in report
