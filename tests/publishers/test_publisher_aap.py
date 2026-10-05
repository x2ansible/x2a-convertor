"""Tests for repository-only AAP publishing."""

from dataclasses import FrozenInstanceError
from unittest.mock import call

import pytest
import requests

from src.publishers.aap_client import (
    AAPClient,
    AAPConfig,
    infer_aap_project_description,
    infer_aap_project_name,
)
from src.publishers.tools import AAPSyncResult, sync_to_aap


class TestSyncToAAP:
    @pytest.fixture
    def client(self, monkeypatch, mocker):
        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
        monkeypatch.setenv("AAP_ORG_NAME", "Default")
        monkeypatch.setenv("AAP_OAUTH_TOKEN", "test-token")
        client = mocker.patch(
            "src.publishers.tools.AAPClient", autospec=True
        ).return_value
        client.find_organization_id.return_value = 1
        client.upsert_project.return_value = {"id": 42}
        client.start_project_update.return_value = {"id": 100, "status": "pending"}
        return client

    def test_disabled_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("AAP_CONTROLLER_URL", raising=False)
        result = sync_to_aap("https://github.com/acme/repo.git", "main")
        assert result.enabled is False
        assert result.error == ""

    def test_missing_org_returns_error(self, monkeypatch):
        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
        monkeypatch.delenv("AAP_ORG_NAME", raising=False)
        result = sync_to_aap("https://github.com/acme/repo.git", "main")
        assert result.enabled is True
        assert "AAP_ORG_NAME is required" in result.error

    def test_invalid_scm_credential_id_returns_error(self, client, monkeypatch):
        monkeypatch.setenv("AAP_SCM_CREDENTIAL_ID", "nope")
        result = sync_to_aap("https://github.com/acme/repo.git", "main")
        assert "scm_credential_id" in result.error
        assert "int" in result.error.lower()
        assert not client.mock_calls

    def test_sync_only_registers_project_and_requests_update(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("AAP_SCM_CREDENTIAL_ID", "7")
        # Legacy environment variables must not trigger any extra provisioning.
        monkeypatch.setenv("AAP_EE_IMAGE", "quay.io/legacy/ee:latest")
        monkeypatch.setenv("AAP_INVENTORY_NAME", "Molecule Local")
        result = sync_to_aap("https://github.com/acme/repo.git", "main", "migration-1")
        assert result.error == ""
        assert result.project_name == "migration-1"
        assert result.project_id == 42
        assert result.project_update_id == 100
        assert result.project_update_status == "pending"
        assert not list(tmp_path.iterdir())
        assert client.mock_calls == [
            call.find_organization_id(name="Default"),
            call.upsert_project(
                org_id=1,
                name="migration-1",
                scm_url="https://github.com/acme/repo.git",
                scm_branch="main",
                description="GitOps project from https://github.com/acme/repo.git (branch: main) — migration project: migration-1",
                scm_credential_id=7,
            ),
            call.start_project_update(project_id=42),
        ]

    @pytest.mark.parametrize(
        ("override", "project_id", "expected"),
        [("custom", "migration-1", "custom"), (None, "", "repo")],
    )
    def test_project_naming(self, client, monkeypatch, override, project_id, expected):
        if override:
            monkeypatch.setenv("AAP_PROJECT_NAME", override)
        result = sync_to_aap("https://github.com/acme/repo.git", "dev", project_id)
        assert result.project_name == expected

    def test_missing_project_id_returns_error(self, client):
        client.upsert_project.return_value = {}
        result = sync_to_aap("https://github.com/acme/repo.git", "main")
        assert "did not return a project id" in result.error
        client.start_project_update.assert_not_called()

    @pytest.mark.parametrize(
        "method", ["find_organization_id", "upsert_project", "start_project_update"]
    )
    @pytest.mark.parametrize(
        "error", [RuntimeError("denied"), requests.ConnectionError("denied")]
    )
    def test_api_failure_returns_error(self, client, method, error):
        getattr(client, method).side_effect = error
        result = sync_to_aap("https://github.com/acme/repo.git", "main")
        assert result.enabled is True
        assert result.error == "denied"


class TestAAPConfig:
    def test_disabled(self, monkeypatch):
        monkeypatch.delenv("AAP_CONTROLLER_URL", raising=False)
        assert AAPConfig.from_env() is None

    def test_missing_org_raises(self, monkeypatch):
        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
        monkeypatch.delenv("AAP_ORG_NAME", raising=False)
        with pytest.raises(ValueError, match="AAP_ORG_NAME is required"):
            AAPConfig.from_env()

    def test_auth_missing(self, monkeypatch):
        for variable in ("AAP_OAUTH_TOKEN", "AAP_USERNAME", "AAP_PASSWORD"):
            monkeypatch.delenv(variable, raising=False)
        cfg = AAPConfig(
            controller_url="https://aap.example", organization_name="Default"
        )
        assert any("Auth required" in error for error in cfg.validate())

    def test_explicit_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://env.example.com")
        monkeypatch.setenv("AAP_ORG_NAME", "env-org")
        monkeypatch.setenv("AAP_OAUTH_TOKEN", "env-token")
        cfg = AAPConfig(
            controller_url="https://explicit.example.com",
            organization_name="explicit-org",
        )
        assert cfg.controller_url == "https://explicit.example.com"
        assert cfg.organization_name == "explicit-org"
        assert cfg.oauth_token == "env-token"


class TestAAPClient:
    @pytest.mark.parametrize(
        ("existing", "method", "path"),
        [(None, "POST", "/projects/"), ({"id": 7}, "PATCH", "/projects/7/")],
    )
    def test_upsert_project(self, mocker, existing, method, path):
        cfg = AAPConfig(
            controller_url="https://aap.example",
            organization_name="Default",
            oauth_token="t",
        )
        client = AAPClient(cfg)
        find = mocker.patch.object(client, "find_project", return_value=existing)
        request = mocker.patch.object(client, "_request", return_value={"id": 7})
        result = client.upsert_project(
            org_id=1,
            name="proj",
            scm_url="https://github.com/acme/repo.git",
            scm_branch="dev",
            description="description",
            scm_credential_id=10,
        )
        assert result["id"] == 7
        find.assert_called_once_with(org_id=1, name="proj")
        assert request.call_args.args == (method, path)
        payload = request.call_args.kwargs["json"]
        assert payload["scm_url"] == "https://github.com/acme/repo.git"
        assert payload["scm_branch"] == "dev"
        assert payload["credential"] == 10
        assert payload["description"] == "description"
        if existing is None:
            assert payload["organization"] == 1
            assert payload["scm_type"] == "git"

    def test_start_project_update(self, mocker):
        client = AAPClient(
            AAPConfig(controller_url="https://aap.example", oauth_token="t")
        )
        request = mocker.patch.object(client, "_request", return_value={"id": 100})
        assert client.start_project_update(project_id=42) == {"id": 100}
        request.assert_called_once_with("POST", "/projects/42/update/", json={})

    def test_inferred_name(self):
        assert infer_aap_project_name("") == "ansible-project"
        assert infer_aap_project_name("https://github.com/acme/repo.git") == "repo"

    def test_description_has_no_assumed_project_directory(self):
        description = infer_aap_project_description(
            "https://github.com/acme/repo.git", "dev", project_id="migration-1"
        )
        assert "branch: dev" in description
        assert "migration-1" in description
        assert "ansible-project" not in description
        assert "playbooks at" not in description


class TestAAPSyncResult:
    def test_result_is_immutable(self):
        result = AAPSyncResult.disabled()

        with pytest.raises(FrozenInstanceError):
            result.__setattr__("enabled", True)

    def test_from_update(self):
        result = AAPSyncResult.from_update(
            "project", 42, {"id": "100", "status": "pending"}
        )
        assert result.enabled
        assert result.project_name == "project"
        assert result.project_id == 42
        assert result.project_update_id == 100
        assert result.project_update_status == "pending"
        assert result.error == ""

    def test_from_update_missing_optional_fields(self):
        result = AAPSyncResult.from_update("project", 42, {})
        assert result.project_update_id is None
        assert result.project_update_status == ""

    def test_summary_reports_request_not_completion(self):
        result = AAPSyncResult.from_update(
            "project", 42, {"id": 100, "status": "pending"}
        )
        assert result.report_summary() == [
            "  Result: SYNC REQUESTED",
            "  Project: project",
            "  Project ID: 42",
            "  Sync job ID: 100",
            "  Sync job status: pending",
        ]

    def test_disabled_summary(self):
        assert AAPSyncResult.disabled().report_summary() == [
            "  Disabled (AAP not configured)."
        ]

    def test_error_summary(self):
        assert AAPSyncResult.from_error("denied").report_summary() == [
            "  Result: FAILED",
            "  Error: denied",
        ]
