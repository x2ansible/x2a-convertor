from pathlib import Path

import pytest
from jinja2 import StrictUndefined

from prompts.get_prompt import jinja_env
from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.types import AAPDiscoveryResult, AnsibleModule, DocumentFile


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
