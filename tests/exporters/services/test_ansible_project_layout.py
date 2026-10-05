"""Tests for the AnsibleProjectLayout value object."""

from dataclasses import replace
from pathlib import Path

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.types import AnsibleModule


def build_layout(**overrides) -> AnsibleProjectLayout:
    kwargs: dict = {"module": AnsibleModule("test_module")}
    kwargs.update(overrides)
    return AnsibleProjectLayout.from_module(**kwargs)


def test_from_module_derives_every_path_from_defaults():
    layout = build_layout()

    assert layout.project_path == Path("ansible")
    assert layout.role_path == Path(
        "ansible/collections/ansible_collections/x2a/project/roles/test_module"
    )
    assert layout.fqcn == "x2a.project.test_module"
    assert layout.run_playbook_path == Path("ansible/run_test_module.yml")
    assert layout.molecule_scenario_path == Path("ansible/molecule/test_module")
    assert layout.checklist_path == layout.role_path / ".checklist.json"


def test_from_module_honors_custom_project_identity():
    layout = build_layout(
        project_path="custom_root", namespace="acme", project_name="infra"
    )

    assert layout.role_path == Path(
        "custom_root/collections/ansible_collections/acme/infra/roles/test_module"
    )
    assert layout.fqcn == "acme.infra.test_module"


def test_molecule_requirements_and_readme_are_project_level_not_scenario_level():
    layout = build_layout()

    assert layout.molecule_requirements_path == Path(
        "ansible/molecule/requirements.yml"
    )
    assert layout.molecule_readme_path == Path("ansible/molecule/README.md")
    assert layout.molecule_verify_path == Path(
        "ansible/molecule/test_module/verify.yml"
    )


def test_molecule_checklist_targets_exposes_the_ten_generated_artifacts():
    targets = build_layout().molecule_checklist_targets()

    assert len(targets) == 10
    assert set(targets) == {
        "ansible/run_test_module.yml",
        "ansible/molecule/requirements.yml",
        "ansible/molecule/README.md",
        "ansible/molecule/test_module/molecule.yml",
        "ansible/molecule/test_module/inventory/hosts.yml",
        "ansible/molecule/test_module/create.yml",
        "ansible/molecule/test_module/destroy.yml",
        "ansible/molecule/test_module/prepare.yml",
        "ansible/molecule/test_module/converge.yml",
        "ansible/molecule/test_module/verify.yml",
    }
    assert all(isinstance(description, str) for description in targets.values())


class TestLayoutConsistency:
    def test_replacing_identity_recomputes_all_paths(self):
        original = build_layout()
        relocated = replace(original, project_path=Path("elsewhere"), namespace="acme")

        assert relocated.role_path == Path(
            "elsewhere/collections/ansible_collections/acme/project/roles/test_module"
        )
        assert relocated.fqcn == "acme.project.test_module"
        assert relocated.run_playbook_path == Path("elsewhere/run_test_module.yml")
        assert (
            relocated.migration_report_path == relocated.role_path / "export-output.md"
        )
        assert original.project_path == Path("ansible")

    def test_requirements_prefer_role_then_collection_then_project(self):
        layout = build_layout()

        assert layout.requirements_search_paths == (
            layout.role_path / "requirements.yml",
            layout.collection_path / "requirements.yml",
            Path("ansible/collections/requirements.yml"),
            Path("ansible/requirements.yml"),
        )
        assert layout.molecule_requirements_path not in layout.requirements_search_paths
