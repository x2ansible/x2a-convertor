"""Generate AAP configuration and publish an Ansible project to AAP."""

from src.config import get_settings
from src.publishers.aap_config_as_code import AAPConfigAsCodeGenerator
from src.publishers.models import AAPConfigRequest, PublishResult
from src.publishers.tools import sync_to_aap
from src.utils.logging import get_logger

logger = get_logger(__name__)


def publish_aap(
    *,
    target_repo: str,
    target_branch: str,
    project_id: str,
    module_name: str,
    inventory: str | None = None,
    scm_credential_name: str | None = None,
    job_credential_names: list[str] | None = None,
    execution_environment_name: str | None = None,
) -> PublishResult:
    """Generate local AAP files, then request synchronization.

    Args:
        target_repo: Git repository URL (e.g., https://github.com/org/repo.git).
        target_branch: Git branch name, already containing the generated project.
        project_id: Migration project ID, used for AAP project naming.
        module_name: Normalized module name identifying the playbook to publish.

    Raises:
        ValueError: If local generation inputs are invalid.
        RuntimeError: If AAP is not configured or synchronization fails.
    """
    organization = get_settings().aap.org_name
    if not organization:
        raise RuntimeError("AAP_ORG_NAME is required for Config-as-Code generation")
    request = AAPConfigRequest.from_project(
        ".",
        project_id=project_id,
        module_name=module_name,
        organization=organization,
        target_repository_url=target_repo,
        target_branch=target_branch,
        inventory=inventory,
        scm_credential_name=scm_credential_name,
        job_credential_names=job_credential_names,
        execution_environment_name=execution_environment_name,
    )
    generation = AAPConfigAsCodeGenerator(request).generate()
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
    return PublishResult(generation=generation, sync=result)
