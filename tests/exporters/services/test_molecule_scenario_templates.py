from pathlib import Path

import yaml

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_contract import TEST_SEQUENCE
from src.exporters.services.molecule_scenario_templates import MoleculeScenarioTemplates
from src.types import AnsibleModule


def test_templates_render_from_layout_without_touching_filesystem(tmp_path):
    layout = AnsibleProjectLayout.from_module(
        AnsibleModule("web_server"), project_path=tmp_path / "ansible"
    )

    files = MoleculeScenarioTemplates(layout).files()

    assert not layout.project_path.exists()
    assert layout.fqcn in files[layout.run_playbook_path]
    assert layout.molecule_verify_path not in files
    config = yaml.safe_load(files[layout.molecule_scenario_path / "molecule.yml"])
    assert not {"driver", "platforms", "provisioner", "verifier"}.intersection(config)
    assert config["ansible"]["executor"]["args"]["ansible_playbook"] == [
        "--inventory=${MOLECULE_SCENARIO_DIRECTORY}/inventory/"
    ]
    inventory = yaml.safe_load(
        files[layout.molecule_scenario_path / "inventory" / "hosts.yml"]
    )
    target = next(iter(inventory["all"]["children"]["molecule"]["hosts"].values()))
    assert target["container_command"] == "/sbin/init"
    assert target["ansible_connection"] == "containers.podman.podman"
    assert (
        config["dependency"]["env"]["ANSIBLE_COLLECTIONS_PATH"]
        == "${MOLECULE_PROJECT_DIRECTORY}/collections"
    )


class TestNativeLifecycle:
    def test_generated_files_match_the_checklist(self, tmp_path):
        layout = AnsibleProjectLayout.from_module(AnsibleModule("web"), tmp_path)
        files = MoleculeScenarioTemplates(layout).files()

        assert {str(path) for path in files} | {
            str(layout.molecule_verify_path)
        } == set(layout.molecule_checklist_targets())

    def test_lifecycle_is_local_and_target_connection_waits_for_python(self, tmp_path):
        layout = AnsibleProjectLayout.from_module(AnsibleModule("web"), tmp_path)
        files = MoleculeScenarioTemplates(layout).files()
        scenario = layout.molecule_scenario_path
        create = yaml.safe_load(files[scenario / "create.yml"])[0]
        destroy = yaml.safe_load(files[scenario / "destroy.yml"])[0]
        prepare = yaml.safe_load(files[scenario / "prepare.yml"])[0]

        for play in (create, destroy):
            assert play["hosts"] == "localhost"
            assert play["connection"] == "local"
            assert play["gather_facts"] is False
            for task in play["tasks"]:
                assert task["loop"] == "{{ groups['molecule'] }}"
                assert task["loop_control"]["loop_var"] == "item_target"
        assert "containers.podman.podman_container_info" in create["tasks"][1]
        assert create["tasks"][1]["until"]
        assert destroy["tasks"][0]["containers.podman.podman_container"] == {
            "name": "{{ item_target }}",
            "state": "absent",
            "force_delete": True,
        }
        assert prepare["hosts"] == "molecule"
        assert "ansible.builtin.raw" in prepare["tasks"][0]
        assert "ansible.builtin.wait_for_connection" in prepare["tasks"][1]

    def test_config_maps_all_actions_and_readme_needs_no_plugins(self, tmp_path):
        layout = AnsibleProjectLayout.from_module(AnsibleModule("web"), tmp_path)
        files = MoleculeScenarioTemplates(layout).files()
        config = yaml.safe_load(files[layout.molecule_scenario_path / "molecule.yml"])

        assert config["scenario"]["test_sequence"] == list(TEST_SEQUENCE)
        for action, filename in config["ansible"]["playbooks"].items():
            assert filename == f"{action}.yml"
            assert (
                layout.molecule_scenario_path / filename in files or action == "verify"
            )
        readme = files[layout.molecule_readme_path]
        assert "molecule-plugins" not in readme
        assert "molecule destroy" in readme
        assert "privileged" in readme


def test_converge_template_imports_the_project_deployment_playbook(tmp_path):
    layout = AnsibleProjectLayout.from_module(
        AnsibleModule("web_server"), project_path=Path("ansible")
    )
    files = MoleculeScenarioTemplates(layout).files()

    assert (
        "../../run_web_server.yml"
        in files[layout.molecule_scenario_path / "converge.yml"]
    )
