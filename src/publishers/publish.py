"""Publisher for Ansible roles — project scaffolding and AAP integration."""

from pathlib import Path

from src.publishers.tools import (
    AAPSyncResult,
    copy_role_directory,
    create_directory_structure,
    generate_ansible_cfg,
    generate_collections_requirements,
    generate_inventory_file,
    generate_playbook_yaml,
    load_collections_file,
    load_inventory_file,
    sync_to_aap,
    verify_files_exist,
)
from src.types.ansible_module import AnsibleModule
from src.utils.logging import get_logger

logger = get_logger(__name__)


def publish_project(
    project_id: str,
    module_name: str,
    collections_file: str | Path | None = None,
    inventory_file: str | Path | None = None,
) -> str:
    """Create or append to an Ansible project structure for a migrated role.

    On the first module migration (no ansible.cfg yet), creates the full
    skeleton: directory structure, ansible.cfg, collections requirements,
    and inventory. On subsequent modules, only the new role and playbook
    are added.

    Args:
        project_id: Migration project ID, used to locate the Ansible Project dir.
        module_name: Name of the single module/role to add.
        collections_file: Path to YAML/JSON file containing collections list.
        inventory_file: Path to YAML/JSON file containing inventory structure.

    Returns:
        Absolute path to the Ansible project directory.

    Raises:
        FileNotFoundError: If the source role directory does not exist.
        OSError: If file operations fail.
    """
    role_name = str(AnsibleModule(module_name))
    source_role_path = (
        Path(project_id) / "modules" / module_name / "ansible" / "roles" / role_name
    )
    ansible_project_dir = Path(project_id) / "ansible-project"

    if not source_role_path.is_dir():
        error_msg = f"Source role directory not found: {source_role_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    publish_dir = str(ansible_project_dir)
    is_first_module = not (ansible_project_dir / "ansible.cfg").exists()

    if is_first_module:
        logger.info(
            f"Creating new Ansible project for module '{module_name}' in {publish_dir}"
        )

        # Create directory structure
        create_directory_structure(
            base_path=publish_dir,
            structure=["collections", "inventory", "roles", "playbooks"],
        )

        # Generate ansible.cfg
        generate_ansible_cfg(f"{publish_dir}/ansible.cfg")

        # Generate collections/requirements.yml
        collections = None
        if collections_file:
            collections = load_collections_file(collections_file)
        generate_collections_requirements(
            f"{publish_dir}/collections/requirements.yml", collections=collections
        )

        # Generate inventory file
        inventory = None
        if inventory_file:
            inventory = load_inventory_file(inventory_file)
        generate_inventory_file(
            f"{publish_dir}/inventory/hosts.yml", inventory=inventory
        )
    else:
        logger.info(
            f"Appending module '{module_name}' to existing Ansible project at {publish_dir}"
        )

    # Copy role directory
    destination = f"{publish_dir}/roles/{role_name}"
    logger.info(f"Copying role {role_name} from {source_role_path}")
    copy_role_directory(
        source_role_path=str(source_role_path), destination_path=destination
    )

    # Generate wrapper playbook
    generate_playbook_yaml(
        file_path=f"{publish_dir}/playbooks/run_{role_name}.yml",
        name=f"Run {role_name}",
        role_name=role_name,
    )

    # Verify files for this role
    required_files = [
        f"{publish_dir}/roles/{role_name}",
        f"{publish_dir}/playbooks/run_{role_name}.yml",
    ]
    verify_files_exist(file_paths=required_files)

    logger.info(f"Module '{module_name}' published successfully to {publish_dir}")
    return str(ansible_project_dir.resolve())


def publish_aap(target_repo: str, target_branch: str, project_id: str) -> AAPSyncResult:
    """Connect to AAP Controller and create/update a project pointing to the given repo.

    Args:
        target_repo: Git repository URL (e.g., https://github.com/org/repo.git).
        target_branch: Git branch name.
        project_id: Migration project ID, used for AAP project naming and subdirectory reference.

    Returns:
        AAPSyncResult with sync outcome.

    Raises:
        RuntimeError: If AAP is not configured or sync fails.
    """
    logger.info(
        f"Syncing to AAP: repo={target_repo} branch={target_branch} project_id={project_id}"
    )

    result = sync_to_aap(
        repository_url=target_repo, branch=target_branch, project_id=project_id
    )

    if not result.enabled:
        raise RuntimeError(
            "AAP is not configured. Set AAP_CONTROLLER_URL and related "
            "environment variables."
        )

    if result.error:
        raise RuntimeError(f"AAP sync failed: {result.error}")

    summary_lines = result.report_summary()
    for line in summary_lines:
        logger.info(line)

    return result
