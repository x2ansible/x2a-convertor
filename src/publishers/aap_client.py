"""Ansible Automation Platform (Controller) REST API client.

This module is intentionally small and opinionated:
- It is used by the publisher workflow (CLI-driven) to upsert a Project
  pointing at the GitHub repository that was just created/pushed.
- It supports username/password (basic auth) now, and bearer token later.
- It is environment-driven (no CLI flags required).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class AAPConfig:
    controller_url: str
    organization_name: str
    api_prefix: str = "/api/controller/v2"
    oauth_token: str | None = None
    username: str | None = None
    password: str | None = None
    ca_bundle_path: str | None = None
    verify_ssl: bool = True
    timeout_s: float = 30.0


def load_aap_config_from_env() -> AAPConfig | None:
    """Load AAP config from environment.

    Returns:
        AAPConfig when AAP integration is configured, otherwise None.

    Notes:
        We treat AAP integration as optional and env-driven:
        - If AAP_CONTROLLER_URL is missing, integration is disabled.
        - If URL exists but required fields are missing, we raise.
    """
    controller_url = (os.environ.get("AAP_CONTROLLER_URL") or "").strip()
    if not controller_url:
        return None

    organization_name = (os.environ.get("AAP_ORG_NAME") or "").strip()
    if not organization_name:
        error_msg = "AAP_ORG_NAME is required when AAP_CONTROLLER_URL is set"
        raise ValueError(error_msg)

    api_prefix = (os.environ.get("AAP_API_PREFIX") or "/api/controller/v2").strip()
    if not api_prefix.startswith("/"):
        raise ValueError("AAP_API_PREFIX must start with '/', e.g. /api/controller/v2")
    api_prefix = api_prefix.rstrip("/")

    ca_bundle_path = (os.environ.get("AAP_CA_BUNDLE") or "").strip() or None
    if ca_bundle_path:
        ca_path_obj = Path(ca_bundle_path)
        if not ca_path_obj.exists():
            raise ValueError(
                f"AAP_CA_BUNDLE is set but file does not exist: {ca_bundle_path}"
            )
        if not ca_path_obj.is_file():
            raise ValueError(
                f"AAP_CA_BUNDLE is set but is not a file: {ca_bundle_path}"
            )

    verify_ssl_raw = (os.environ.get("AAP_VERIFY_SSL") or "true").strip().lower()
    verify_ssl = verify_ssl_raw in {"1", "true", "yes"}

    timeout_raw = (os.environ.get("AAP_TIMEOUT_S") or "30").strip()
    try:
        timeout_s = float(timeout_raw)
    except ValueError as e:
        raise ValueError(f"AAP_TIMEOUT_S must be a number, got: {timeout_raw}") from e

    return AAPConfig(
        controller_url=controller_url,
        organization_name=organization_name,
        api_prefix=api_prefix,
        oauth_token=(os.environ.get("AAP_OAUTH_TOKEN") or "").strip() or None,
        username=(os.environ.get("AAP_USERNAME") or "").strip() or None,
        password=(os.environ.get("AAP_PASSWORD") or "").strip() or None,
        ca_bundle_path=ca_bundle_path,
        verify_ssl=verify_ssl,
        timeout_s=timeout_s,
    )


class AAPClient:
    """Minimal client for AAP/Controller API (/api/v2)."""

    def __init__(self, cfg: AAPConfig) -> None:
        self._cfg = cfg
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        token = cfg.oauth_token
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def _url(self, path: str) -> str:
        base = self._cfg.controller_url.rstrip("/")
        p = path if path.startswith("/") else f"/{path}"
        return f"{base}{p}"

    def _api(self, path: str) -> str:
        p = path if path.startswith("/") else f"/{path}"
        return f"{self._cfg.api_prefix}{p}"

    def _auth(self) -> tuple[str, str] | None:
        if self._cfg.oauth_token:
            return None

        username = self._cfg.username
        password = self._cfg.password
        if username and password:
            return (username, password)

        error_msg = "AAP auth missing: set AAP_OAUTH_TOKEN or AAP_USERNAME/AAP_PASSWORD"
        raise ValueError(error_msg)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        verify: bool | str = self._cfg.verify_ssl
        if self._cfg.ca_bundle_path:
            verify = self._cfg.ca_bundle_path

        resp = self._session.request(
            method=method,
            url=self._url(path),
            auth=self._auth(),
            json=json,
            params=params,
            verify=verify,
            timeout=self._cfg.timeout_s,
        )
        resp.raise_for_status()
        if resp.status_code == 204:
            return {}
        return resp.json()

    def find_organization_id(self, *, name: str) -> int:
        data = self._request(
            "GET",
            self._api("/organizations/"),
            params={"name": name},
        )
        results = data.get("results", [])
        if not results:
            raise RuntimeError(f"AAP organization not found: {name}")
        return int(results[0]["id"])

    def find_project(self, *, org_id: int, name: str) -> dict[str, Any] | None:
        data = self._request(
            "GET",
            self._api("/projects/"),
            params={"organization": org_id, "name": name},
        )
        results = data.get("results", [])
        if not results:
            return None
        return results[0]

    def upsert_project(
        self,
        *,
        org_id: int,
        name: str,
        scm_url: str,
        scm_branch: str,
        description: str,
        scm_credential_id: int | None = None,
    ) -> dict[str, Any]:
        existing = self.find_project(org_id=org_id, name=name)
        if not existing:
            payload: dict[str, Any] = {
                "name": name,
                "description": description,
                "organization": org_id,
                "scm_type": "git",
                "scm_url": scm_url,
                "scm_branch": scm_branch,
                "scm_update_on_launch": True,
                "scm_clean": True,
                "scm_delete_on_update": True,
            }
            if scm_credential_id:
                payload["credential"] = scm_credential_id

            return self._request("POST", self._api("/projects/"), json=payload)

        project_id = int(existing["id"])
        patch: dict[str, Any] = {
            "scm_url": scm_url,
            "scm_branch": scm_branch,
            "description": description,
        }
        if scm_credential_id is not None:
            patch["credential"] = scm_credential_id

        return self._request(
            "PATCH",
            self._api(f"/projects/{project_id}/"),
            json=patch,
        )

    def start_project_update(self, *, project_id: int) -> dict[str, Any]:
        return self._request(
            "POST",
            self._api(f"/projects/{project_id}/update/"),
            json={},
        )


def infer_aap_project_name(repository_url: str) -> str:
    """Infer a stable AAP project name from a git clone URL."""
    url = repository_url.strip()
    if not url:
        return "ansible-project"

    # Common pattern: https://github.com/org/repo.git
    last = url.rstrip("/").split("/")[-1]
    name = last.removesuffix(".git").strip()
    if not name:
        return "ansible-project"
    return name


def infer_aap_project_description(repository_url: str, branch: str) -> str:
    repo = repository_url.strip()
    br = branch.strip() or "main"
    return f"GitOps project from {repo} (branch: {br})"
