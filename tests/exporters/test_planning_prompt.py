from pathlib import Path
from unittest.mock import MagicMock

import pytest
from jinja2 import StrictUndefined

from prompts.get_prompt import jinja_env
from src.exporters.planning_agent import PlanningAgent
from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.state import ExportState
from src.exporters.types import MigrationCategory
from src.types import AAPDiscoveryResult, AnsibleModule, Checklist, DocumentFile
from src.types.technology import Technology


class TestPlanningPrompt:
    @pytest.mark.parametrize("existing_checklist", ["", "Existing migration tasks"])
    @pytest.mark.parametrize(
        "discovery",
        [None, AAPDiscoveryResult.disabled(), AAPDiscoveryResult.success("acme.web")],
    )
    def test_paths_come_from_the_layout(self, discovery, existing_checklist):
        layout = AnsibleProjectLayout.from_module(
            AnsibleModule("web_server"),
            project_path="custom_project",
            namespace="acme",
            project_name="infra",
        )
        plan = DocumentFile(path=Path("plan.md"), content="Migration plan")
        template = jinja_env.overlay(undefined=StrictUndefined).get_template(
            "export_ansible_planning_task.j2"
        )

        prompt = template.render(
            module=layout.module,
            layout=layout,
            high_level_migration_plan=plan,
            module_migration_plan=plan.to_document(),
            path="source",
            existing_checklist=existing_checklist,
            aap_discovery=discovery,
        )

        assert str(layout.role_path) in prompt
        assert str(layout.run_playbook_path) in prompt
        assert all(target in prompt for target in layout.molecule_checklist_targets())
        assert "x2a/project" not in prompt
        assert "ansible/molecule" not in prompt
        assert plan.to_document() in prompt
        if discovery and discovery.enabled:
            assert discovery.content in prompt
            assert f'target_path="{layout.role_path}/requirements.yml"' in prompt

    @pytest.mark.parametrize("technology", list(Technology))
    def test_planner_includes_rules_for_the_source_technology(
        self, technology, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        plan = DocumentFile(path=Path("plan.md"), content="Migration plan")
        state = ExportState(
            user_message="migrate",
            path="source",
            module=AnsibleModule("sample"),
            module_migration_plan=plan,
            high_level_migration_plan=plan,
            directory_listing=[],
            current_phase="planning",
            write_attempt_counter=0,
            validation_attempt_counter=0,
            validation_report="",
            last_output="",
            checklist=Checklist("sample", MigrationCategory),
            source_technology=technology,
        )
        state.checklist_path.parent.mkdir(parents=True)
        agent = object.__new__(PlanningAgent)
        agent._log = MagicMock()
        agent.invoke_react = MagicMock()

        agent.execute(state, None)

        messages = agent.invoke_react.call_args.args[1]
        system_prompt = messages[0]["content"]
        assert ("Chef-to-Ansible Planning Rules" in system_prompt) == (
            technology is Technology.CHEF
        )
        assert ("force_default" in system_prompt) == (technology is Technology.CHEF)
        assert ("data bags" in system_prompt) == (technology is Technology.CHEF)
