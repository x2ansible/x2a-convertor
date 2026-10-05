from unittest.mock import MagicMock

import pytest

from src.exporters.services.ansible_scaffold import (
    DEFAULT_NAMESPACE,
    DEFAULT_PROJECT,
    AnsibleCreator,
    AnsibleProject,
)


def create_role_files(path):
    (path / "tasks").mkdir(parents=True)
    (path / "tasks" / "main.yml").touch()
    (path / "meta").mkdir()
    (path / "meta" / "main.yml").touch()


def test_create_role_scaffolds_in_adjacent_collection(tmp_path):
    project_path = tmp_path / "playbook"
    collection_path = (
        project_path / "collections" / "ansible_collections" / "x2a" / "project"
    )
    creator = MagicMock()

    def create_role(*arguments, **kwargs):
        create_role_files(collection_path / "roles" / kwargs["role_name"])

    creator.run.side_effect = create_role
    project = AnsibleProject(project_path, creator)

    role_path = project.create_role("My-Role")

    assert role_path == collection_path / "roles" / "my_role"
    assert not (role_path / "tasks" / "main.yml").exists()
    assert project.check_role("my_role")
    creator.run.assert_called_once_with(
        "add",
        "resource",
        "role",
        role_name="my_role",
        path=str(collection_path),
    )


def test_create_role_is_idempotent_when_role_exists(tmp_path):
    project_path = tmp_path / "playbook"
    creator = MagicMock()
    project = AnsibleProject(project_path, creator)
    role_path = project.collection_path / "roles" / "role_name"
    create_role_files(role_path)

    assert project.create_role("role_name") == role_path
    assert (role_path / "tasks" / "main.yml").exists()
    creator.run.assert_not_called()


def test_scaffold_initializes_playbook_project_with_default_fqcn(tmp_path):
    project_path = tmp_path / "playbook"
    creator = MagicMock()
    project = AnsibleProject.ensure(project_path, creator)

    assert isinstance(project, AnsibleProject)
    assert project.path == project_path
    assert project.collection_path == (
        project_path / "collections" / "ansible_collections" / "x2a" / "project"
    )
    creator.run.assert_called_once_with(
        "init",
        "playbook",
        collection=f"{DEFAULT_NAMESPACE}.{DEFAULT_PROJECT}",
        init_path=str(project_path),
    )


def test_scaffold_removes_creator_template_collection_requirements(tmp_path):
    project_path = tmp_path / "playbook"
    requirements_path = project_path / "collections" / "requirements.yml"
    creator = MagicMock()

    def initialize(*arguments, **kwargs):
        requirements_path.parent.mkdir(parents=True)
        requirements_path.write_text("collections:\n  - name: cisco.ios\n")

    creator.run.side_effect = initialize

    AnsibleProject.ensure(project_path, creator)

    assert not requirements_path.exists()


def test_scaffold_does_not_reinitialize_nonempty_project(tmp_path):
    project_path = tmp_path / "playbook"
    project_path.mkdir()
    (project_path / "ansible.cfg").touch()
    creator = MagicMock()

    AnsibleProject.ensure(project_path, creator)

    creator.run.assert_not_called()


def test_creator_raises_for_failed_api_result():
    api = MagicMock()
    api.run.return_value.status = "error"
    api.run.return_value.message = "invalid project"

    with pytest.raises(RuntimeError, match="invalid project"):
        AnsibleCreator(api).run("init", "playbook")


def test_role_check_rejects_missing_or_incomplete_role(tmp_path):
    project = AnsibleProject(tmp_path, MagicMock())
    (project.collection_path / "roles" / "incomplete").mkdir(parents=True)

    assert project.check_role("absent") is False
    assert project.check_role("incomplete") is False


def test_create_role_refuses_to_overwrite_incomplete_role(tmp_path):
    creator = MagicMock()
    project = AnsibleProject(tmp_path, creator)
    role_path = project.collection_path / "roles" / "partial"
    role_path.mkdir(parents=True)

    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        project.create_role("partial")

    creator.run.assert_not_called()
