from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.exporters.agent_state import WriteAgentState
from src.exporters.state import ExportState
from src.exporters.types import MigrationCategory
from src.exporters.write_agent import WriteAgent
from src.types import AnsibleModule, Checklist, ChecklistStatus, DocumentFile


class TestWriteCompletion:
    @pytest.fixture
    def state(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        plan = DocumentFile(path=Path("plan.md"), content="Migration plan")
        export_state = ExportState(
            user_message="migrate this",
            path="source",
            module=AnsibleModule("sample"),
            module_migration_plan=plan,
            high_level_migration_plan=plan,
            directory_listing=[],
            current_phase="writing",
            write_attempt_counter=0,
            validation_attempt_counter=0,
            validation_report="",
            last_output="",
            checklist=Checklist("sample", MigrationCategory),
        )
        target = export_state.role_path / "tasks" / "main.yml"
        target.parent.mkdir(parents=True)
        target.write_text("- name: Creator placeholder\n  ansible.builtin.debug: {}\n")
        assert export_state.checklist is not None
        export_state.checklist.add_task("recipes", "source.rb", str(target))
        return WriteAgentState(export_state=export_state, max_attempts=2)

    @pytest.fixture
    def agent(self):
        agent = object.__new__(WriteAgent)
        agent._log = MagicMock()
        agent._graph = MagicMock()
        agent.max_attempts = 2
        return agent

    def test_pending_scaffold_does_not_finish_the_write_loop(self, agent, state):
        result = agent._check_files_node(state)

        assert not result.complete
        assert result.missing_files == []
        assert agent._evaluate_write_node(result) == "write_files"

    def test_completed_conversion_finishes_the_write_loop(self, agent, state):
        state.export_state.checklist.items[0].status = ChecklistStatus.COMPLETE

        result = agent._check_files_node(state)

        assert result.complete
        assert agent._evaluate_write_node(result) == "__end__"

    def test_pending_molecule_does_not_prevent_writer_completion(self, agent, state):
        checklist = state.export_state.checklist
        checklist.items[0].status = ChecklistStatus.COMPLETE
        checklist.add_task("molecule", "N/A", "molecule/verify.yml")

        result = agent._check_files_node(state)

        assert result.complete

    def test_completed_files_skip_the_write_graph(self, agent, state):
        state.export_state.checklist.items[0].status = ChecklistStatus.COMPLETE

        agent.execute(state.export_state, None)

        agent._graph.invoke.assert_not_called()

    def test_retry_exhaustion_reports_unconverted_scaffold(self, agent, state):
        state.attempt = state.max_attempts
        state = agent._check_files_node(state)
        assert agent._evaluate_write_node(state) == "mark_failed"

        result = agent._mark_failed_node(state)

        assert result.export_state.failed
        assert "Failed to complete 1 files" in result.export_state.failure_reason
        assert (
            str(state.export_state.role_path / "tasks" / "main.yml")
            in result.export_state.failure_reason
        )
