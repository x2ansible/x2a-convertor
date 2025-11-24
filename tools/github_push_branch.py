"""Tool for pushing a git branch to remote repository."""

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class GitHubPushBranchInput(BaseModel):
    """Input schema for pushing git branch."""

    repository_url: str = Field(
        description=(
            "GitHub repository URL where the branch should be pushed "
            "(e.g., 'https://github.com/user/repo')"
        )
    )
    branch: str = Field(
        description="Branch name to push to remote"
    )
    remote: str = Field(
        default="origin",
        description=(
            "Remote name (default: 'origin'). "
            "The remote should be configured with the GitHub repository URL."
        )
    )
    force: bool = Field(
        default=False,
        description=(
            "Force push the branch (overwrites remote branch). "
            "Use with caution. Default: False"
        )
    )


class GitHubPushBranchTool(BaseTool):
    """Push a git branch to remote repository.

    Pushes the specified branch to the remote repository. This should be
    used after committing changes and before creating a PR.
    """

    name: str = "github_push_branch"
    description: str = (
        "Push a git branch to the remote repository. "
        "Uses the target repository URL to locate the cloned repository "
        "(from github_commit_changes) and pushes the specified branch. "
        "Only pushes the commits created by github_commit_changes "
        "(which contain only the publish_results directory contents). "
        "Use this after committing changes and before creating a PR. "
        "Requires proper authentication configured for the remote."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = (
        GitHubPushBranchInput
    )

    def _get_repo_path(self, repository_url: str) -> Path:
        """Get a predictable path for the cloned repository."""
        # Create a hash of the repository URL for a unique directory name
        url_hash = hashlib.md5(repository_url.encode()).hexdigest()[:8]
        parsed = urlparse(repository_url)
        path_parts = [p for p in parsed.path.split('/') if p]
        if len(path_parts) >= 2:
            repo_name = path_parts[-1].replace('.git', '')
        else:
            repo_name = "repo"

        temp_base = Path(tempfile.gettempdir()) / "x2a_publish"
        return temp_base / f"{repo_name}_{url_hash}"

    def _run(
        self,
        repository_url: str = "",
        branch: str = "",
        remote: str = "origin",
        force: bool = False,
    ) -> str:
        """Push branch to remote repository.

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

        # Find the cloned repository location
        repo_path = self._get_repo_path(repository_url)

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

            # Check if branch has commits to push
            result = subprocess.run(
                [
                    "git", "rev-list", "--count",
                    f"{remote}/{branch}..{branch}"
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            commits_ahead = (
                result.stdout.strip()
                if result.returncode == 0
                else "unknown"
            )

            # Push the branch
            push_cmd = ["git", "push"]
            if force:
                push_cmd.append("--force")
            push_cmd.extend([remote, branch])

            logger.info(f"Executing: {' '.join(push_cmd)}")
            result = subprocess.run(
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
