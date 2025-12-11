"""Tests for Ansible project creation in publisher."""

import yaml

import pytest

from src.publishers.tools import (
    copy_role_directory,
    create_directory_structure,
    generate_ansible_cfg,
    generate_collections_requirements,
    generate_inventory_file,
    generate_playbook_yaml,
)


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary directory for test project."""
    return tmp_path / "ansible_project"


@pytest.fixture
def sample_role_dir(tmp_path):
    """Create a sample role directory structure."""
    role_dir = tmp_path / "sample_role"
    (role_dir / "tasks").mkdir(parents=True)
    (role_dir / "meta").mkdir()
    (role_dir / "tasks" / "main.yml").write_text(
        "- name: Test task\n  debug:\n    msg: Hello"
    )
    (role_dir / "meta" / "main.yml").write_text("---\ndependencies: []")
    return str(role_dir)


@pytest.fixture
def sample_role_dir2(tmp_path):
    """Create a second sample role directory structure."""
    role_dir = tmp_path / "sample_role2"
    (role_dir / "tasks").mkdir(parents=True)
    (role_dir / "meta").mkdir()
    (role_dir / "tasks" / "main.yml").write_text(
        "- name: Test task 2\n  debug:\n    msg: World"
    )
    (role_dir / "meta" / "main.yml").write_text("---\ndependencies: []")
    return str(role_dir)


class TestAnsibleProjectCreation:
    """Test Ansible project structure creation."""

    def test_create_directory_structure(self, temp_project_dir):
        """Test that all required directories are created."""
        structure = [
            "collections",
            "inventory",
            "roles",
            "playbooks",
        ]
        create_directory_structure(
            base_path=str(temp_project_dir), structure=structure
        )

        # Check all directories exist
        assert (temp_project_dir / "collections").exists()
        assert (temp_project_dir / "inventory").exists()
        assert (temp_project_dir / "roles").exists()
        assert (temp_project_dir / "playbooks").exists()

    def test_copy_single_role(self, temp_project_dir, sample_role_dir):
        """Test copying a single role to the project."""
        destination = temp_project_dir / "roles" / "sample_role"
        destination.parent.mkdir(parents=True)

        copy_role_directory(
            source_role_path=sample_role_dir,
            destination_path=str(destination),
        )

        # Check role was copied
        assert destination.exists()
        assert (destination / "tasks" / "main.yml").exists()
        assert (destination / "meta" / "main.yml").exists()

    def test_copy_multiple_roles(
        self, temp_project_dir, sample_role_dir, sample_role_dir2
    ):
        """Test copying multiple roles to the project."""
        roles_dir = temp_project_dir / "roles"
        roles_dir.mkdir(parents=True)

        copy_role_directory(
            source_role_path=sample_role_dir,
            destination_path=str(roles_dir / "sample_role"),
        )
        copy_role_directory(
            source_role_path=sample_role_dir2,
            destination_path=str(roles_dir / "sample_role2"),
        )

        # Check both roles were copied
        assert (roles_dir / "sample_role").exists()
        assert (roles_dir / "sample_role2").exists()

    def test_generate_playbooks_for_roles(
        self, temp_project_dir, sample_role_dir
    ):
        """Test that playbooks are generated for each role."""
        playbooks_dir = temp_project_dir / "playbooks"
        playbooks_dir.mkdir(parents=True)

        playbook_path = playbooks_dir / "run_sample_role.yml"
        generate_playbook_yaml(
            file_path=str(playbook_path),
            name="Run sample_role",
            role_name="sample_role",
        )

        # Check playbook was generated
        assert playbook_path.exists()

        # Check playbook content
        content = playbook_path.read_text()
        assert "sample_role" in content
        assert "roles:" in content

    def test_generate_playbooks_multiple_roles(
        self, temp_project_dir, sample_role_dir, sample_role_dir2
    ):
        """Test that playbooks are generated for multiple roles."""
        playbooks_dir = temp_project_dir / "playbooks"
        playbooks_dir.mkdir(parents=True)

        generate_playbook_yaml(
            file_path=str(playbooks_dir / "run_sample_role.yml"),
            name="Run sample_role",
            role_name="sample_role",
        )
        generate_playbook_yaml(
            file_path=str(playbooks_dir / "run_sample_role2.yml"),
            name="Run sample_role2",
            role_name="sample_role2",
        )

        # Check both playbooks were generated
        assert (playbooks_dir / "run_sample_role.yml").exists()
        assert (playbooks_dir / "run_sample_role2.yml").exists()


class TestAnsibleProjectTools:
    """Test individual tool functions for Ansible project creation."""

    def test_generate_ansible_cfg_creates_file(self, tmp_path):
        """Test that generate_ansible_cfg creates a valid file."""
        cfg_path = tmp_path / "ansible.cfg"
        generate_ansible_cfg(str(cfg_path))

        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert "roles_path" in content
        assert "collections_paths" in content

    def test_generate_collections_requirements_default(self, tmp_path):
        """Test collections requirements with default (None)."""
        req_path = tmp_path / "requirements.yml"
        generate_collections_requirements(str(req_path))

        assert req_path.exists()
        content = yaml.safe_load(req_path.read_text())
        assert "collections" in content
        assert content["collections"] == []

    def test_generate_collections_requirements_with_data(self, tmp_path):
        """Test collections requirements with provided data."""
        collections = [
            {"name": "test.collection", "version": "1.0.0"},
        ]
        req_path = tmp_path / "requirements.yml"
        generate_collections_requirements(
            str(req_path), collections=collections
        )

        assert req_path.exists()
        content = yaml.safe_load(req_path.read_text())
        assert len(content["collections"]) == 1
        assert content["collections"][0]["name"] == "test.collection"

    def test_generate_inventory_default(self, tmp_path):
        """Test inventory generation with default (None)."""
        inv_path = tmp_path / "hosts.yml"
        generate_inventory_file(str(inv_path))

        assert inv_path.exists()
        content = yaml.safe_load(inv_path.read_text())
        assert "all" in content

    def test_generate_inventory_with_data(self, tmp_path):
        """Test inventory generation with provided data."""
        inventory = {
            "all": {
                "children": {
                    "test": {
                        "hosts": {"host1": {"ansible_host": "1.2.3.4"}},
                    },
                },
            },
        }
        inv_path = tmp_path / "hosts.yml"
        generate_inventory_file(str(inv_path), inventory=inventory)

        assert inv_path.exists()
        content = yaml.safe_load(inv_path.read_text())
        assert "test" in content["all"]["children"]
        assert "host1" in content["all"]["children"]["test"]["hosts"]
