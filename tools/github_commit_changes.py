"""Tool for committing changes to git repository."""

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class GitHubCommitChangesInput(BaseModel):
    """Input schema for committing git changes."""

    repository_url: str = Field(
        description=(
            "GitHub repository URL where changes should be committed "
            "(e.g., 'https://github.com/user/repo')"
        )
    )
    directory: str = Field(
        default="publish_results",
        description=(
            "Directory path to commit (relative to current repository root). "
            "Default: 'publish_results'. "
            "This directory will be copied to the target repository."
        ),
    )
    commit_message: str = Field(description="Git commit message for the changes")
    branch: str = Field(
        description=("Branch name to commit to (will be created if it doesn't exist)")
    )


class GitHubCommitChangesTool(BaseTool):
    """Commit changes to git repository.

    Stages and commits the specified directory to the given branch.
    Creates the branch if it doesn't exist. This tool should be used
    before pushing changes and creating a PR.
    """

    name: str = "github_commit_changes"
    description: str = (
        "Commit changes to a git repository. "
        "Clones the target repository, copies ONLY the contents of the "
        "specified directory (default: 'publish_results') to it, "
        "creates/checks out the branch if needed, "
        "and commits ONLY those files. "
        "The target repository URL must be provided. "
        "This tool ONLY commits files from the specified directory - "
        "no other working directory changes included."
        "Use this before pushing changes and creating a PR."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = GitHubCommitChangesInput

    def _run(
        self,
        repository_url: str = "",
        directory: str = "publish_results",
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
            return (
                f"ERROR: Directory '{directory}' does not exist in current repository"
            )

        # Get predictable path for cloned repository
        def _get_repo_path(repo_url: str) -> Path:
            """Get a predictable path for the cloned repository."""
            url_hash = hashlib.md5(repo_url.encode()).hexdigest()[:8]
            parsed = urlparse(repo_url)
            path_parts = [p for p in parsed.path.split("/") if p]
            if len(path_parts) >= 2:
                repo_name = path_parts[-1].replace(".git", "")
            else:
                repo_name = "repo"
            temp_base = Path(tempfile.gettempdir()) / "x2a_publish"
            return temp_base / f"{repo_name}_{url_hash}"

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
            result = subprocess.run(
                ["git", "clone", repository_url, str(repo_path)],
                capture_output=True,
                text=True,
                check=True,
            )

            # Copy the directory contents to the cloned repository root
            # We want to copy the contents of publish_results/,
            # not the directory itself
            source_dir = Path(directory)

            # Copy all contents from publish_results/ to the repo root
            # Track what we copy so we only stage those items
            copied_items = []
            for item in source_dir.iterdir():
                target_item = repo_path / item.name
                if item.is_dir():
                    if target_item.exists():
                        shutil.rmtree(target_item)
                    shutil.copytree(item, target_item)
                else:
                    shutil.copy2(item, target_item)
                # Track the relative path for staging
                copied_items.append(item.name)

            logger.info(
                f"Copied contents from {source_dir} to {repo_path}: "
                f"{', '.join(copied_items)}"
            )

            # Change to the cloned repository directory
            original_cwd = Path.cwd()

            try:
                import os

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

                # Stage ONLY the files we copied from publish_results/
                # This ensures we don't accidentally include other changes
                items_str = ", ".join(copied_items)
                logger.info(f"Staging only copied items: {items_str}")
                for item_name in copied_items:
                    result = subprocess.run(
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
                    return (
                        "INFO: No changes to commit. "
                        "Files may already be committed or unchanged."
                    )

                # Commit the changes
                logger.info(f"Committing with message: {commit_message}")
                result = subprocess.run(
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
                return success_message

            finally:
                os.chdir(original_cwd)

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
