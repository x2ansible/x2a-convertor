"""Deterministic tools for publishing workflow."""

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import yaml

from src.publishers.template_loader import get_template
from src.utils.logging import get_logger

logger = get_logger(__name__)


def create_directory_structure(base_path: str, structure: list[str]) -> str:
    """Create directory structure for GitOps publishing.

    Args:
        base_path: Base path where directories should be created
        structure: List of directory paths to create

    Returns:
        Success message or error message
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
        return (
            "ERROR: Some directories failed to create:\n"
            + "\n".join(errors)
            + "\n\nSuccessfully created:\n"
            + "\n".join(created_dirs)
        )

    return f"Successfully created {len(created_dirs)} directories:\n" + "\n".join(
        f"  - {d}" for d in created_dirs
    )


def copy_role_directory(source_role_path: str, destination_path: str) -> str:
    """Copy an entire Ansible role directory to a new location.

    Excludes export-output.md, .checklist.json, and .ansible cache directory.

    Args:
        source_role_path: Source role directory path
        destination_path: Destination path for the role

    Returns:
        Success or error message
    """
    logger.info(f"Copying role from {source_role_path} to {destination_path}")

    source_path_obj = Path(source_role_path)
    dest_path_obj = Path(destination_path)

    if not source_path_obj.exists():
        return f"ERROR: Source role path does not exist: {source_role_path}"

    if not source_path_obj.is_dir():
        return f"ERROR: Source path is not a directory: {source_role_path}"

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
        return f"Successfully copied role from {source_role_path} to {destination_path}"

    except shutil.Error as e:
        error_msg = f"ERROR: Failed to copy role directory: {e}"
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"ERROR: Unexpected error copying role: {e}"
        logger.error(error_msg)
        return error_msg


def generate_playbook_yaml(
    file_path: str,
    name: str,
    role_name: str,
    hosts: str = "all",
    become: bool = False,
    vars: dict[str, Any] | None = None,
) -> str:
    """Generate Ansible playbook YAML file.

    Args:
        file_path: Output file path
        name: Playbook name
        role_name: Role name to use
        hosts: Target hosts (default: "all")
        become: Use privilege escalation (default: False)
        vars: Variables for role (default: None)

    Returns:
        Success or error message
    """
    logger.info(f"Generating playbook YAML: {name}")

    if vars is None:
        vars = {}

    if not role_name:
        return "ERROR: role_name is required for playbook generation"

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
        return (
            f"Successfully generated playbook YAML at {file_path}\n"
            f"Playbook: {name}\n"
            f"Role: {role_name}\n"
            f"Hosts: {hosts}"
        )

    except Exception as e:
        error_msg = f"ERROR: Failed to generate playbook YAML: {e}"
        logger.error(error_msg)
        return error_msg


def generate_job_template_yaml(
    file_path: str,
    name: str,
    playbook_path: str,
    inventory: str,
    role_name: str = "",
    description: str = "",
    extra_vars: str = "",
) -> str:
    """Generate AAP job template YAML file.

    Args:
        file_path: Output file path
        name: Job template name
        playbook_path: Path to playbook file
        inventory: Inventory name or path
        role_name: Role name (optional)
        description: Description (optional)
        extra_vars: Extra vars YAML (optional)

    Returns:
        Success or error message
    """
    logger.info(f"Generating job template YAML: {name}")

    if not playbook_path:
        return "ERROR: playbook_path is required for job_template generation"
    if not inventory:
        return "ERROR: inventory is required for job_template generation"

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
        return (
            f"Successfully generated job template YAML at {file_path}\n"
            f"Job template: {name}\n"
            f"Playbook: {playbook_path}\n"
            f"Inventory: {inventory}"
        )

    except Exception as e:
        error_msg = f"ERROR: Failed to generate job template YAML: {e}"
        logger.error(error_msg)
        return error_msg


def generate_github_actions_workflow(file_path: str) -> str:
    """Generate GitHub Actions workflow file.

    Args:
        file_path: Output file path

    Returns:
        Success or error message
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
        return f"Successfully generated GitHub Actions workflow at {file_path}"

    except Exception as e:
        error_msg = f"ERROR: Failed to generate GitHub Actions workflow: {e}"
        logger.error(error_msg)
        return error_msg


def verify_files_exist(file_paths: list[str]) -> str:
    """Verify that all required files exist.

    Args:
        file_paths: List of file/directory paths to verify

    Returns:
        Success or error message
    """
    logger.info(f"Verifying {len(file_paths)} files exist")

    missing_files = []
    for file_path in file_paths:
        path_obj = Path(file_path)
        if not path_obj.exists():
            missing_files.append(file_path)

    if missing_files:
        error_msg = f"ERROR: {len(missing_files)} files are missing:\n" + "\n".join(
            f"  - {f}" for f in missing_files
        )
        logger.error(error_msg)
        return error_msg

    logger.info("All files verified successfully")
    return f"Successfully verified {len(file_paths)} files exist"


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
        Success message or error message
    """
    if not repository_url:
        return "ERROR: repository_url is required"

    if not commit_message:
        return "ERROR: commit_message is required"

    if not branch:
        return "ERROR: branch is required"

    logger.info(
        f"Committing {directory} to branch {branch} in {repository_url} "
        f"with message: {commit_message}"
    )

    # Check if directory exists in current location
    dir_path = Path(directory)
    if not dir_path.exists():
        return f"ERROR: Directory '{directory}' does not exist in current repository"

    repo_path = _get_repo_path(repository_url)

    # Create parent directory if needed
    repo_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing clone if it exists (to ensure clean state)
    if repo_path.exists():
        logger.info(f"Removing existing clone at {repo_path}")
        shutil.rmtree(repo_path)

    try:
        logger.info(f"Cloning target repository to {repo_path}")

        # Clone the target repository
        subprocess.run(
            ["git", "clone", repository_url, str(repo_path)],
            capture_output=True,
            text=True,
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

        # Change to the cloned repository directory
        original_cwd = Path.cwd()
        os.chdir(repo_path)

        # Get current branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_branch = result.stdout.strip()

        # Create or checkout branch if needed
        if current_branch != branch:
            logger.info(f"Switching to branch: {branch}")
            # Check if branch exists
            result = subprocess.run(
                ["git", "branch", "--list", branch],
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout.strip():
                # Branch exists, checkout
                subprocess.run(
                    ["git", "checkout", branch],
                    check=True,
                )
            else:
                # Branch doesn't exist, create and checkout
                subprocess.run(
                    ["git", "checkout", "-b", branch],
                    check=True,
                )

        # Stage ONLY the files we copied from the directory
        items_str = ", ".join(copied_items)
        logger.info(f"Staging only copied items: {items_str}")
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
            os.chdir(original_cwd)
            return (
                "ERROR: No changes to commit. "
                "Files may already be committed or unchanged. "
                "Cannot create PR without new commits."
            )

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

        success_message = (
            f"✅ Successfully committed changes to branch '{branch}' "
            f"in {repository_url}\n"
            f"Commit: {commit_hash}\n"
            f"Message: {commit_message}\n"
            f"Files committed: {', '.join(copied_items)}\n"
            f"Repository location: {repo_path}\n"
            f"Note: Only files from '{directory}' were committed, "
            "no other working directory changes included"
        )
        logger.info(success_message)
        os.chdir(original_cwd)
        return success_message

    except subprocess.CalledProcessError as e:
        error_message = (
            f"ERROR: Git command failed: {e}\n"
            f"Command output: {e.stderr if e.stderr else e.stdout}"
        )
        logger.error(error_message)
        return error_message

    except Exception as e:
        error_message = f"ERROR: Unexpected error during git commit: {e}"
        logger.error(error_message)
        return error_message


def github_push_branch(
    repository_url: str,
    branch: str,
    repo_path: Path | None = None,
    remote: str = "origin",
    force: bool = False,
) -> str:
    """Push a git branch to remote repository.

    Args:
        repository_url: Target GitHub repository URL
        branch: Branch name to push
        remote: Remote name (default: 'origin')
        force: Whether to force push (default: False)

    Returns:
        Success message or error message
    """
    if not repository_url:
        return "ERROR: repository_url is required"

    if not branch:
        return "ERROR: branch is required"

    logger.info(f"Pushing branch '{branch}' to {repository_url}")

    # Repo path must be provided (from commit_changes)
    if repo_path is None:
        return (
            "ERROR: repo_path is required. This should be set by github_commit_changes."
        )

    # Check if repository exists (should have been cloned by commit tool)
    if not repo_path.exists() or not (repo_path / ".git").exists():
        return (
            f"ERROR: Repository not found at {repo_path}. "
            "Please run github_commit_changes first to clone "
            "and commit the repository."
        )

    original_cwd = Path.cwd()
    try:
        os.chdir(repo_path)

        # Check if remote exists
        result = subprocess.run(
            ["git", "remote", "get-url", remote],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return (
                f"ERROR: Remote '{remote}' not found. "
                f"Available remotes can be checked with 'git remote -v'"
            )

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
            return (
                f"ERROR: Branch '{branch}' does not exist locally. "
                "Please commit changes first using github_commit_changes."
            )

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

        success_message = (
            f"✅ Successfully pushed branch '{branch}' "
            f"to {repository_url}\n"
            f"Remote: {remote}\n"
            f"Commits ahead: {commits_ahead}\n"
            "Branch is now ready for PR creation"
        )
        logger.info(success_message)
        return success_message

    except subprocess.CalledProcessError as e:
        error_message = (
            f"ERROR: Git push failed: {e}\n"
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
        return error_message

    except Exception as e:
        error_message = f"ERROR: Unexpected error during git push: {e}"
        logger.error(error_message)
        return error_message

    finally:
        os.chdir(original_cwd)


def github_create_pr(
    repository_url: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> str:
    """Create a GitHub Pull Request.

    Args:
        repository_url: GitHub repository URL
        title: PR title
        body: PR description/body
        head: Branch name containing the changes (source branch)
        base: Branch name to merge into (target branch, default: 'main')

    Returns:
        Success message with PR URL or error message
    """
    logger.info(f"Creating PR from {head} to {base} in {repository_url}")

    github_token = os.environ.get("GITHUB_TOKEN", "")

    if not github_token:
        return "ERROR: GITHUB_TOKEN environment variable not set. Cannot create PR."

    # Extract owner and repo from URL
    try:
        cleaned_url = repository_url.replace(".git", "")
        parsed_url = urlparse(cleaned_url)
        path_segments = [p for p in parsed_url.path.split("/") if p]

        if len(path_segments) < 2:
            return (
                f"ERROR: Could not extract owner/repo from URL: "
                f"{repository_url}. Expected format: /owner/repo"
            )

        owner = path_segments[-2]
        repo = path_segments[-1]

    except Exception as e:
        return f"ERROR: Failed to parse repository URL {repository_url}: {e}"

    # Verify branches are different
    if head == base:
        return (
            f"ERROR: Cannot create PR: head branch '{head}' "
            f"cannot be the same as base branch '{base}'. "
            f"Please use a feature branch for the PR."
        )

    # Verify that head branch has commits ahead of base using GitHub API
    compare_url = f"https://api.github.com/repos/{owner}/{repo}/compare/{base}...{head}"
    compare_headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {github_token}",
    }

    try:
        logger.info(f"Checking commits between {base} and {head}...")
        compare_response = requests.get(compare_url, headers=compare_headers)
        compare_response.raise_for_status()
        compare_data = compare_response.json()

        commits_ahead = compare_data.get("ahead_by", 0)
        commits_behind = compare_data.get("behind_by", 0)

        logger.info(
            f"Branch {head} is {commits_ahead} commits ahead "
            f"and {commits_behind} commits behind {base}"
        )

        if commits_ahead == 0:
            return (
                f"ERROR: Cannot create PR: Branch '{head}' has no commits "
                f"ahead of '{base}'. The branches are at the same commit. "
                f"This usually means the files are already in the base branch."
            )

    except requests.exceptions.HTTPError as e:
        # If comparison fails, log but continue (might be a new branch)
        logger.warning(
            f"Could not compare branches {base} and {head}: {e}. "
            "Continuing with PR creation..."
        )
    except Exception as e:
        logger.warning(
            f"Error checking branch comparison: {e}. Continuing with PR creation..."
        )

    # GitHub API call to create PR
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
    }

    payload = {"title": title, "body": body, "head": head, "base": base}

    logger.info(f"Sending POST request to {api_url}")

    response: requests.Response | None = None
    try:
        response = requests.post(api_url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()

        pr_data = response.json()
        pr_url = pr_data.get("html_url")
        pr_number = pr_data.get("number")

        success_message = (
            f"✅ Pull Request #{pr_number} created successfully! URL: {pr_url}"
        )
        logger.info(success_message)
        return success_message

    except requests.exceptions.HTTPError as e:
        if response is None:
            error_message = f"ERROR: GitHub API Error when creating PR: {e}"
        else:
            error_message = (
                f"ERROR: GitHub API Error ({response.status_code}) "
                f"when creating PR: {e}"
            )
            error_message += f"\nResponse Content: {response.text}"

            # Parse error details from JSON response (inline, no nesting)
            error_details = None
            with contextlib.suppress(json.JSONDecodeError):
                error_details = response.json()

            if error_details:
                if "message" in error_details:
                    error_message += f"\nAPI Message: {error_details['message']}"
                if "errors" in error_details:
                    error_message += f"\nValidation Errors: {error_details['errors']}"

        logger.error(error_message)
        return error_message

    except requests.exceptions.RequestException as e:
        error_message = (
            f"ERROR: An error occurred during the request to GitHub API: {e}"
        )
        logger.error(error_message)
        return error_message
