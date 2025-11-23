"""Tool for creating a GitHub Pull Request."""

import os
import requests
import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from urllib.parse import urlparse

logger = get_logger(__name__)


class GitHubCreatePRInput(BaseModel):
    """Input schema for creating a GitHub PR."""

    repository_url: str = Field(
        description=(
            "GitHub repository URL "
            "(e.g., 'https://github.com/user/repo')"
        )
    )
    title: str = Field(description="PR title")
    body: str = Field(description="PR description/body")
    head: str = Field(
        description="Branch name containing the changes (source branch)"
    )
    base: str = Field(
        default="main",
        description=(
            "Branch name to merge into "
            "(target branch, default: 'main')"
        ),
    )


class GitHubCreatePRTool(BaseTool):
    """Create a GitHub Pull Request.

    Creates a PR from a branch to the base branch in a GitHub repository.
    This tool can be used after pushing changes to create a PR for review.
    """

    name: str = "github_create_pr"
    description: str = (
        "Create a Pull Request (PR) in a GitHub repository. "
        "Creates a PR from the head branch to the base branch. "
        "Requires GITHUB_TOKEN environment variable for authentication."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = GitHubCreatePRInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def _run(
        self,
        repository_url: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
    ) -> str:
        """Create GitHub Pull Request.
        # ... (docstring unchanged) ...
        """
        logger.info(
            f"Creating PR from {head} to {base} in {repository_url}"
        )

        github_token = os.environ.get("GITHUB_TOKEN", "")

        if not github_token:
            return (
                "ERROR: GITHUB_TOKEN environment variable not set. "
                "Cannot create PR."
            )

        # Extract owner and repo from URL (IMPROVED SECTION)
        try:
            cleaned_url = repository_url.replace(".git", "")
            parsed_url = urlparse(cleaned_url)
            # Filter out empty strings from path split
            path_segments = [p for p in parsed_url.path.split('/') if p]

            if len(path_segments) < 2:
                return (
                    f"ERROR: Could not extract owner/repo from URL: "
                    f"{repository_url}. Expected format: /owner/repo"
                )

            owner = path_segments[-2]
            repo = path_segments[-1]

        except Exception as e:
            return (
                f"ERROR: Failed to parse repository URL {repository_url}: {e}"
            )

        # GITHUB API CALL TO CREATE PR

        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base
        }

        logger.info(f"Sending POST request to {api_url}")

        try:
            response = requests.post(
                api_url, headers=headers, data=json.dumps(payload)
            )
            response.raise_for_status()

            pr_data = response.json()
            pr_url = pr_data.get("html_url")
            pr_number = pr_data.get("number")

            success_message = (
                f"✅ Pull Request #{pr_number} created successfully! "
                f"URL: {pr_url}"
            )
            logger.info(success_message)
            return success_message

        except requests.exceptions.HTTPError as e:
            error_message = (
                f"GitHub API Error ({response.status_code}) "
                f"when creating PR: {e}"
            )
            logger.error(error_message)

            error_message += f"\nResponse Content: {response.text}"

            try:
                error_details = response.json()
                if 'message' in error_details:
                    error_message += (
                        f"\nAPI Message: {error_details['message']}"
                    )
                if 'errors' in error_details:
                    error_message += (
                        f"\nValidation Errors: {error_details['errors']}"
                    )
            except json.JSONDecodeError:
                # Fallback handled by response.text above
                pass 

            return error_message

        except requests.exceptions.RequestException as e:
            error_message = (
                f"❌ An error occurred during the request to GitHub API: {e}"
            )
            logger.error(error_message)
            return error_message