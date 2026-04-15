"""Tests for publish_project and publish_aap functions."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.publishers.publish import publish_aap, publish_project
from src.publishers.tools import AAPSyncResult


class TestPublishProject:
    """Tests for the publish_project function."""

    def test_first_module_creates_skeleton(self, project_with_module):
        project_dir, module_name = project_with_module
        old_cwd = Path.cwd()
        os.chdir(Path(project_dir).parent)
        try:
            pid = Path(project_dir).name
            result = publish_project(project_id=pid, module_name=module_name)

            project = Path(result)
            assert (project / "ansible.cfg").exists()
            assert (project / "collections" / "requirements.yml").exists()
            assert (project / "inventory" / "hosts.yml").exists()
            assert (project / "roles" / module_name / "tasks" / "main.yml").exists()
            assert (project / "playbooks" / f"run_{module_name}.yml").exists()
            assert (project / "README.md").exists()
            readme_content = (project / "README.md").read_text()
            assert module_name in readme_content
        finally:
            os.chdir(old_cwd)

    def test_second_module_appends_to_existing(self, second_module_in_project):
        project_dir, mod_a, mod_b = second_module_in_project
        old_cwd = Path.cwd()
        os.chdir(Path(project_dir).parent)
        try:
            pid = Path(project_dir).name

            # First module creates skeleton
            publish_project(project_id=pid, module_name=mod_a)
            ansible_project = Path(pid) / "ansible-project"
            cfg_mtime = (ansible_project / "ansible.cfg").stat().st_mtime

            # Second module appends
            publish_project(project_id=pid, module_name=mod_b)

            # ansible.cfg should NOT be overwritten
            assert (ansible_project / "ansible.cfg").stat().st_mtime == cfg_mtime

            # Both roles and playbooks should exist
            assert (ansible_project / "roles" / mod_a).exists()
            assert (ansible_project / "roles" / mod_b).exists()
            assert (ansible_project / "playbooks" / f"run_{mod_a}.yml").exists()
            assert (ansible_project / "playbooks" / f"run_{mod_b}.yml").exists()

            # README should exist and mention both roles
            readme = ansible_project / "README.md"
            assert readme.exists()
            readme_content = readme.read_text()
            assert mod_a in readme_content
            assert mod_b in readme_content
        finally:
            os.chdir(old_cwd)

    def test_missing_source_role_raises(self, tmp_path):
        old_cwd = Path.cwd()
        os.chdir(tmp_path)
        try:
            # No role directory exists at the expected path
            (tmp_path / "proj" / "modules" / "missing_mod" / "ansible" / "roles").mkdir(
                parents=True
            )
            with pytest.raises(
                FileNotFoundError, match="Source role directory not found"
            ):
                publish_project(project_id="proj", module_name="missing_mod")
        finally:
            os.chdir(old_cwd)

    def test_with_collections_file(self, project_with_module, tmp_path):
        project_dir, module_name = project_with_module
        old_cwd = Path.cwd()
        os.chdir(Path(project_dir).parent)
        try:
            pid = Path(project_dir).name

            collections_file = tmp_path / "collections.yml"
            collections_file.write_text(
                '- name: community.general\n  version: ">=5.0.0"\n'
            )

            result = publish_project(
                project_id=pid,
                module_name=module_name,
                collections_file=str(collections_file),
            )

            project = Path(result)
            assert (project / "collections" / "requirements.yml").exists()
        finally:
            os.chdir(old_cwd)


class TestPublishAAP:
    """Tests for the publish_aap function."""

    def test_aap_not_configured_raises(self):
        with pytest.raises(RuntimeError, match="not configured"):
            publish_aap(
                target_repo="https://github.com/org/repo.git",
                target_branch="main",
                project_id="proj-1",
            )

    @patch("src.publishers.publish.sync_to_aap")
    def test_aap_error_raises(self, mock_sync):
        mock_sync.return_value = AAPSyncResult.from_error("Connection refused")

        with pytest.raises(RuntimeError, match="Connection refused"):
            publish_aap(
                target_repo="https://github.com/org/repo.git",
                target_branch="main",
                project_id="proj-1",
            )

    @patch("src.publishers.publish.sync_to_aap")
    def test_aap_success(self, mock_sync):
        mock_sync.return_value = AAPSyncResult(
            enabled=True,
            project_name="test-project",
            project_id=42,
            project_update_id=100,
            project_update_status="pending",
        )

        result = publish_aap(
            target_repo="https://github.com/org/repo.git",
            target_branch="main",
            project_id="proj-1",
        )

        assert result.project_name == "test-project"
        assert result.project_id == 42
        mock_sync.assert_called_once_with(
            repository_url="https://github.com/org/repo.git",
            branch="main",
            project_id="proj-1",
            molecule_role_names=None,
        )
