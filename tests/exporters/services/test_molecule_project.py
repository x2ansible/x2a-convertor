from pathlib import Path

import pytest
import yaml

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_project import MoleculeProject
from src.types import AnsibleModule


class TestMoleculeProject:
    @pytest.fixture
    def layout(self, tmp_path: Path) -> AnsibleProjectLayout:
        return AnsibleProjectLayout.from_module(
            AnsibleModule("web_server"), project_path=tmp_path / "ansible"
        )

    def test_scaffold_creates_ansible_native_scenario(self, layout):
        project = MoleculeProject(layout)

        project.scaffold()

        scenario = layout.molecule_scenario_path
        config = yaml.safe_load((scenario / "molecule.yml").read_text())
        assert "driver" not in config
        assert "platforms" not in config
        assert config["ansible"]["executor"]["backend"] == "ansible-playbook"
        assert (scenario / "inventory" / "hosts.yml").is_file()
        assert (scenario / "create.yml").is_file()
        assert (scenario / "destroy.yml").is_file()
        assert project.validate_scaffold() == []
        assert layout.molecule_verify_path not in project.templates.files()
        assert any("verify.yml" in error for error in project.validate())

    def test_scaffold_preserves_existing_artifacts(self, layout):
        project = MoleculeProject(layout)
        project.scaffold()
        deployment = layout.run_playbook_path
        deployment.write_text("# user-maintained deployment entry point\n")

        project.scaffold()

        assert deployment.read_text() == "# user-maintained deployment entry point\n"

    def test_fresh_instance_can_validate_existing_files(self, layout):
        MoleculeProject(layout).scaffold()
        layout.molecule_verify_path.write_text("- hosts: all\n  tasks: []\n")

        assert MoleculeProject(layout).validate() == []

    def test_fresh_instance_checks_all_expected_files(self, layout):
        layout.molecule_scenario_path.mkdir(parents=True)
        layout.molecule_verify_path.write_text("- hosts: all\n  tasks: []\n")

        errors = MoleculeProject(layout).validate()

        assert any(str(layout.run_playbook_path) in error for error in errors)
        assert any("prepare.yml" in error for error in errors)
