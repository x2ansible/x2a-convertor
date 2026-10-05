from pathlib import Path
from unittest.mock import MagicMock

from src.exporters.molecule_agent import MoleculeAgent
from src.exporters.services.molecule_project import MoleculeProject
from src.exporters.state import ExportState
from src.exporters.to_ansible import MigrationPhase, ToAnsibleSubagent
from src.exporters.types import MigrationCategory, MoleculeStatus
from src.types import AnsibleModule, Checklist, DocumentFile


def create_state(tmp_path: Path) -> ExportState:
    return ExportState(
        user_message="migrate module",
        path=str(tmp_path / "source"),
        module=AnsibleModule("web_server"),
        module_migration_plan=DocumentFile(
            path=Path("plan.md"),
            content=(
                "# Plan\n\nSummary context is available.\n\n"
                "## Pre-flight checks\n\n```bash\nsystemctl is-active nginx\n```\n\n"
                "## Other checks\nOther plan detail must not add a test."
            ),
        ),
        high_level_migration_plan=DocumentFile(
            path=Path("high-level.md"), content="# High-level plan"
        ),
        directory_listing=[],
        current_phase="writing",
        write_attempt_counter=0,
        validation_attempt_counter=0,
        validation_report="",
        last_output="",
        checklist=Checklist("web_server", MigrationCategory),
    )


def create_agent() -> MoleculeAgent:
    agent = object.__new__(MoleculeAgent)
    agent._log = MagicMock()
    return agent


def initialize_state(state: ExportState) -> ExportState:
    orchestrator = object.__new__(ToAnsibleSubagent)
    return orchestrator._initialize(state)


def write_valid_verification(agent):
    captured_messages: list[list[dict[str, str]]] = []

    def invoke_react(state, messages, metrics):
        captured_messages.append(messages)
        verify = state.molecule_verify_path
        verify.write_text(
            "---\n- hosts: all\n  tasks:\n"
            "    - name: Assert service state\n"
            "      ansible.builtin.assert:\n"
            "        that: ansible_facts['services']['httpd.service']['state'] == 'running'\n"
        )
        return {"messages": []}

    agent.invoke_react = invoke_react
    return captured_messages


def test_generation_marks_files_static_only_not_executed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    agent = create_agent()
    captured_messages = write_valid_verification(agent)
    state = initialize_state(create_state(tmp_path))
    metrics = MagicMock()

    result = agent.execute(state, metrics)

    assert result.molecule_status == MoleculeStatus.NOT_EXECUTED
    assert "not run by the converter" in result.molecule_report
    system_prompt = captured_messages[0][0]["content"]
    task_prompt = captured_messages[0][1]["content"]
    assert "Summary context is available" in task_prompt
    assert "Other plan detail must not add a test" in task_prompt
    assert "Do not derive checks from other sections" in task_prompt
    assert "systemctl is-active nginx" in task_prompt
    assert "only source of verification expectations" in system_prompt
    assert (
        "Write only the `verify.yml` file at the path provided in the task."
        in system_prompt
    )
    assert "Write only ``." not in system_prompt
    assert "no Molecule driver plugin is used" in system_prompt
    assert "scenario's Ansible inventory" in system_prompt
    assert str(state.molecule_verify_path) in task_prompt
    assert "Final role task files" not in task_prompt
    assert result.checklist is not None
    assert all(
        item.status.value == "complete"
        for item in result.checklist.items_by_category(include={"molecule"})
    )
    metrics.record_metric.assert_any_call("molecule_static_validation", True)


def test_generation_failure_is_reported_and_verify_remains_incomplete(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    agent = create_agent()
    agent.invoke_react = MagicMock(return_value={"messages": []})
    state = initialize_state(create_state(tmp_path))

    result = agent.execute(state, None)

    verify_path = str(state.molecule_verify_path)
    assert result.checklist is not None
    verify_item = result.checklist.find_task("N/A", verify_path)
    assert verify_item is not None
    assert result.molecule_status == MoleculeStatus.GENERATION_FAILED
    assert verify_item.status.value == "error"
    assert "verify.yml" in result.molecule_report
    assert agent.invoke_react.call_count == agent.MAX_GENERATION_ATTEMPTS


def test_empty_supported_expectation_set_can_be_statically_validated(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    agent = create_agent()
    state = initialize_state(create_state(tmp_path))

    def write_empty_verification(state, messages, metrics):
        state.molecule_verify_path.write_text(
            "---\n- name: No supported pre-flight checks\n  hosts: all\n  tasks: []\n"
        )
        return {"messages": []}

    agent.invoke_react = MagicMock(side_effect=write_empty_verification)
    result = agent.execute(state, None)

    assert result.molecule_status == MoleculeStatus.NOT_EXECUTED
    assert result.checklist is not None
    assert all(
        item.status.value == "complete"
        for item in result.checklist.items_by_category(include={"molecule"})
    )


def test_initialize_is_the_single_owner_of_molecule_checklist_seeding(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    orchestrator = object.__new__(ToAnsibleSubagent)
    state = create_state(tmp_path)

    initialized = orchestrator._initialize(state)

    assert initialized.checklist is not None
    molecule_items = initialized.checklist.items_by_category(include={"molecule"})
    assert len(molecule_items) == 10
    assert all(item.source_path == "N/A" for item in molecule_items)


class TestExistingScaffold:
    def test_legacy_driver_is_reported_without_llm_retries_or_overwrites(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        state = initialize_state(create_state(tmp_path))
        MoleculeProject(state.layout).scaffold()
        config = state.layout.molecule_scenario_path / "molecule.yml"
        legacy = "driver:\n  name: podman\n"
        config.write_text(legacy)
        agent = create_agent()
        agent.invoke_react = MagicMock()

        result = agent.execute(state, None)

        assert result.molecule_status == MoleculeStatus.GENERATION_FAILED
        assert "driver plugin" in result.molecule_report
        assert config.read_text() == legacy
        agent.invoke_react.assert_not_called()
        assert result.checklist is not None
        assert all(
            item.status.value != "complete"
            for item in result.checklist.items_by_category(include={"molecule"})
        )


def test_scaffold_uses_the_named_project_factory_dependency():
    orchestrator = object.__new__(ToAnsibleSubagent)
    orchestrator._ansible_project_factory = MagicMock()
    project = MagicMock()
    project.create_role.return_value = Path("ansible/role")
    orchestrator._ansible_project_factory.return_value = project
    state = create_state(Path())

    result = orchestrator._scaffold_project(state)

    orchestrator._ansible_project_factory.assert_called_once_with(Path("ansible"))
    project.create_role.assert_called_once_with("web_server")
    assert result.current_phase == MigrationPhase.SCAFFOLDING


def test_workflow_generates_molecule_after_review():
    orchestrator = object.__new__(ToAnsibleSubagent)
    state = create_state(Path())

    state = state.update(current_phase=MigrationPhase.WRITING)
    assert orchestrator._check_failure_after_agent(state) == "review_role"
    state = state.update(current_phase=MigrationPhase.REVIEWING)
    assert orchestrator._check_failure_after_agent(state) == "molecule_testing"
    state = state.update(current_phase=MigrationPhase.MOLECULE_TESTING)
    assert orchestrator._check_failure_after_agent(state) == "validate_migration"
