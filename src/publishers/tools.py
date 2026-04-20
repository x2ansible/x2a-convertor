"""Deterministic tools for publishing workflow."""

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
import yaml

from src.config import get_settings
from src.publishers.aap_client import (
    AAPClient,
    AAPConfig,
    infer_aap_project_description,
    infer_aap_project_name,
)
from src.publishers.template_loader import get_template
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MoleculeTemplateInfo:
    """Info about a molecule job template created on AAP."""

    name: str
    template_id: int
    role_name: str


@dataclass
class AAPSyncResult:
    """Result of syncing a repository to AAP."""

    enabled: bool = False
    project_name: str = ""
    project_id: int | None = None
    project_update_id: int | None = None
    project_update_status: str = ""
    error: str = ""
    molecule_templates: list[MoleculeTemplateInfo] = field(default_factory=list)

    @classmethod
    def disabled(cls) -> "AAPSyncResult":
        """Create a result indicating AAP is not enabled."""
        return cls(enabled=False)

    @classmethod
    def from_error(cls, error: str) -> "AAPSyncResult":
        """Create a result indicating an error occurred."""
        return cls(enabled=True, error=error)

    def report_summary(self) -> list[str]:
        """Generate summary lines for this AAP sync result."""
        lines: list[str] = []
        if not self.enabled:
            lines.append("  Disabled (AAP not configured).")
            return lines

        if self.error:
            lines.append("  Result: FAILED")
            lines.append(f"  Error: {self.error}")
            return lines

        lines.append("  Result: SUCCESS")
        if self.project_name:
            lines.append(f"  Project: {self.project_name}")
        if self.project_id is not None:
            lines.append(f"  Project ID: {self.project_id}")
        if self.project_update_id is not None:
            lines.append(f"  Sync job ID: {self.project_update_id}")
        if self.project_update_status:
            lines.append(f"  Sync job status: {self.project_update_status}")
        if self.molecule_templates:
            lines.append("  Molecule job templates (run-ready):")
            for t in self.molecule_templates:
                lines.append(f"    - {t.name} (id={t.template_id})")
        return lines


LOADERS: dict[str, Any] = {
    ".yaml": yaml.safe_load,
    ".yml": yaml.safe_load,
    ".json": json.load,
}


def _load_yaml_or_json(file_path_obj: Path) -> Any:
    with file_path_obj.open() as f:
        loader = LOADERS.get(file_path_obj.suffix.lower(), json.load)
        return loader(f)


def load_collections_file(
    file_path: str | Path,
) -> list[dict[str, str]] | None:
    """Load collections from YAML or JSON file.

    Args:
        file_path: Path to collections file (YAML or JSON)

    Returns:
        List of collection dicts with 'name' and optional 'version',
        or None if file doesn't exist

    Raises:
        TypeError: If file format is invalid (wrong type)
        ValueError: If file format is invalid (parse error)
        RuntimeError: If file cannot be read
    """
    file_path_obj = Path(file_path)
    slog = logger.bind(filename=str(file_path_obj))
    if not file_path_obj.exists():
        slog.warning(f"Collections file not found: {file_path_obj}")
        return None

    try:
        data = _load_yaml_or_json(file_path_obj)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        error_msg = f"Failed to parse collections file {file_path}: {e}"
        slog.bind(phase="load_collections_file", error_type="parse").error(error_msg)
        raise ValueError(error_msg) from e
    except Exception as e:
        error_msg = f"Failed to load collections file {file_path}: {e}"
        slog.bind(phase="load_collections_file", error_type="load").error(error_msg)
        raise RuntimeError(error_msg) from e

    # Type check after successful loading (outside try block)
    if not isinstance(data, list):
        hint = "Check that `--collections-file` points to the correct YAML/JSON file. The top-level value must be a list of collection entries."
        error_msg = (
            "Invalid collections file format. "
            f"File: {file_path_obj}. "
            f"Expected: list, got: {type(data).__name__}. "
            f"Hint: {hint}"
        )
        slog.bind(
            phase="load_collections_file",
            expected_type="list",
            actual_type=type(data).__name__,
        ).error(error_msg)
        raise TypeError(error_msg)

    slog.info(f"Loaded {len(data)} collections from {file_path_obj}")
    return data


def load_inventory_file(file_path: str | Path) -> dict | None:
    """Load inventory from YAML or JSON file.

    Args:
        file_path: Path to inventory file (YAML or JSON)

    Returns:
        Inventory structure as dict, or None if file doesn't exist

    Raises:
        TypeError: If file format is invalid (wrong type)
        ValueError: If file format is invalid (parse error)
        RuntimeError: If file cannot be read
    """
    file_path_obj = Path(file_path)
    slog = logger.bind(filename=str(file_path_obj))
    if not file_path_obj.exists():
        slog.warning(f"Inventory file not found: {file_path_obj}")
        return None

    try:
        data = _load_yaml_or_json(file_path_obj)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        error_msg = f"Failed to parse inventory file {file_path}: {e}"
        slog.bind(phase="load_inventory_file", error_type="parse").error(error_msg)
        raise ValueError(error_msg) from e
    except Exception as e:
        error_msg = f"Failed to load inventory file {file_path}: {e}"
        slog.bind(phase="load_inventory_file", error_type="load").error(error_msg)
        raise RuntimeError(error_msg) from e

    # Type check after successful loading (outside try block)
    if not isinstance(data, dict):
        hint = "Check that `--inventory-file` points to the correct YAML/JSON file. The top-level value must be a mapping (dict) in Ansible inventory format."
        error_msg = (
            "Invalid inventory file format. "
            f"File: {file_path_obj}. "
            f"Expected: dict, got: {type(data).__name__}. "
            f"Hint: {hint}"
        )
        slog.bind(
            phase="load_inventory_file",
            expected_type="dict",
            actual_type=type(data).__name__,
        ).error(error_msg)
        raise TypeError(error_msg)

    slog.info(f"Loaded inventory from {file_path_obj}")
    return data


def create_directory_structure(base_path: str, structure: list[str]) -> None:
    """Create directory structure for GitOps publishing.

    Args:
        base_path: Base path where directories should be created
        structure: List of directory paths to create

    Raises:
        OSError: If directory creation fails
    """
    logger.info(f"Creating directory structure at {base_path}")

    base_path_obj = Path(base_path)
    base_path_obj.mkdir(parents=True, exist_ok=True)

    created_dirs: list[str] = []
    errors: list[str] = []

    for dir_path in structure:
        try:
            full_path = base_path_obj / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(full_path))
            logger.debug(f"Created directory: {full_path}")
        except Exception as e:
            error_msg = f"Failed to create {dir_path}: {e}"
            errors.append(error_msg)
            logger.error(error_msg)

    if errors:
        error_details = (
            "Some directories failed to create:\n"
            + "\n".join(errors)
            + "\n\nSuccessfully created:\n"
            + "\n".join(created_dirs)
        )
        logger.error(error_details)
        raise OSError(error_details)

    logger.info(f"Successfully created {len(created_dirs)} directories")


def copy_role_directory(source_role_path: str, destination_path: str) -> None:
    """Copy an entire Ansible role directory to a new location.

    Excludes export-output.md, .checklist.json, and .ansible cache directory.

    Args:
        source_role_path: Source role directory path
        destination_path: Destination path for the role

    Raises:
        ValueError: If source path is invalid
        FileNotFoundError: If source path does not exist
        OSError: If copy operation fails
    """
    logger.info(f"Copying role from {source_role_path} to {destination_path}")

    source_path_obj = Path(source_role_path)
    dest_path_obj = Path(destination_path)

    if not source_path_obj.exists():
        error_msg = f"Source role path does not exist: {source_role_path}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    if not source_path_obj.is_dir():
        error_msg = f"Source path is not a directory: {source_role_path}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if it looks like an Ansible role
    required_dirs = ["tasks", "meta"]
    has_role_structure = any((source_path_obj / d).exists() for d in required_dirs)
    if not has_role_structure:
        logger.warning(
            f"Source path may not be a valid Ansible role "
            f"(missing tasks/ or meta/): {source_role_path}"
        )

    # Files and directories to exclude from copy
    excluded_items = {
        "export-output.md",
        ".checklist.json",
        ".ansible",  # Ansible cache directory
    }

    def ignore_files(dir_path: str, names: list[str]) -> list[str]:
        """Ignore function for copytree to exclude files/directories."""
        ignored = []
        for name in names:
            if name in excluded_items:
                ignored.append(name)
                logger.debug(f"Excluding: {name}")
        return ignored

    try:
        # Create parent directory if needed
        dest_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Remove destination if it exists
        if dest_path_obj.exists():
            if dest_path_obj.is_dir():
                shutil.rmtree(dest_path_obj)
            else:
                dest_path_obj.unlink()

        # Copy the entire directory tree, excluding specified files
        shutil.copytree(
            source_path_obj,
            dest_path_obj,
            dirs_exist_ok=False,
            ignore=ignore_files,
        )

        logger.info(f"Successfully copied role to {destination_path}")

    except shutil.Error as e:
        error_msg = f"Failed to copy role directory: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e
    except Exception as e:
        error_msg = f"Unexpected error copying role: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def generate_playbook_yaml(
    file_path: str,
    name: str,
    role_name: str,
    hosts: str = "all",
    become: bool = False,
    vars: dict[str, Any] | None = None,
) -> None:
    """Generate Ansible playbook YAML file.

    Args:
        file_path: Output file path
        name: Playbook name
        role_name: Role name to use
        hosts: Target hosts (default: "all")
        become: Use privilege escalation (default: False)
        vars: Variables for role (default: None)

    Raises:
        ValueError: If role_name is missing
        OSError: If file generation fails
    """
    logger.info(f"Generating playbook YAML: {name}")

    if vars is None:
        vars = {}

    if not role_name:
        error_msg = "role_name is required for playbook generation"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        template = get_template("playbook.yml")
        playbook_content = template.render(
            name=name,
            role_name=role_name,
            hosts=hosts,
            become=become,
            vars=vars or {},
        )

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(playbook_content)

        logger.info(f"Successfully generated playbook YAML: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate playbook YAML: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def generate_molecule_playbook(file_path: str, role_name: str) -> None:
    """Generate a wrapper playbook that runs molecule tests for a role.

    Args:
        file_path: Output file path
        role_name: Name of the role to test
    """
    logger.info(f"Generating molecule wrapper playbook for {role_name}")

    content = f"""---
- name: Run Molecule tests for {role_name}
  hosts: localhost
  connection: local
  gather_facts: false

  tasks:
    - name: Run molecule test
      ansible.builtin.command:
        cmd: molecule test -s default
        chdir: "{{{{ playbook_dir }}}}/roles/{role_name}"
      environment:
        ANSIBLE_FORCE_COLOR: "true"
      register: molecule_result

    - name: Display molecule output
      ansible.builtin.debug:
        var: molecule_result.stdout_lines
"""

    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(parents=True, exist_ok=True)
    file_path_obj.write_text(content)

    logger.info(f"Successfully generated molecule playbook: {file_path}")


def generate_molecule_instructions(file_path: str, role_names: list[str]) -> None:
    """Generate user-facing instructions for running molecule tests on AAP.

    Args:
        file_path: Output file path for the markdown instructions
        role_names: List of role names that have molecule tests
    """
    template_list = "\n".join(
        f"- **Molecule — {name}** — tests the `{name}` role" for name in role_names
    )

    template = get_template("molecule_instructions.md")
    content = template.render(template_list=template_list)

    file_path_obj = Path(file_path)
    file_path_obj.parent.mkdir(parents=True, exist_ok=True)
    file_path_obj.write_text(content)

    logger.info(f"Generated molecule instructions: {file_path}")


def generate_job_template_yaml(
    file_path: str,
    name: str,
    playbook_path: str,
    inventory: str,
    role_name: str = "",
    description: str = "",
    extra_vars: str = "",
) -> None:
    """Generate AAP job template YAML file.

    Args:
        file_path: Output file path
        name: Job template name
        playbook_path: Path to playbook file
        inventory: Inventory name or path
        role_name: Role name (optional)
        description: Description (optional)
        extra_vars: Extra vars YAML (optional)

    Raises:
        ValueError: If required parameters are missing
        OSError: If file generation fails
    """
    logger.info(f"Generating job template YAML: {name}")

    if not playbook_path:
        error_msg = "playbook_path is required for job_template generation"
        logger.error(error_msg)
        raise ValueError(error_msg)
    if not inventory:
        error_msg = "inventory is required for job_template generation"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Parse extra_vars before main try block to avoid nesting
    parsed_extra_vars = None
    if extra_vars:
        try:
            parsed_extra_vars = yaml.safe_load(extra_vars)
            # If parsing returns None or empty, use original string
            if parsed_extra_vars is None:
                parsed_extra_vars = extra_vars
        except yaml.YAMLError:
            parsed_extra_vars = extra_vars

    try:
        template = get_template("job_template.yaml")
        job_template_content = template.render(
            name=name,
            playbook_path=playbook_path,
            inventory=inventory,
            description=description or "",
            role_name=role_name or "",
            extra_vars=parsed_extra_vars,
        )

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(job_template_content)

        logger.info(f"Successfully generated job template YAML: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate job template YAML: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def generate_github_actions_workflow(file_path: str) -> None:
    """Generate GitHub Actions workflow file.

    Args:
        file_path: Output file path

    Raises:
        OSError: If file generation fails
    """
    logger.info(f"Generating GitHub Actions workflow at {file_path}")

    try:
        template = get_template("github_actions_workflow.yml")
        workflow_content = template.render()

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(workflow_content)

        logger.info(f"Successfully generated GitHub Actions workflow: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate GitHub Actions workflow: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def generate_ansible_cfg(file_path: str) -> None:
    """Generate ansible.cfg file for the project.

    Args:
        file_path: Output file path

    Raises:
        OSError: If file generation fails
    """
    logger.info(f"Generating ansible.cfg at {file_path}")

    try:
        template = get_template("ansible.cfg")
        ansible_cfg_content = template.render()

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(ansible_cfg_content)

        logger.info(f"Successfully generated ansible.cfg: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate ansible.cfg: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def generate_collections_requirements(
    file_path: str, collections: list[dict[str, str]] | None = None
) -> None:
    """Generate collections/requirements.yml file.

    Args:
        file_path: Output file path
        collections: List of collection dicts with 'name' and optional 'version'
            Example: [{"name": "community.general", "version": ">=1.0.0"}]

    Raises:
        OSError: If file generation fails
    """
    logger.info(f"Generating collections/requirements.yml at {file_path}")

    try:
        template = get_template("collections_requirements.yml")
        requirements_content = template.render(collections=collections)

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(requirements_content)

        logger.info(f"Successfully generated collections/requirements.yml: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate collections/requirements.yml: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def generate_inventory_file(file_path: str, inventory: dict | None = None) -> None:
    """Generate inventory file (hosts.yml).

    Args:
        file_path: Output file path
        inventory: Inventory structure as dict. If None, uses sample inventory.
            Example: {"all": {"children": {"servers": {"hosts": {...}}}}}

    Raises:
        OSError: If file generation fails
    """
    logger.info(f"Generating inventory file at {file_path}")

    try:
        template = get_template("inventory_hosts.yml")
        inventory_content = template.render(inventory=inventory)

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(inventory_content)

        logger.info(f"Successfully generated inventory file: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate inventory file: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def _collect_role_metadata(role_path: str) -> dict[str, Any]:
    """Read available metadata from a role directory.

    Extracts description and platforms from meta/main.yml, and default
    variable names/values from defaults/main.yml.

    Args:
        role_path: Path to the role directory.

    Returns:
        Dict with keys: name, description, defaults, platforms.
    """
    role_path_obj = Path(role_path)
    name = role_path_obj.name
    description = ""
    defaults: dict[str, Any] = {}
    platforms: list[str] = []

    # Read meta/main.yml
    meta_file = role_path_obj / "meta" / "main.yml"
    if meta_file.exists():
        try:
            meta_data = _load_yaml_or_json(meta_file)
            if isinstance(meta_data, dict):
                galaxy_info = meta_data.get("galaxy_info", {})
                if isinstance(galaxy_info, dict):
                    description = galaxy_info.get("description", "")
                    raw_platforms = galaxy_info.get("platforms", [])
                    if isinstance(raw_platforms, list):
                        for p in raw_platforms:
                            if isinstance(p, dict) and "name" in p:
                                platforms.append(p["name"])
                            elif isinstance(p, str):
                                platforms.append(p)
        except Exception:
            logger.debug(f"Could not parse meta/main.yml for role {name}")

    # Read defaults/main.yml
    defaults_file = role_path_obj / "defaults" / "main.yml"
    if defaults_file.exists():
        try:
            defaults_data = _load_yaml_or_json(defaults_file)
            if isinstance(defaults_data, dict):
                defaults = defaults_data
        except Exception:
            logger.debug(f"Could not parse defaults/main.yml for role {name}")

    return {
        "name": name,
        "description": description,
        "defaults": defaults,
        "platforms": platforms,
    }


def generate_readme(
    file_path: str,
    project_id: str,
    roles: list[dict[str, Any]],
    collections: list[dict[str, str]] | None = None,
) -> None:
    """Generate a README.md file for the Ansible project.

    Args:
        file_path: Output file path.
        project_id: Project identifier used as the title.
        roles: List of role metadata dicts (from _collect_role_metadata).
        collections: List of collection dicts with 'name' and optional 'version'.

    Raises:
        OSError: If file generation fails.
    """
    logger.info(f"Generating README.md at {file_path}")

    try:
        template = get_template("README.md")
        readme_content = template.render(
            project_id=project_id,
            roles=roles,
            collections=collections or [],
        )

        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with file_path_obj.open("w") as f:
            f.write(readme_content)

        logger.info(f"Successfully generated README.md: {file_path}")

    except Exception as e:
        error_msg = f"Failed to generate README.md: {e}"
        logger.error(error_msg)
        raise OSError(error_msg) from e


def verify_files_exist(file_paths: list[str]) -> None:
    """Verify that all required files exist.

    Args:
        file_paths: List of file/directory paths to verify

    Raises:
        FileNotFoundError: If any files are missing
    """
    logger.info(f"Verifying {len(file_paths)} files exist")

    missing_files = []
    for file_path in file_paths:
        path_obj = Path(file_path)
        if not path_obj.exists():
            missing_files.append(file_path)

    if missing_files:
        error_msg = f"{len(missing_files)} files are missing:\n" + "\n".join(
            f"  - {f}" for f in missing_files
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    logger.info("All files verified successfully")


def sync_to_aap(
    repository_url: str,
    branch: str,
    project_id: str = "",
    molecule_role_names: list[str] | None = None,
) -> AAPSyncResult:
    """Upsert an AAP Project pointing at the provided repository and trigger a sync.

    This is env-driven and optional:
    - If AAP_CONTROLLER_URL is not set, returns AAPSyncResult.disabled().
    - If enabled but misconfigured or API call fails, returns
      AAPSyncResult.from_error(...).

    Environment variables:
    - Required when enabled:
      - AAP_CONTROLLER_URL
      - AAP_ORG_NAME
      - Auth: AAP_USERNAME + AAP_PASSWORD OR AAP_OAUTH_TOKEN
    - Optional:
      - AAP_PROJECT_NAME
      - AAP_CA_BUNDLE (path to PEM/CRT CA cert for self-signed/private PKI)
      - AAP_SCM_CREDENTIAL_ID (needed for private SCM repos)
      - AAP_VERIFY_SSL (true/false)
      - AAP_TIMEOUT_S
    """
    try:
        cfg = AAPConfig.from_env()
    except ValueError as e:
        return AAPSyncResult.from_error(str(e))

    if cfg is None:
        return AAPSyncResult.disabled()

    # Get project name from settings or use project_id or infer from repository URL
    settings = get_settings()
    project_name = (
        settings.aap.project_name
        or project_id
        or infer_aap_project_name(repository_url)
    )
    scm_credential_id = settings.aap.scm_credential_id

    try:
        client = AAPClient(cfg)
        assert cfg.organization_name  # Validated by from_env()
        org_id = client.find_organization_id(name=cfg.organization_name)
        description = infer_aap_project_description(
            repository_url, branch, project_id=project_id
        )
        project = client.upsert_project(
            org_id=org_id,
            name=project_name,
            scm_url=repository_url,
            scm_branch=branch,
            description=description,
            scm_credential_id=scm_credential_id,
        )

        aap_project_id = int(project.get("id", 0))
        if not aap_project_id:
            return AAPSyncResult.from_error("AAP API did not return a project id")

        update = client.start_project_update(project_id=aap_project_id)
        update_id = int(update["id"]) if "id" in update else None

        # Register molecule EE, inventory, and create run-ready job templates
        molecule_templates: list[MoleculeTemplateInfo] = []
        molecule_ee_image = settings.aap.molecule_ee_image
        if molecule_ee_image and project_id:
            # Wait for project sync to complete — AAP validates playbook
            # paths against the synced repo, so templates can't be created
            # until the sync finishes.
            if update_id:
                _wait_for_project_sync(client, update_id)
            try:
                molecule_templates = _setup_molecule_on_aap(
                    client=client,
                    org_id=org_id,
                    aap_project_id=aap_project_id,
                    project_id=project_id,
                    molecule_ee_image=molecule_ee_image,
                    inventory_name=settings.aap.inventory_name,
                    role_names=molecule_role_names,
                )
            except Exception as e:
                logger.warning(f"Molecule AAP setup failed (non-fatal): {e}")

        return AAPSyncResult(
            enabled=True,
            project_name=project_name,
            molecule_templates=molecule_templates,
            project_id=aap_project_id,
            project_update_id=update_id,
            project_update_status=update.get("status", ""),
        )
    except (requests.exceptions.RequestException, RuntimeError, ValueError) as e:
        return AAPSyncResult.from_error(str(e))


def _wait_for_project_sync(
    client: "AAPClient",
    update_id: int,
    timeout_s: int = 120,
    poll_interval_s: int = 5,
) -> None:
    """Poll AAP until a project update job finishes.

    AAP validates playbook paths against the synced repo content, so
    job templates cannot be created until the sync completes.

    Raises:
        RuntimeError: If sync fails or times out.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = client.get_project_update(update_id=update_id)
        status = data.get("status", "")
        if status == "successful":
            logger.info(f"Project sync completed (update_id={update_id})")
            return
        if status in ("failed", "error", "canceled"):
            raise RuntimeError(
                f"Project sync {status} (update_id={update_id}): "
                f"{data.get('result_traceback', 'no details')}"
            )
        logger.debug(f"Project sync status: {status}, waiting...")
        time.sleep(poll_interval_s)
    raise RuntimeError(
        f"Project sync timed out after {timeout_s}s (update_id={update_id})"
    )


def _setup_molecule_on_aap(
    client: "AAPClient",
    org_id: int,
    aap_project_id: int,
    project_id: str,
    molecule_ee_image: str,
    inventory_name: str = "Molecule Local",
    role_names: list[str] | None = None,
) -> list[MoleculeTemplateInfo]:
    """Register molecule EE, ensure inventory, and create run-ready job templates.

    Creates fully configured job templates on AAP (with EE and inventory pre-set)
    for each role that has molecule tests.

    Args:
        client: Authenticated AAP client
        org_id: AAP organization ID
        aap_project_id: AAP project ID
        project_id: Migration project ID (used to construct playbook paths)
        molecule_ee_image: Container image URL for the molecule EE
        inventory_name: Name of the inventory to find or create
        role_names: Role names with molecule tests. If not provided, scans
            the ansible-project directory for molecule_*.yml playbooks.

    Returns:
        List of created/updated molecule job template info
    """
    templates: list[MoleculeTemplateInfo] = []

    # Determine which roles have molecule tests
    if role_names:
        discovered_roles = sorted(role_names)
    else:
        # Fall back to filesystem scan
        ansible_project = Path(project_id) / "ansible-project"
        if not ansible_project.is_dir():
            return templates
        discovered_roles = sorted(
            p.stem.removeprefix("molecule_")
            for p in ansible_project.glob("molecule_*.yml")
        )

    if not discovered_roles:
        return templates

    # Register molecule EE
    ee = client.upsert_execution_environment(
        name="Molecule EE",
        image=molecule_ee_image,
        org_id=org_id,
        pull="always",
    )
    ee_id = int(ee["id"])
    logger.info(f"Registered Molecule EE (id={ee_id}, image={molecule_ee_image})")

    # Find or create localhost inventory
    inventory = client.find_or_create_inventory(
        org_id=org_id,
        name=inventory_name,
    )
    inventory_id = int(inventory["id"])
    logger.info(f"Using inventory '{inventory_name}' (id={inventory_id})")

    # Create fully configured job templates for each molecule role
    for role_name in discovered_roles:
        # Playbook path relative to repo root
        relative_playbook = (
            f"{project_id}/ansible-project/molecule_{role_name}.yml"
        )
        template_name = f"Molecule — {role_name}"

        jt = client.upsert_job_template(
            org_id=org_id,
            name=template_name,
            project_id=aap_project_id,
            playbook=relative_playbook,
            execution_environment_id=ee_id,
            inventory_id=inventory_id,
        )
        jt_id = int(jt.get("id", 0))
        templates.append(
            MoleculeTemplateInfo(
                name=template_name,
                template_id=jt_id,
                role_name=role_name,
            )
        )
        logger.info(f"Created run-ready job template '{template_name}' (id={jt_id})")

    return templates
