"""Ansible Automation Platform (Controller) REST API client.

This module is intentionally small and opinionated:
- It is used by the publisher workflow (CLI-driven) to upsert a Project
  pointing at the GitHub repository that was just created/pushed.
- It supports username/password (basic auth) now, and bearer token later.
- It is environment-driven (no CLI flags required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import AAPSettings, get_settings
from src.publishers.base_client import BaseAAPClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AAPConfig:
    """Configuration for Ansible Automation Platform integration.

    This class wraps AAPSettings from the centralized config module
    and provides backwards-compatible interface for the AAPClient.

    Environment Variables (loaded via pydantic-settings):
        AAP_CONTROLLER_URL: Controller base URL (required to enable)
        AAP_ORG_NAME: Organization name (required when enabled)
        AAP_API_PREFIX: API path prefix (default: /api/controller/v2)
        AAP_OAUTH_TOKEN: OAuth token for auth
        AAP_USERNAME: Username for basic auth
        AAP_PASSWORD: Password for basic auth
        AAP_CA_BUNDLE: Path to CA bundle for self-signed certs
        AAP_VERIFY_SSL: Verify SSL (true/false, default: true)
        AAP_TIMEOUT_S: Request timeout in seconds (default: 30)
        AAP_PROJECT_NAME: Project name (default: inferred from repo URL)
        AAP_SCM_CREDENTIAL_ID: Credential ID for private repos
    """

    controller_url: str | None = None
    organization_name: str | None = None
    api_prefix: str = "/api/controller/v2"
    oauth_token: str | None = None
    username: str | None = None
    password: str | None = None
    ca_bundle_path: str | None = None
    verify_ssl: bool = True
    timeout_s: float = 30.0
    _settings: AAPSettings | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Load configuration from centralized settings if not explicitly set."""
        if self._settings is None:
            self._settings = get_settings().aap

        s = self._settings
        self.controller_url = self.controller_url or s.controller_url
        self.organization_name = self.organization_name or s.org_name
        self.api_prefix = (
            self.api_prefix if self.api_prefix != "/api/controller/v2" else s.api_prefix
        ).rstrip("/")
        self.oauth_token = self.oauth_token or (
            s.oauth_token.get_secret_value() if s.oauth_token else None
        )
        self.username = self.username or s.username
        self.password = self.password or (
            s.password.get_secret_value() if s.password else None
        )
        self.ca_bundle_path = self.ca_bundle_path or s.ca_bundle
        self.verify_ssl = s.verify_ssl
        self.timeout_s = s.timeout_s

    def is_enabled(self) -> bool:
        """Check if AAP integration is enabled (controller_url is set)."""
        return bool(self.controller_url)

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        if not self.controller_url:
            return []

        errors: list[str] = []

        if not self.organization_name:
            errors.append("AAP_ORG_NAME is required when AAP_CONTROLLER_URL is set")

        if not self.api_prefix.startswith("/"):
            errors.append("AAP_API_PREFIX must start with '/', e.g. /api/controller/v2")

        if self.ca_bundle_path:
            ca_path_obj = Path(self.ca_bundle_path)
            if not ca_path_obj.exists():
                errors.append(
                    f"AAP_CA_BUNDLE file does not exist: {self.ca_bundle_path}"
                )
            elif not ca_path_obj.is_file():
                errors.append(f"AAP_CA_BUNDLE is not a file: {self.ca_bundle_path}")

        if not self.oauth_token and not (self.username and self.password):
            errors.append(
                "Auth required: set AAP_OAUTH_TOKEN or AAP_USERNAME + AAP_PASSWORD"
            )

        return errors

    @classmethod
    def from_env(cls) -> AAPConfig | None:
        """Load config from environment.

        Returns:
            AAPConfig if enabled and valid, None if disabled.

        Raises:
            ValueError: If enabled but configuration is invalid.
        """
        config = cls()

        if not config.is_enabled():
            return None

        errors = config.validate()
        if errors:
            raise ValueError("; ".join(errors))

        return config


class AAPClient(BaseAAPClient):
    """Client for AAP Controller API (/api/controller/v2).

    Extends BaseAAPClient to share session and SSL configuration.
    Accepts AAPConfig for backward compatibility with existing code.
    """

    def __init__(self, cfg: AAPConfig) -> None:
        self._cfg = cfg
        # Pass the underlying settings to BaseAAPClient
        super().__init__(cfg._settings)

    @property
    def _base_url(self) -> str:
        """Return the Controller API base URL."""
        if not self._cfg.controller_url:
            raise ValueError("controller_url is not configured")
        return self._cfg.controller_url.rstrip("/")

    @property
    def _api_prefix(self) -> str:
        """Return the Controller API path prefix."""
        return self._cfg.api_prefix

    @property
    def _auth_header_format(self) -> str:
        """Controller API uses Bearer token format."""
        return "Bearer"

    def find_organization_id(self, *, name: str) -> int:
        data = self._request(
            "GET",
            "/organizations/",
            params={"name": name},
        )
        results = data.get("results", [])
        if not results:
            raise RuntimeError(f"AAP organization not found: {name}")
        return int(results[0]["id"])

    def find_project(self, *, org_id: int, name: str) -> dict[str, Any] | None:
        data = self._request(
            "GET",
            "/projects/",
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

            return self._request("POST", "/projects/", json=payload)

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
            f"/projects/{project_id}/",
            json=patch,
        )

    def start_project_update(self, *, project_id: int) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/projects/{project_id}/update/",
            json={},
        )

    def upsert_execution_environment(
        self,
        *,
        name: str,
        image: str,
        org_id: int,
        pull: str = "always",
    ) -> dict[str, Any]:
        """Create or update an Execution Environment on AAP.

        Args:
            name: EE display name
            image: Container image URL (e.g., quay.io/org/ee:latest)
            org_id: Organization ID
            pull: Image pull policy (always, missing, never)

        Returns:
            EE resource dict from AAP API
        """
        # Search by name only — EE may exist with organization=null
        data = self._request(
            "GET",
            "/execution_environments/",
            params={"name": name},
        )
        results = data.get("results", [])

        if not results:
            return self._request(
                "POST",
                "/execution_environments/",
                json={
                    "name": name,
                    "image": image,
                    "organization": org_id,
                    "pull": pull,
                },
            )

        ee_id = int(results[0]["id"])
        if results[0].get("image") != image:
            return self._request(
                "PATCH",
                f"/execution_environments/{ee_id}/",
                json={"image": image, "pull": pull},
            )
        return results[0]

    def find_or_create_inventory(
        self,
        *,
        org_id: int,
        name: str = "Molecule Local",
    ) -> dict[str, Any]:
        """Find an existing inventory or create a localhost one.

        Args:
            org_id: Organization ID
            name: Inventory name to search for / create

        Returns:
            Inventory resource dict from AAP API
        """
        data = self._request(
            "GET",
            "/inventories/",
            params={"name": name, "organization": org_id},
        )
        results = data.get("results", [])
        if results:
            return results[0]

        # Create inventory
        inventory = self._request(
            "POST",
            "/inventories/",
            json={"name": name, "organization": org_id},
        )
        inventory_id = int(inventory["id"])

        # Add localhost host with local connection
        self._request(
            "POST",
            f"/inventories/{inventory_id}/hosts/",
            json={
                "name": "localhost",
                "variables": '{"ansible_connection": "local"}',
            },
        )
        logger.info(f"Created inventory '{name}' (id={inventory_id}) with localhost")
        return inventory

    def upsert_job_template(
        self,
        *,
        org_id: int,
        name: str,
        project_id: int,
        playbook: str,
        execution_environment_id: int | None = None,
        inventory_id: int | None = None,
    ) -> dict[str, Any]:
        """Create or update a Job Template on AAP.

        Args:
            org_id: Organization ID
            name: Job template name
            project_id: AAP project ID
            playbook: Playbook path relative to project root
            execution_environment_id: EE to use (optional)
            inventory_id: Inventory to assign (optional). When set,
                ask_inventory_on_launch is disabled for one-click launch.

        Returns:
            Job template resource dict from AAP API
        """
        data = self._request(
            "GET",
            "/job_templates/",
            params={"name": name, "organization": org_id},
        )
        results = data.get("results", [])

        payload: dict[str, Any] = {
            "name": name,
            "project": project_id,
            "playbook": playbook,
        }
        if inventory_id:
            payload["inventory"] = inventory_id
            payload["ask_inventory_on_launch"] = False
        else:
            payload["ask_inventory_on_launch"] = True

        if execution_environment_id:
            payload["execution_environment"] = execution_environment_id

        if not results:
            payload["organization"] = org_id
            return self._request("POST", "/job_templates/", json=payload)

        template_id = int(results[0]["id"])
        return self._request(
            "PATCH",
            f"/job_templates/{template_id}/",
            json=payload,
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


def infer_aap_project_description(
    repository_url: str, branch: str, *, project_id: str = ""
) -> str:
    repo = repository_url.strip()
    br = branch.strip() or "main"
    desc = f"GitOps project from {repo} (branch: {br})"
    if project_id:
        desc += f" — playbooks at {project_id}/ansible-project"
    return desc
