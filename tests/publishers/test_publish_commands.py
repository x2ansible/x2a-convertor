"""Tests for the publish-aap function and CLI contract."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from src.publishers.models import AAPConfigGenerationResult, PublishResult
from src.publishers.publish import publish_aap
from src.publishers.tools import AAPSyncResult


class TestPublishAAP:
    @staticmethod
    def prepare_project(tmp_path, monkeypatch):
        (tmp_path / "ansible").mkdir()
        (tmp_path / "ansible" / "run_module.yml").write_text("---\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "src.publishers.publish.get_settings",
            lambda: Mock(aap=Mock(org_name="Default", project_name=None)),
        )

    @patch("src.publishers.publish.sync_to_aap")
    def test_aap_not_configured_raises(self, mock_sync, tmp_path, monkeypatch):
        self.prepare_project(tmp_path, monkeypatch)
        mock_sync.return_value = AAPSyncResult.disabled()
        with pytest.raises(RuntimeError, match="not configured"):
            publish_aap(
                target_repo="https://github.com/org/repo.git",
                target_branch="main",
                project_id="proj-1",
                module_name="module",
            )

    @patch("src.publishers.publish.sync_to_aap")
    def test_aap_error_raises(self, mock_sync, tmp_path, monkeypatch):
        self.prepare_project(tmp_path, monkeypatch)
        mock_sync.return_value = AAPSyncResult.from_error("Connection refused")
        with pytest.raises(RuntimeError, match="Connection refused"):
            publish_aap(
                target_repo="https://github.com/org/repo.git",
                target_branch="main",
                project_id="proj-1",
                module_name="module",
            )

    @patch("src.publishers.publish.sync_to_aap")
    def test_generation_failure_does_not_sync(self, mock_sync, tmp_path, monkeypatch):
        (tmp_path / "ansible").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(
            "src.publishers.publish.get_settings",
            lambda: Mock(aap=Mock(org_name="Default", project_name=None)),
        )

        with pytest.raises(ValueError, match="playbook does not exist"):
            publish_aap(
                target_repo="https://github.com/org/repo.git",
                target_branch="main",
                project_id="proj-1",
                module_name="module",
            )

        mock_sync.assert_not_called()

    @patch("src.publishers.publish.sync_to_aap")
    def test_aap_success(self, mock_sync, tmp_path, monkeypatch):
        self.prepare_project(tmp_path, monkeypatch)
        mock_sync.return_value = AAPSyncResult.from_update(
            "test-project", 42, {"id": 100, "status": "pending"}
        )
        result = publish_aap(
            target_repo="https://github.com/org/repo.git",
            target_branch="main",
            project_id="proj-1",
            module_name="module",
        )
        assert result.sync.project_name == "test-project"
        assert result.sync.project_id == 42
        mock_sync.assert_called_once_with(
            repository_url="https://github.com/org/repo.git",
            branch="main",
            project_id="proj-1",
            project_name="proj-1",
        )


class TestPublishCLI:
    ARGS = (
        "publish-aap",
        "--target-repo",
        "https://github.com/org/repo.git",
        "--target-branch",
        "main",
        "--project-id",
        "proj-1",
        "--module-name",
        "module",
    )

    @pytest.fixture
    def command(self):
        # Importing the CLI loads LiteLLM, which otherwise loads the local .env.
        with patch("dotenv.load_dotenv"):
            from app import cli
        return cli

    def test_removed_command_is_not_registered(self, command):
        assert "publish-project" not in command.commands
        result = CliRunner().invoke(command, ["publish-project", "proj-1", "role"])
        assert result.exit_code == 2
        assert "No such command" in result.output

    def test_molecule_option_is_rejected(self, command):
        result = CliRunner().invoke(command, [*self.ARGS, "--molecule-roles", "nginx"])
        assert result.exit_code == 2
        assert "No such option" in result.output
        assert "--molecule-roles" in result.output

    @patch("app.publish_aap")
    def test_publish_requests_sync_without_local_project(
        self, publish, tmp_path, monkeypatch, command
    ):
        monkeypatch.chdir(tmp_path)
        publish.return_value = PublishResult(
            generation=AAPConfigGenerationResult(
                changed=False,
                module_name="module",
                module_directory=tmp_path / "ansible" / "aap-config" / "module",
                project_name="proj-1",
                job_template_name="proj-1_module",
                files=[],
            ),
            sync=AAPSyncResult.from_update(
                "proj-1", 42, {"id": 100, "status": "pending"}
            ),
        )
        result = CliRunner().invoke(command, self.ARGS)
        assert result.exit_code == 0, result.output
        assert "AAP project sync requested: proj-1 (ID: 42)" in result.output
        assert not list(tmp_path.iterdir())
        publish.assert_called_once_with(
            target_repo="https://github.com/org/repo.git",
            target_branch="main",
            project_id="proj-1",
            module_name="module",
            inventory=None,
            scm_credential_name=None,
            job_credential_names=[],
            execution_environment_name=None,
        )

    @patch("app.publish_aap", side_effect=RuntimeError("AAP sync failed: denied"))
    def test_publish_failure_exits_nonzero(self, publish, command):
        result = CliRunner().invoke(command, self.ARGS)
        assert result.exit_code == 1
        assert "AAP sync failed: denied" in result.output
