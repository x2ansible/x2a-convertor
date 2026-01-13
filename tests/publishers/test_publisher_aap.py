"""Tests for AAP integration used by the publisher workflow."""

from __future__ import annotations

from typing import Any

import pytest

from src.publishers import aap_client
from src.publishers import tools as tools_module
from src.publishers.tools import sync_to_aap


def test_sync_to_aap_disabled_when_env_not_set(monkeypatch):
    monkeypatch.delenv("AAP_CONTROLLER_URL", raising=False)
    monkeypatch.delenv("AAP_ORG_NAME", raising=False)

    result = sync_to_aap(
        repository_url="https://github.com/acme/repo.git", branch="main"
    )
    assert result.enabled is False
    assert result.error == ""


def test_sync_to_aap_enabled_but_missing_org_returns_error(monkeypatch):
    monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
    monkeypatch.delenv("AAP_ORG_NAME", raising=False)

    result = sync_to_aap(
        repository_url="https://github.com/acme/repo.git", branch="main"
    )
    assert result.enabled is True
    assert "AAP_ORG_NAME is required" in (result.error or "")


def test_sync_to_aap_invalid_scm_credential_id_returns_error(monkeypatch):
    monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
    monkeypatch.setenv("AAP_ORG_NAME", "Default")
    monkeypatch.setenv("AAP_USERNAME", "u")
    monkeypatch.setenv("AAP_PASSWORD", "p")
    monkeypatch.setenv("AAP_SCM_CREDENTIAL_ID", "nope")

    result = sync_to_aap(
        repository_url="https://github.com/acme/repo.git", branch="main"
    )
    assert result.enabled is True
    # pydantic-settings validates type at load time
    assert "scm_credential_id" in (result.error or "")
    assert "int" in (result.error or "").lower()


def test_sync_to_aap_happy_flow(monkeypatch):
    monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
    monkeypatch.setenv("AAP_ORG_NAME", "Default")
    monkeypatch.setenv("AAP_USERNAME", "u")
    monkeypatch.setenv("AAP_PASSWORD", "p")

    calls: dict[str, object] = {}

    class FakeClient:
        def __init__(self, cfg):
            calls["cfg"] = cfg

        def find_organization_id(self, *, name: str) -> int:
            assert name == "Default"
            calls["org"] = name
            return 1

        def upsert_project(
            self,
            *,
            org_id: int,
            name: str,
            scm_url: str,
            scm_branch: str,
            description: str,
            scm_credential_id=None,
        ):
            assert org_id == 1
            assert scm_url.endswith(".git")
            assert scm_branch == "main"
            assert description
            calls["project_name"] = name
            return {"id": 42}

        def start_project_update(self, *, project_id: int):
            assert project_id == 42
            return {"id": 100, "status": "successful"}

    monkeypatch.setattr(tools_module, "AAPClient", FakeClient)

    result = sync_to_aap(
        repository_url="https://github.com/acme/repo.git", branch="main"
    )
    assert result.enabled is True
    assert result.error == ""
    assert result.project_id == 42
    assert result.project_update_id == 100
    assert result.project_update_status == "successful"
    assert calls.get("org") == "Default"


def test_sync_to_aap_client_failure_returns_error(monkeypatch):
    monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
    monkeypatch.setenv("AAP_ORG_NAME", "Default")
    monkeypatch.setenv("AAP_USERNAME", "u")
    monkeypatch.setenv("AAP_PASSWORD", "p")

    class FakeClient:
        def __init__(self, cfg):
            pass

        def find_organization_id(self, *, name: str) -> int:
            raise RuntimeError("org not found")

    monkeypatch.setattr(tools_module, "AAPClient", FakeClient)

    result = sync_to_aap(
        repository_url="https://github.com/acme/repo.git", branch="main"
    )
    assert result.enabled is True
    assert "org not found" in (result.error or "")


def test_aapconfig_from_env_disabled(monkeypatch):
    monkeypatch.delenv("AAP_CONTROLLER_URL", raising=False)
    cfg = aap_client.AAPConfig.from_env()
    assert cfg is None


def test_aapconfig_from_env_missing_org_raises(monkeypatch):
    monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example")
    monkeypatch.delenv("AAP_ORG_NAME", raising=False)
    monkeypatch.delenv("AAP_OAUTH_TOKEN", raising=False)
    monkeypatch.delenv("AAP_USERNAME", raising=False)
    monkeypatch.delenv("AAP_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="AAP_ORG_NAME is required"):
        aap_client.AAPConfig.from_env()


def test_aap_client_auth_missing_validation():
    """Test that AAPConfig validation catches missing auth."""
    cfg = aap_client.AAPConfig(
        controller_url="https://aap.example", organization_name="Default"
    )
    errors = cfg.validate()
    assert any("Auth required" in e for e in errors)


def test_aap_client_upsert_project_creates_when_missing(monkeypatch):
    cfg = aap_client.AAPConfig(
        controller_url="https://aap.example",
        organization_name="Default",
        oauth_token="t",
    )
    client = aap_client.AAPClient(cfg)

    called: dict[str, Any] = {}

    def fake_find_project(*, org_id: int, name: str):
        assert org_id == 1
        assert name == "proj"
        return None

    def fake_request(method: str, path: str, *, json=None, params=None):
        called["method"] = method
        called["path"] = path
        called["json"] = json
        return {"id": 9}

    monkeypatch.setattr(client, "find_project", fake_find_project)
    monkeypatch.setattr(client, "_request", fake_request)

    out = client.upsert_project(
        org_id=1,
        name="proj",
        scm_url="https://github.com/acme/repo.git",
        scm_branch="main",
        description="d",
        scm_credential_id=None,
    )

    assert out["id"] == 9
    assert called["method"] == "POST"
    assert "/projects/" in str(called["path"])
    assert called["json"]["organization"] == 1
    assert called["json"]["scm_url"].endswith(".git")


def test_aap_client_upsert_project_updates_when_exists(monkeypatch):
    cfg = aap_client.AAPConfig(
        controller_url="https://aap.example",
        organization_name="Default",
        oauth_token="t",
    )
    client = aap_client.AAPClient(cfg)

    called: dict[str, Any] = {}

    def fake_find_project(*, org_id: int, name: str):
        return {"id": 7}

    def fake_request(method: str, path: str, *, json=None, params=None):
        called["method"] = method
        called["path"] = path
        called["json"] = json
        return {"id": 7}

    monkeypatch.setattr(client, "find_project", fake_find_project)
    monkeypatch.setattr(client, "_request", fake_request)

    out = client.upsert_project(
        org_id=1,
        name="proj",
        scm_url="https://github.com/acme/repo.git",
        scm_branch="dev",
        description="d2",
        scm_credential_id=10,
    )

    assert out["id"] == 7
    assert called["method"] == "PATCH"
    assert "/projects/7/" in str(called["path"])
    assert called["json"]["scm_branch"] == "dev"
    assert called["json"]["credential"] == 10


def test_infer_aap_project_name_defaults():
    assert aap_client.infer_aap_project_name("") == "ansible-project"
    assert (
        aap_client.infer_aap_project_name("https://github.com/acme/repo.git") == "repo"
    )


def test_infer_aap_project_description_includes_branch():
    desc = aap_client.infer_aap_project_description(
        "https://github.com/acme/repo.git", "dev"
    )
    assert "branch: dev" in desc


def test_aapconfig_explicit_overrides_env(monkeypatch):
    """Explicit constructor values take precedence over environment."""
    monkeypatch.setenv("AAP_CONTROLLER_URL", "https://env.example.com")
    monkeypatch.setenv("AAP_ORG_NAME", "env-org")
    monkeypatch.setenv("AAP_OAUTH_TOKEN", "env-token")

    cfg = aap_client.AAPConfig(
        controller_url="https://explicit.example.com",
        organization_name="explicit-org",
    )

    assert cfg.controller_url == "https://explicit.example.com"
    assert cfg.organization_name == "explicit-org"
    # oauth_token not passed, so comes from env
    assert cfg.oauth_token == "env-token"
