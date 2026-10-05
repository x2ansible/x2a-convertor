"""AAP project synchronization for the publishing workflow."""

from dataclasses import dataclass

import requests

from src.config import get_settings
from src.publishers.aap_client import (
    AAPClient,
    AAPConfig,
    infer_aap_project_description,
    infer_aap_project_name,
)


@dataclass(frozen=True)
class AAPSyncResult:
    """Result of requesting a repository sync on AAP."""

    enabled: bool = False
    project_name: str = ""
    project_id: int | None = None
    project_update_id: int | None = None
    project_update_status: str = ""
    error: str = ""

    @classmethod
    def disabled(cls) -> "AAPSyncResult":
        """Create a result indicating AAP is not enabled."""
        return cls(enabled=False)

    @classmethod
    def from_error(cls, error: str) -> "AAPSyncResult":
        """Create a result indicating an error occurred."""
        return cls(enabled=True, error=error)

    @classmethod
    def from_update(
        cls, project_name: str, project_id: int, update: dict
    ) -> "AAPSyncResult":
        """Create a result from the Controller's project update response."""
        return cls(
            enabled=True,
            project_name=project_name,
            project_id=project_id,
            project_update_id=int(update["id"]) if "id" in update else None,
            project_update_status=update.get("status", ""),
        )

    def report_summary(self) -> list[str]:
        """Generate summary lines for this AAP sync request."""
        if not self.enabled:
            return ["  Disabled (AAP not configured)."]
        if self.error:
            return ["  Result: FAILED", f"  Error: {self.error}"]

        lines = ["  Result: SYNC REQUESTED"]
        if self.project_name:
            lines.append(f"  Project: {self.project_name}")
        if self.project_id is not None:
            lines.append(f"  Project ID: {self.project_id}")
        if self.project_update_id is not None:
            lines.append(f"  Sync job ID: {self.project_update_id}")
        if self.project_update_status:
            lines.append(f"  Sync job status: {self.project_update_status}")
        return lines


def sync_to_aap(
    repository_url: str,
    branch: str,
    project_id: str = "",
) -> AAPSyncResult:
    """Upsert an AAP Project and trigger a sync, without waiting for completion.

    Returns a disabled result when AAP_CONTROLLER_URL is unset, or an error
    result for invalid configuration or API failures. The repository must
    already contain the generated Ansible project; no local files are needed.
    """
    try:
        cfg = AAPConfig.from_env()
        if cfg is None:
            return AAPSyncResult.disabled()

        settings = get_settings()
        project_name = (
            settings.aap.project_name
            or project_id
            or infer_aap_project_name(repository_url)
        )
        client = AAPClient(cfg)
        assert cfg.organization_name  # Validated by from_env()
        org_id = client.find_organization_id(name=cfg.organization_name)
        project = client.upsert_project(
            org_id=org_id,
            name=project_name,
            scm_url=repository_url,
            scm_branch=branch,
            description=infer_aap_project_description(
                repository_url, branch, project_id=project_id
            ),
            scm_credential_id=settings.aap.scm_credential_id,
        )
        aap_project_id = int(project.get("id", 0))
        if not aap_project_id:
            return AAPSyncResult.from_error("AAP API did not return a project id")

        update = client.start_project_update(project_id=aap_project_id)
        return AAPSyncResult.from_update(project_name, aap_project_id, update)
    except (requests.exceptions.RequestException, RuntimeError, ValueError) as e:
        return AAPSyncResult.from_error(str(e))
