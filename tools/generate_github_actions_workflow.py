"""Tool for generating GitHub Actions workflow files."""

from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class GenerateGitHubActionsWorkflowInput(BaseModel):
    """Input schema for generating GitHub Actions workflow."""

    file_path: str = Field(description="Output file path")
    collection_namespace: str = Field(
        default="", description="Collection namespace (optional)"
    )
    collection_name: str = Field(default="", description="Collection name (optional)")


class GenerateGitHubActionsWorkflowTool(BaseTool):
    """Generate GitHub Actions workflow for Ansible Collection Import to AAP."""

    name: str = "generate_github_actions_workflow"
    description: str = (
        "Generate GitHub Actions workflow for Ansible Collection Import to AAP. "
        "Creates a workflow file that imports collections to AAP."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = (
        GenerateGitHubActionsWorkflowInput
    )

    def _run(
        self,
        file_path: str,
        collection_namespace: str = "",
        collection_name: str = "",
    ) -> str:
        """Generate GitHub Actions workflow file."""
        logger.info(f"Generating GitHub Actions workflow at {file_path}")

        try:
            workflow_content = """name: Ansible Collection Import to AAP

on:
  push:
    branches:
      - main
      - master
  workflow_dispatch:

jobs:
  import-collection:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v3

      - name: Import Ansible Collection to AAP
        uses: ansible/ansible-automation-platform-collection-import-action@v1
        with:
          controller_url: ${{ secrets.AAP_CONTROLLER_URL }}
          controller_username: ${{ secrets.AAP_USERNAME }}
          controller_password: ${{ secrets.AAP_PASSWORD }}
"""

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
