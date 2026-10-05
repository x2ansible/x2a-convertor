"""Publish an existing Ansible project's Git repository to AAP."""

from src.publishers.tools import AAPSyncResult, sync_to_aap
from src.utils.logging import get_logger

logger = get_logger(__name__)


def publish_aap(
    target_repo: str,
    target_branch: str,
    project_id: str,
) -> AAPSyncResult:
    """Create/update an AAP project and request synchronization of its repository.

    Args:
        target_repo: Git repository URL (e.g., https://github.com/org/repo.git).
        target_branch: Git branch name, already containing the generated project.
        project_id: Migration project ID, used for AAP project naming.

    Returns:
        AAPSyncResult with the initial sync job status; does not wait for completion.

    Raises:
        RuntimeError: If AAP is not configured or the sync request fails.
    """
    logger.info(
        f"Syncing to AAP: repo={target_repo} branch={target_branch} project_id={project_id}"
    )
    result = sync_to_aap(
        repository_url=target_repo,
        branch=target_branch,
        project_id=project_id,
    )
    if not result.enabled:
        raise RuntimeError(
            "AAP is not configured. Set AAP_CONTROLLER_URL and related "
            "environment variables."
        )
    if result.error:
        raise RuntimeError(f"AAP sync failed: {result.error}")

    for line in result.report_summary():
        logger.info(line)
    return result
