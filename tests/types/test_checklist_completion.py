import pytest

from src.exporters.types import MigrationCategory
from src.types import Checklist, ChecklistStatus


class TestChecklistCompletion:
    @pytest.mark.parametrize("status", list(ChecklistStatus))
    @pytest.mark.parametrize("exists", [True, False])
    def test_requires_completed_status_and_existing_target(
        self, tmp_path, status, exists
    ):
        target = tmp_path / "main.yml"
        if exists:
            target.write_text("---\n")
        checklist = Checklist("sample", MigrationCategory)
        checklist.add_task("recipes", "source.rb", str(target), status=status)

        expected = (
            [] if exists and status == ChecklistStatus.COMPLETE else [str(target)]
        )
        assert checklist.incomplete_targets() == expected

    def test_excludes_other_agents_targets(self, tmp_path):
        target = tmp_path / "verify.yml"
        checklist = Checklist("sample", MigrationCategory)
        checklist.add_task("molecule", "N/A", str(target))

        assert checklist.incomplete_targets(exclude={"molecule"}) == []
        assert checklist.incomplete_targets() == [str(target)]
