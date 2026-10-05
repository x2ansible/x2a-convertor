"""Tests for ExportState's own behavior: layout caching and molecule defaults."""

from pathlib import Path

from src.exporters.state import ExportState
from src.exporters.types import MigrationCategory, MoleculeStatus
from src.types import AnsibleModule, Checklist, DocumentFile


def create_state(tmp_path: Path) -> ExportState:
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
        checklist=Checklist("test_module", MigrationCategory),
    )


def test_layout_is_cached_per_state_instance(tmp_path):
    state = create_state(tmp_path)

    assert state.layout is state.layout


def test_layout_is_derived_from_the_state_module(tmp_path):
    state = create_state(tmp_path)

    assert state.layout.module == state.module


def test_path_properties_delegate_to_the_layout(tmp_path):
    state = create_state(tmp_path)

    assert state.role_path == state.layout.role_path
    assert state.project_path == state.layout.project_path
    assert state.checklist_path == state.layout.checklist_path
    assert state.molecule_verify_path == state.layout.molecule_verify_path
    assert (
        state.molecule_checklist_targets() == state.layout.molecule_checklist_targets()
    )


def test_molecule_status_defaults_to_not_generated(tmp_path):
    assert create_state(tmp_path).molecule_status == MoleculeStatus.NOT_GENERATED


class TestStateTransitions:
    def test_module_update_does_not_reuse_cached_layout(self, tmp_path):
        state = create_state(tmp_path)
        original_layout = state.layout

        updated = state.update(module=AnsibleModule("another_role"))

        assert state.layout is original_layout
        assert updated.layout.module == AnsibleModule("another_role")
        assert updated.layout.role_path.name == "another_role"

    def test_failure_preserves_original_state(self, tmp_path):
        state = create_state(tmp_path)

        failed = state.mark_failed("scaffolding failed")

        assert failed.did_fail()
        assert failed.get_failure_reason() == "scaffolding failed"
        assert not state.did_fail()
