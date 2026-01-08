"""Deterministic tools for publishing workflow."""

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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
class AAPSyncResult:
    """Result of syncing a repository to AAP."""

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
        return lines


LOADERS: dict[str, Any] = {
    ".yaml": yaml.safe_load,
    ".yml": yaml.safe_load,
    ".json": json.load,
}


def _github_api_base() -> str:
    return get_settings().github.api_base


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


def sync_to_aap(repository_url: str, branch: str) -> AAPSyncResult:
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

    # Get project name from settings or infer from repository URL
    settings = get_settings()
    project_name = settings.aap.project_name or infer_aap_project_name(repository_url)
    scm_credential_id = settings.aap.scm_credential_id

    try:
        client = AAPClient(cfg)
        assert cfg.organization_name  # Validated by from_env()
        org_id = client.find_organization_id(name=cfg.organization_name)
        description = infer_aap_project_description(repository_url, branch)
        project = client.upsert_project(
            org_id=org_id,
            name=project_name,
            scm_url=repository_url,
            scm_branch=branch,
            description=description,
            scm_credential_id=scm_credential_id,
        )

        project_id = int(project.get("id", 0))
        if not project_id:
            return AAPSyncResult.from_error("AAP API did not return a project id")

        update = client.start_project_update(project_id=project_id)

        return AAPSyncResult(
            enabled=True,
            project_name=project_name,
            project_id=project_id,
            project_update_id=int(update["id"]) if "id" in update else None,
            project_update_status=update.get("status", ""),
        )
    except (requests.exceptions.RequestException, RuntimeError, ValueError) as e:
        return AAPSyncResult.from_error(str(e))


def _get_repo_path(repository_url: str) -> Path:
    """Generate a deterministic temporary path for cloning a repository.

    Same URL always maps to same path, enabling safe reuse. Used by
    github_commit_changes() and publish workflow.
    """
    url_hash = hashlib.md5(repository_url.encode()).hexdigest()[:8]
    parsed = urlparse(repository_url)
    path_parts = [p for p in parsed.path.split("/") if p]
    repo_name = path_parts[-1].replace(".git", "") if len(path_parts) >= 2 else "repo"

    temp_base = Path(tempfile.gettempdir()) / "x2a_publish"
    return temp_base / f"{repo_name}_{url_hash}"


def github_commit_changes(
    repository_url: str,
    directory: str,
    commit_message: str = "",
    branch: str = "",
) -> str:
    """Commit changes to git repository.

    Args:
        repository_url: Target GitHub repository URL
        directory: Directory path to commit (relative to current repo root)
        commit_message: Git commit message
        branch: Branch name to commit to

    Returns:
        Commit hash

    Raises:
        ValueError: If required parameters are missing
        FileNotFoundError: If directory does not exist
        subprocess.CalledProcessError: If git commands fail
        RuntimeError: If unexpected errors occur
    """
    if not repository_url:
        error_msg = "repository_url is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not commit_message:
        error_msg = "commit_message is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not branch:
        error_msg = "branch is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(
        f"Committing {directory} to branch {branch} in {repository_url} "
        f"with message: {commit_message}"
    )

    # Check if directory exists in current location
    dir_path = Path(directory)
    if not dir_path.exists():
        error_msg = f"Directory '{directory}' does not exist in current repository"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    repo_path = _get_repo_path(repository_url)

    # Create parent directory if needed
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing clone if it exists (to ensure clean state)
    if repo_path.exists():
        logger.info(f"Removing existing clone at {repo_path}")
        shutil.rmtree(repo_path)

    # Store original working directory before changing it
    original_cwd = Path.cwd()

    try:
        logger.info(f"Cloning target repository to {repo_path}")

        # Clone the target repository
        subprocess.run(
            ["git", "clone", repository_url, str(repo_path)],
            capture_output=True,
            text=True,
            check=True,
        )

        # Change to the cloned repository directory
        os.chdir(repo_path)

        # Fetch remote branches to check if branch exists
        subprocess.run(
            ["git", "fetch", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )

        # Check if branch exists on remote
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", branch],
            capture_output=True,
            text=True,
            check=False,
        )
        branch_exists_remote = bool(result.stdout.strip())

        # Rule 3: If branch already exists, fail immediately
        if branch_exists_remote:
            os.chdir(original_cwd)
            error_msg = (
                f"Branch '{branch}' already exists in repository "
                f"{repository_url}. Cannot create duplicate branch."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)  # noqa: TRY301

        # Branch doesn't exist, create it
        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_branch = result.stdout.strip()

        # Create new branch
        if current_branch != branch:
            logger.info(f"Creating new branch: {branch}")
            subprocess.run(
                ["git", "checkout", "-b", branch],
                check=True,
            )

        # Copy the directory contents to the cloned repository root
        source_dir = Path(directory)

        # Copy all contents from the directory to the repo root
        copied_items: list[str] = []
        for item in source_dir.iterdir():
            target_item = repo_path / item.name
            if item.is_dir():
                if target_item.exists():
                    shutil.rmtree(target_item)
                shutil.copytree(item, target_item)
            else:
                shutil.copy2(item, target_item)
            copied_items.append(item.name)

        logger.info(
            f"Copied contents from {source_dir} to {repo_path}: "
            f"{', '.join(copied_items)}"
        )

        # Stage all copied files
        items_str = ", ".join(copied_items)
        logger.info(f"Staging copied items: {items_str}")
        for item_name in copied_items:
            subprocess.run(
                ["git", "add", item_name],
                capture_output=True,
                text=True,
                check=True,
            )

        # Check if there are any changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            # No changes - this can happen if new branch has same content as default branch
            # Create empty commit to establish the branch
            logger.info(
                f"No changes detected on new branch '{branch}'. "
                "Creating empty commit to establish branch."
            )
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", commit_message],
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            # Commit the changes
            logger.info(f"Committing with message: {commit_message}")
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                capture_output=True,
                text=True,
                check=True,
            )

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit_hash = result.stdout.strip()[:7]

        logger.info(
            f"Successfully committed changes to branch '{branch}' "
            f"in {repository_url}. Commit: {commit_hash}. "
            f"Files committed: {', '.join(copied_items)}"
        )
        os.chdir(original_cwd)
        return commit_hash

    except subprocess.CalledProcessError as e:
        error_message = (
            f"Git command failed: {e}\n"
            f"Command output: {e.stderr if e.stderr else e.stdout}"
        )
        logger.error(error_message)
        os.chdir(original_cwd)
        raise

    except Exception as e:
        error_message = f"Unexpected error during git commit: {e}"
        logger.error(error_message)
        os.chdir(original_cwd)
        raise RuntimeError(error_message) from e


def github_push_branch(
    repository_url: str,
    branch: str,
    repo_path: Path | None = None,
    remote: str = "origin",
    force: bool = False,
) -> None:
    """Push a git branch to remote repository.

    Args:
        repository_url: Target GitHub repository URL
        branch: Branch name to push
        remote: Remote name (default: 'origin')
        force: Whether to force push (default: False)

    Raises:
        ValueError: If required parameters are missing
        subprocess.CalledProcessError: If git commands fail
        RuntimeError: If unexpected errors occur
    """
    if not repository_url:
        error_msg = "repository_url is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not branch:
        error_msg = "branch is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"Pushing branch '{branch}' to {repository_url}")

    # Repo path must be provided (from commit_changes)
    if repo_path is None:
        error_msg = (
            "repo_path is required. This should be set by github_commit_changes."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Check if repository exists (should have been cloned by commit tool)
    if not repo_path.exists() or not (repo_path / ".git").exists():
        error_msg = (
            f"Repository not found at {repo_path}. "
            "Please run github_commit_changes first to clone "
            "and commit the repository."
        )
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    original_cwd = Path.cwd()
    os.chdir(repo_path)

    try:
        # Check if remote exists
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            os.chdir(original_cwd)
            error_msg = (
                f"Remote '{remote}' not found. "
                f"Available remotes can be checked with 'git remote -v'"
            )
            logger.error(error_msg)
            # Must raise here: validation requires being in repo directory
            raise RuntimeError(error_msg)  # noqa: TRY301

        remote_url = result.stdout.strip()
        logger.info(f"Remote URL: {remote_url}")

        # Fetch remote branches to ensure we have latest info
        logger.info("Fetching remote branches...")
        subprocess.run(
            ["git", "fetch", remote],
            capture_output=True,
            text=True,
            check=False,
        )

        # Check if branch exists locally
        result = subprocess.run(
            ["git", "branch", "--list", branch],
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout.strip():
            os.chdir(original_cwd)
            error_msg = (
                f"Branch '{branch}' does not exist locally. "
                "Please commit changes first using github_commit_changes."
            )
            logger.error(error_msg)
            # Must raise here: validation requires being in repo directory
            raise RuntimeError(error_msg)  # noqa: TRY301

        # Check if branch exists on remote
        result = subprocess.run(
            ["git", "ls-remote", "--heads", remote, branch],
            capture_output=True,
            text=True,
            check=False,
        )
        branch_exists_remote = bool(result.stdout.strip())

        # Check if branch has commits to push
        if branch_exists_remote:
            result = subprocess.run(
                ["git", "rev-list", "--count", f"{remote}/{branch}..{branch}"],
                capture_output=True,
                text=True,
                check=False,
            )
            commits_ahead = result.stdout.strip() if result.returncode == 0 else "0"
        else:
            # New branch - count commits ahead of base branch
            result = subprocess.run(
                ["git", "rev-list", "--count", f"{remote}/main..{branch}"],
                capture_output=True,
                text=True,
                check=False,
            )
            commits_ahead = (
                result.stdout.strip() if result.returncode == 0 else "unknown"
            )
            logger.info(
                f"Branch '{branch}' is new on remote. "
                f"It has {commits_ahead} commits ahead of main."
            )

        # Push the branch (use -u for new branches to set upstream)
        push_cmd = ["git", "push"]
        if not branch_exists_remote:
            push_cmd.append("-u")
        if force:
            push_cmd.append("--force")
        push_cmd.extend([remote, branch])

        logger.info(f"Executing: {' '.join(push_cmd)}")
        subprocess.run(
            push_cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        logger.info(
            f"Successfully pushed branch '{branch}' to {repository_url}. "
            f"Remote: {remote}. Commits ahead: {commits_ahead}. "
            "Branch is now ready for PR creation"
        )

    except subprocess.CalledProcessError as e:
        error_message = (
            f"Git push failed: {e}\n"
            f"Command output: {e.stderr if e.stderr else e.stdout}"
        )

        # Provide helpful error messages for common issues
        error_lower = error_message.lower()
        if "authentication" in error_lower or "permission" in error_lower:
            error_message += (
                "\n\nTip: Ensure you have proper authentication "
                "configured. "
                "You may need to set up SSH keys or use a personal "
                "access token."
            )
        elif "not found" in error_lower:
            error_message += (
                f"\n\nTip: The remote branch '{branch}' "
                "may not exist yet. "
                "This is normal for new branches - "
                "the push should create it."
            )

        logger.error(error_message)
        os.chdir(original_cwd)
        raise

    except Exception as e:
        error_message = f"Unexpected error during git push: {e}"
        logger.error(error_message)
        os.chdir(original_cwd)
        raise RuntimeError(error_message) from e

    finally:
        os.chdir(original_cwd)


def github_get_repository(owner: str, repo_name: str) -> str | None:
    """Check if a GitHub repository exists and return its URL.

    Args:
        owner: GitHub user or organization name
        repo_name: Name of the repository

    Returns:
        Repository URL (HTTPS) if it exists, None otherwise
    """
    settings = get_settings()
    if not settings.github.token:
        return None

    github_token = settings.github.token.get_secret_value()

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {github_token}",
    }

    api_url = f"{_github_api_base()}/repos/{owner}/{repo_name}"

    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            repo_data = response.json()
            return repo_data.get("clone_url")
        return None
    except requests.exceptions.RequestException:
        return None


def github_create_repository(
    owner: str,
    repo_name: str,
    description: str = "",
    private: bool = False,
) -> str:
    """Create a new GitHub repository.

    Args:
        owner: GitHub user or organization name
        repo_name: Name for the new repository
        description: Repository description (optional)
        private: Whether the repository should be private (default: False)

    Returns:
        Repository URL (HTTPS)

    Raises:
        ValueError: If required parameters are missing or GITHUB_TOKEN not set
        requests.exceptions.HTTPError: If GitHub API operations fail
        RuntimeError: If unexpected errors occur
    """
    logger.info(f"Creating GitHub repository: {owner}/{repo_name}")

    # Check if repository already exists
    existing_repo_url = github_get_repository(owner, repo_name)
    if existing_repo_url:
        logger.info(
            f"Repository {owner}/{repo_name} already exists. "
            f"Using existing repository: {existing_repo_url}"
        )
        return existing_repo_url

    settings = get_settings()
    if not settings.github.token:
        error_msg = (
            "GITHUB_TOKEN environment variable not set. Cannot create repository."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    github_token = settings.github.token.get_secret_value()

    if not owner:
        error_msg = "owner is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not repo_name:
        error_msg = "repo_name is required"
        logger.error(error_msg)
        raise ValueError(error_msg)

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "name": repo_name,
        "description": description,
        "private": private,
        "auto_init": False,  # Don't initialize with README, we'll push our own content
    }

    # Try orgs endpoint first (for organizations)
    api_url = f"{_github_api_base()}/orgs/{owner}/repos"
    logger.info(f"Sending POST request to {api_url}")

    response: requests.Response | None = None
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        # If 404, try user/repos (for personal accounts)
        if response.status_code == 404:
            api_url = f"{_github_api_base()}/user/repos"
            logger.info(
                f"Owner not found as organization, trying user endpoint: {api_url}"
            )
            response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()

        repo_data = response.json()
        repo_url = repo_data.get("clone_url")
        repo_html_url = repo_data.get("html_url")

        if not repo_url:
            error_msg = "GitHub API did not return repository URL"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info(
            f"Repository {owner}/{repo_name} created successfully! URL: {repo_html_url}"
        )
        return repo_url

    except requests.exceptions.HTTPError as e:
        if response is None:
            error_message = f"GitHub API Error when creating repository: {e}"
        else:
            error_message = f"GitHub API Error ({response.status_code}) when creating repository: {e}"
            error_message += f"\nResponse Content: {response.text}"

            # Parse error details from JSON response
            error_details = None
            with contextlib.suppress(json.JSONDecodeError):
                error_details = response.json()

            if error_details:
                if "message" in error_details:
                    error_message += f"\nAPI Message: {error_details['message']}"
                if "errors" in error_details:
                    error_message += f"\nValidation Errors: {error_details['errors']}"

        logger.error(error_message)
        raise

    except requests.exceptions.RequestException as e:
        error_message = f"An error occurred during the request to GitHub API: {e}"
        logger.error(error_message)
        raise
