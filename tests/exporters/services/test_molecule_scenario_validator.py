from pathlib import Path

import pytest
import yaml

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_scenario_templates import MoleculeScenarioTemplates
from src.exporters.services.molecule_scenario_validator import MoleculeScenarioValidator
from src.exporters.services.molecule_scenario_writer import MoleculeScenarioWriter
from src.types import AnsibleModule

VALID_VERIFY = """---
- name: Verify migrated service
  hosts: all
  tasks:
    - name: Assert service state
      ansible.builtin.assert:
        that:
          - ansible_facts['services']['httpd.service']['state'] == 'running'
"""


def create_validator(
    tmp_path: Path,
) -> tuple[MoleculeScenarioValidator, AnsibleProjectLayout]:
    layout = AnsibleProjectLayout.from_module(
        AnsibleModule("web_server"), project_path=tmp_path / "ansible"
    )
    files = MoleculeScenarioTemplates(layout).files()
    MoleculeScenarioWriter().write_missing(files)
    return MoleculeScenarioValidator(layout), layout


def test_validator_rejects_missing_verify_playbook(tmp_path):
    validator, layout = create_validator(tmp_path)
    files = MoleculeScenarioTemplates(layout).files()

    errors = validator.validate(list(files))

    assert any("verify.yml" in error for error in errors)


def test_validator_rejects_debug_only_verify_playbook(tmp_path):
    validator, layout = create_validator(tmp_path)
    layout.molecule_verify_path.write_text(
        "---\n- hosts: all\n  tasks:\n"
        "    - ansible.builtin.debug:\n        msg: placeholder\n"
    )

    assert (
        "verify.yml must contain at least one behavior assertion"
        in validator.validate([layout.molecule_verify_path])
    )


def test_validator_accepts_concrete_assertions(tmp_path):
    validator, layout = create_validator(tmp_path)
    layout.molecule_verify_path.write_text(VALID_VERIFY)
    files = MoleculeScenarioTemplates(layout).files()

    assert validator.validate([*files, layout.molecule_verify_path]) == []


def test_validator_accepts_no_supported_expectations(tmp_path):
    validator, layout = create_validator(tmp_path)
    layout.molecule_verify_path.write_text(
        "---\n- name: No supported pre-flight checks\n  hosts: all\n  tasks: []\n"
    )
    files = MoleculeScenarioTemplates(layout).files()

    assert validator.validate([*files, layout.molecule_verify_path]) == []


def test_validator_reports_invalid_yaml(tmp_path):
    validator, layout = create_validator(tmp_path)
    layout.molecule_verify_path.write_text("- tasks: [\n")

    errors = validator.validate([layout.molecule_verify_path])

    assert errors and "Invalid YAML" in errors[0]


class TestMalformedScenario:
    @pytest.fixture
    def layout(self, tmp_path):
        _, layout = create_validator(tmp_path)
        layout.molecule_verify_path.write_text(VALID_VERIFY)
        return layout

    def validate(self, layout):
        files = MoleculeScenarioTemplates(layout).files()
        return MoleculeScenarioValidator(layout).validate(
            [*files, layout.molecule_verify_path]
        )

    @pytest.mark.parametrize(
        "content",
        [
            "- hosts: all\n",
            "- hosts: all\n  tasks: null\n",
            "- hosts: all\n  tasks: {}\n",
            "- hosts: all\n  tasks: [invalid]\n",
            "- hosts: localhost\n  tasks: []\n",
            "- hosts: all\n  tasks: []\n- hosts: production\n  tasks: []\n",
            "- hosts: all\n  tasks: []\n---\n- hosts: all\n  tasks: []\n",
        ],
    )
    def test_rejects_invalid_verification_structure(self, layout, content):
        layout.molecule_verify_path.write_text(content)

        assert self.validate(layout)

    @pytest.mark.parametrize(
        "condition", [None, True, False, 1, "", " ", "true", [], ["true"]]
    )
    def test_rejects_vacuous_assertions(self, layout, condition):
        playbook = [
            {"hosts": "all", "tasks": [{"ansible.builtin.assert": {"that": condition}}]}
        ]
        layout.molecule_verify_path.write_text(yaml.safe_dump(playbook))

        assert any(
            "concrete expected behavior" in error for error in self.validate(layout)
        )

    @pytest.mark.parametrize(
        ("section", "value"),
        [
            ("driver", None),
            ("driver", {"name": "podman"}),
            ("driver", {"name": "docker"}),
            ("provisioner", {"name": "ansible"}),
            ("verifier", {"name": "ansible"}),
            ("platforms", [None]),
            ("scenario", None),
            ("scenario", {"test_sequence": [None, {}]}),
            ("ansible", {"executor": True, "playbooks": True}),
            (
                "ansible",
                {
                    "executor": {"backend": "ansible-playbook"},
                    "playbooks": {
                        "prepare": "prepare.yml",
                        "converge": "converge.yml",
                        "verify": "verify.yml",
                    },
                    "env": None,
                },
            ),
            ("dependency", {"options": None}),
            (
                "dependency",
                {
                    "options": {
                        "requirements-file": "${MOLECULE_PROJECT_DIRECTORY}/molecule/requirements.yml"
                    },
                    "env": None,
                },
            ),
        ],
    )
    def test_reports_malformed_configuration_without_raising(
        self, layout, section, value
    ):
        path = layout.molecule_scenario_path / "molecule.yml"
        config = yaml.safe_load(path.read_text())
        config[section] = value
        path.write_text(yaml.safe_dump(config))

        assert self.validate(layout)

    @pytest.mark.parametrize(
        "content",
        [
            "42",
            "null",
            "- tasks: null",
            "- tasks: [ansible.builtin.include_role: wrong]",
        ],
    )
    def test_reports_malformed_deployment_without_raising(self, layout, content):
        layout.run_playbook_path.write_text(content)

        assert any("Deployment playbook" in error for error in self.validate(layout))

    @pytest.mark.parametrize("action", ["create", "destroy"])
    def test_lifecycle_must_execute_on_controller(self, layout, action):
        path = layout.molecule_scenario_path / f"{action}.yml"
        playbook = yaml.safe_load(path.read_text())
        playbook[0]["hosts"] = "all"
        path.write_text(yaml.safe_dump(playbook))

        assert any("locally" in error for error in self.validate(layout))

    @pytest.mark.parametrize("action", ["create", "destroy"])
    def test_lifecycle_must_use_inventory_and_explicit_state(self, layout, action):
        path = layout.molecule_scenario_path / f"{action}.yml"
        playbook = yaml.safe_load(path.read_text())
        playbook[0]["tasks"][0]["containers.podman.podman_container"]["state"] = (
            "stopped"
        )
        path.write_text(yaml.safe_dump(playbook))

        assert any("inventory containers" in error for error in self.validate(layout))

    def test_create_requires_container_inspection(self, layout):
        path = layout.molecule_scenario_path / "create.yml"
        playbook = yaml.safe_load(path.read_text())
        playbook[0]["tasks"] = playbook[0]["tasks"][:1]
        path.write_text(yaml.safe_dump(playbook))

        assert any("podman_container_info" in error for error in self.validate(layout))

    @pytest.mark.parametrize(
        "filename", ["create.yml", "destroy.yml", "inventory/hosts.yml"]
    )
    def test_missing_native_artifacts_fail_validation(self, layout, filename):
        (layout.molecule_scenario_path / filename).unlink()

        assert any(filename in error for error in self.validate(layout))

    @pytest.mark.parametrize(
        "hosts",
        [None, {}, [], {"target": None}, {"target": {"ansible_connection": "ssh"}}],
    )
    def test_inventory_rejects_malformed_or_non_podman_targets(self, layout, hosts):
        path = layout.molecule_scenario_path / "inventory" / "hosts.yml"
        path.write_text(
            yaml.safe_dump({"all": {"children": {"molecule": {"hosts": hosts}}}})
        )

        assert any("inventory" in error for error in self.validate(layout))

    def test_inventory_rejects_unrelated_hosts(self, layout):
        path = layout.molecule_scenario_path / "inventory" / "hosts.yml"
        inventory = yaml.safe_load(path.read_text())
        inventory["all"]["hosts"] = {"production": {}}
        path.write_text(yaml.safe_dump(inventory))

        assert any("only disposable" in error for error in self.validate(layout))

    def test_sequence_order_matters(self, layout):
        path = layout.molecule_scenario_path / "molecule.yml"
        config = yaml.safe_load(path.read_text())
        config["scenario"]["test_sequence"].reverse()
        path.write_text(yaml.safe_dump(config))

        assert any("in order" in error for error in self.validate(layout))

    def test_builtin_default_driver_is_allowed(self, layout):
        path = layout.molecule_scenario_path / "molecule.yml"
        config = yaml.safe_load(path.read_text())
        config["driver"] = {"name": "default"}
        path.write_text(yaml.safe_dump(config))

        assert self.validate(layout) == []

    def test_import_path_in_unrelated_field_is_not_an_import(self, layout):
        converge = layout.molecule_scenario_path / "converge.yml"
        converge.write_text(
            f"- name: ../../{layout.run_playbook_path.name}\n  hosts: all\n"
        )

        assert any("does not import" in error for error in self.validate(layout))
