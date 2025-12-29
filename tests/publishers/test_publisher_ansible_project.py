"""Tests for Ansible project creation in publisher.

Uses real file operations via tmp_path for happy paths, and mocker for
simulating system-level failures like PermissionError.
"""

from __future__ import annotations

import pytest
import yaml

from src.publishers.tools import (
    copy_role_directory,
    create_directory_structure,
    generate_ansible_cfg,
    generate_collections_requirements,
    generate_inventory_file,
    generate_playbook_yaml,
)

# -----------------------------------------------------------------------------
# Directory Structure Tests
# -----------------------------------------------------------------------------


def test_create_directory_structure_creates_all_dirs(tmp_path):
    """Test that all required directories are created."""
    base_path = tmp_path / "ansible_project"
    structure = ["collections", "inventory", "roles", "playbooks"]

    create_directory_structure(base_path=str(base_path), structure=structure)

    for dir_name in structure:
        assert (base_path / dir_name).is_dir()


def test_create_directory_structure_base_path_is_file_raises(tmp_path):
    """Test that base_path cannot be a file."""
    base_path = tmp_path / "not_a_dir"
    base_path.write_text("x")

    with pytest.raises(OSError):
        create_directory_structure(base_path=str(base_path), structure=["roles"])


def test_create_directory_structure_permission_error(mocker, tmp_path):
    """Test graceful handling when mkdir fails due to permissions."""
    mocker.patch("pathlib.Path.mkdir", side_effect=PermissionError("denied"))

    with pytest.raises(PermissionError):
        create_directory_structure(
            base_path=str(tmp_path / "project"),
            structure=["roles"],
        )


# -----------------------------------------------------------------------------
# Copy Role Directory Tests (Parametrized)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role_fixtures", "expected_roles"),
    [
        (["sample_role_dir"], ["sample_role"]),
        (["sample_role_dir", "sample_role_dir2"], ["sample_role", "sample_role2"]),
    ],
    ids=["single_role", "multiple_roles"],
)
def test_copy_roles(tmp_path, role_fixtures, expected_roles, request):
    """Test copying single or multiple roles to the project."""
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir(parents=True)

    for fixture_name, role_name in zip(role_fixtures, expected_roles, strict=True):
        source_dir = request.getfixturevalue(fixture_name)
        destination = roles_dir / role_name

        copy_role_directory(
            source_role_path=source_dir,
            destination_path=str(destination),
        )

        # Verify role was copied with correct structure
        assert destination.is_dir()
        assert (destination / "tasks" / "main.yml").exists()
        assert (destination / "meta" / "main.yml").exists()

        # Parse and verify tasks file is valid YAML
        tasks_content = yaml.safe_load((destination / "tasks" / "main.yml").read_text())
        assert isinstance(tasks_content, list)


def test_copy_role_directory_missing_source_raises(tmp_path):
    """Test that copying from a missing source path fails."""
    with pytest.raises(FileNotFoundError):
        copy_role_directory(
            source_role_path=str(tmp_path / "does_not_exist"),
            destination_path=str(tmp_path / "roles" / "sample_role"),
        )


def test_copy_role_directory_permission_error(mocker, tmp_path, sample_role_dir):
    """Test graceful handling when copytree fails due to permissions."""
    mocker.patch(
        "src.publishers.tools.shutil.copytree",
        side_effect=PermissionError("denied"),
    )

    with pytest.raises(OSError, match="copy"):
        copy_role_directory(
            source_role_path=sample_role_dir,
            destination_path=str(tmp_path / "roles" / "sample_role"),
        )


# -----------------------------------------------------------------------------
# Playbook Generation Tests (Parametrized)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role_name", "playbook_name", "hosts", "become"),
    [
        ("sample_role", "Run sample_role", "all", False),
        ("web_server", "Deploy web_server", "webservers", True),
    ],
    ids=["default_hosts", "custom_hosts_with_become"],
)
def test_generate_playbook_yaml(tmp_path, role_name, playbook_name, hosts, become):
    """Test playbook generation with various configurations."""
    playbook_path = tmp_path / f"run_{role_name}.yml"

    generate_playbook_yaml(
        file_path=str(playbook_path),
        name=playbook_name,
        role_name=role_name,
        hosts=hosts,
        become=become,
    )

    assert playbook_path.exists()

    # Parse and verify YAML structure
    content = yaml.safe_load(playbook_path.read_text())
    assert isinstance(content, list)
    assert len(content) == 1

    play = content[0]
    assert play["name"] == playbook_name
    assert play["hosts"] == hosts
    assert "roles" in play
    assert any(role_name in str(r) for r in play["roles"])

    if become:
        assert play.get("become") is True


def test_generate_playbook_yaml_missing_role_name_raises(tmp_path):
    """Test that playbook generation requires role_name."""
    with pytest.raises(ValueError, match="role_name is required"):
        generate_playbook_yaml(
            file_path=str(tmp_path / "playbook.yml"),
            name="Run missing",
            role_name="",
        )


def test_generate_playbook_yaml_permission_error(mocker, tmp_path):
    """Test graceful handling when file write fails due to permissions."""
    mocker.patch("pathlib.Path.open", side_effect=PermissionError("denied"))

    with pytest.raises(OSError):
        generate_playbook_yaml(
            file_path=str(tmp_path / "playbook.yml"),
            name="Test",
            role_name="test_role",
        )


# -----------------------------------------------------------------------------
# Ansible Config Tests
# -----------------------------------------------------------------------------


def test_generate_ansible_cfg_creates_valid_file(tmp_path):
    """Test that generate_ansible_cfg creates a valid config file."""
    cfg_path = tmp_path / "ansible.cfg"
    generate_ansible_cfg(str(cfg_path))

    assert cfg_path.exists()

    content = cfg_path.read_text()
    # Verify essential config sections/keys
    assert "[defaults]" in content
    assert "roles_path" in content
    assert "collections_paths" in content


def test_generate_ansible_cfg_path_is_directory_raises(tmp_path):
    """Test that ansible.cfg path cannot be a directory."""
    cfg_path = tmp_path / "ansible.cfg"
    cfg_path.mkdir()

    with pytest.raises(OSError):
        generate_ansible_cfg(str(cfg_path))


def test_generate_ansible_cfg_permission_error(mocker, tmp_path):
    """Test graceful handling when config write fails due to permissions."""
    mocker.patch("pathlib.Path.open", side_effect=PermissionError("denied"))

    with pytest.raises(OSError):
        generate_ansible_cfg(str(tmp_path / "ansible.cfg"))


# -----------------------------------------------------------------------------
# Collections Requirements Tests (Parametrized)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("collections_input", "expected_count", "expected_first_name"),
    [
        (None, 0, None),
        ([], 0, None),
        ([{"name": "community.general"}], 1, "community.general"),
        (
            [
                {"name": "community.general", "version": ">=5.0.0"},
                {"name": "ansible.posix", "version": "1.5.0"},
            ],
            2,
            "community.general",
        ),
    ],
    ids=["default_none", "empty_list", "single_collection", "multiple_collections"],
)
def test_generate_collections_requirements(
    tmp_path,
    collections_input,
    expected_count,
    expected_first_name,
):
    """Test collections requirements generation with various inputs."""
    req_path = tmp_path / "requirements.yml"

    generate_collections_requirements(str(req_path), collections=collections_input)

    assert req_path.exists()

    # Parse and verify YAML structure
    content = yaml.safe_load(req_path.read_text())
    assert isinstance(content, dict)
    assert "collections" in content
    assert isinstance(content["collections"], list)
    assert len(content["collections"]) == expected_count

    if expected_count > 0:
        assert content["collections"][0]["name"] == expected_first_name


def test_generate_collections_requirements_path_is_directory_raises(tmp_path):
    """Test that requirements.yml path cannot be a directory."""
    req_path = tmp_path / "requirements.yml"
    req_path.mkdir()

    with pytest.raises(OSError):
        generate_collections_requirements(str(req_path))


def test_generate_collections_requirements_permission_error(mocker, tmp_path):
    """Test graceful handling when requirements write fails due to permissions."""
    mocker.patch("pathlib.Path.open", side_effect=PermissionError("denied"))

    with pytest.raises(OSError):
        generate_collections_requirements(str(tmp_path / "requirements.yml"))


# -----------------------------------------------------------------------------
# Inventory File Tests (Parametrized)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("inventory_input", "expected_structure"),
    [
        (
            None,
            {"has_all": True, "group_count": None},
        ),
        (
            {"all": {"children": {"webservers": {"hosts": {"web1": {}}}}}},
            {"has_all": True, "group_count": 1, "group_name": "webservers"},
        ),
        (
            {
                "all": {
                    "children": {
                        "webservers": {"hosts": {"web1": {"ansible_host": "1.2.3.4"}}},
                        "dbservers": {"hosts": {"db1": {"ansible_host": "5.6.7.8"}}},
                    }
                }
            },
            {"has_all": True, "group_count": 2, "group_name": "webservers"},
        ),
    ],
    ids=["default_inventory", "single_group", "multiple_groups"],
)
def test_generate_inventory_file(tmp_path, inventory_input, expected_structure):
    """Test inventory generation with various inputs."""
    inv_path = tmp_path / "hosts.yml"

    generate_inventory_file(str(inv_path), inventory=inventory_input)

    assert inv_path.exists()

    # Parse and verify YAML structure
    content = yaml.safe_load(inv_path.read_text())
    assert isinstance(content, dict)
    assert expected_structure["has_all"] == ("all" in content)

    if expected_structure.get("group_count") is not None:
        children = content["all"].get("children", {})
        assert len(children) == expected_structure["group_count"]
        assert expected_structure["group_name"] in children


def test_generate_inventory_file_path_is_directory_raises(tmp_path):
    """Test that inventory file path cannot be a directory."""
    inv_path = tmp_path / "hosts.yml"
    inv_path.mkdir()

    with pytest.raises(OSError):
        generate_inventory_file(str(inv_path))


def test_generate_inventory_file_permission_error(mocker, tmp_path):
    """Test graceful handling when inventory write fails due to permissions."""
    mocker.patch("pathlib.Path.open", side_effect=PermissionError("denied"))

    with pytest.raises(OSError):
        generate_inventory_file(str(tmp_path / "hosts.yml"))


# -----------------------------------------------------------------------------
# Integration Test: Full Project Structure
# -----------------------------------------------------------------------------


def test_full_project_structure_generation(tmp_path, sample_role_dir):
    """Integration test: verify complete project generation produces valid files."""
    base_path = tmp_path / "ansible_project"

    # 1. Create directory structure
    create_directory_structure(
        base_path=str(base_path),
        structure=["collections", "inventory", "roles", "playbooks"],
    )

    # 2. Copy role
    copy_role_directory(
        source_role_path=sample_role_dir,
        destination_path=str(base_path / "roles" / "sample_role"),
    )

    # 3. Generate playbook
    generate_playbook_yaml(
        file_path=str(base_path / "playbooks" / "run_sample_role.yml"),
        name="Run sample_role",
        role_name="sample_role",
    )

    # 4. Generate ansible.cfg
    generate_ansible_cfg(str(base_path / "ansible.cfg"))

    # 5. Generate collections requirements
    generate_collections_requirements(
        str(base_path / "collections" / "requirements.yml"),
        collections=[{"name": "community.general"}],
    )

    # 6. Generate inventory
    generate_inventory_file(
        str(base_path / "inventory" / "hosts.yml"),
        inventory={"all": {"children": {"test": {"hosts": {"host1": {}}}}}},
    )

    # Verify all files exist and are valid YAML where applicable
    assert (base_path / "ansible.cfg").exists()

    playbook = yaml.safe_load(
        (base_path / "playbooks" / "run_sample_role.yml").read_text()
    )
    assert isinstance(playbook, list)
    assert playbook[0]["name"] == "Run sample_role"

    requirements = yaml.safe_load(
        (base_path / "collections" / "requirements.yml").read_text()
    )
    assert requirements["collections"][0]["name"] == "community.general"

    inventory = yaml.safe_load((base_path / "inventory" / "hosts.yml").read_text())
    assert "test" in inventory["all"]["children"]

    role_tasks = yaml.safe_load(
        (base_path / "roles" / "sample_role" / "tasks" / "main.yml").read_text()
    )
    assert isinstance(role_tasks, list)
