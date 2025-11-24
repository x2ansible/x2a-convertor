"""Tool for creating directory structures for GitOps publishing."""

from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CreateDirectoryStructureInput(BaseModel):
    """Input schema for creating directory structure."""

    base_path: str = Field(
        description="Base path where the directory structure should be created"
    )
    structure: list[str] = Field(
        description=(
            "List of directory paths to create. "
            "Can be relative paths like 'roles/myrole' or 'aap-config/job-templates'"
        )
    )


class CreateDirectoryStructureTool(BaseTool):
    """Create directory structure for GitOps publishing.

    Creates the necessary directories for organizing roles, playbooks,
    and AAP configuration files in a GitOps repository structure.
    """

    name: str = "create_directory_structure"
    description: str = (
        "Create a directory structure for GitOps publishing. "
        "Creates all specified directories, creating parent directories as needed. "
        "Useful for setting up the repository structure before copying files."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = (
        CreateDirectoryStructureInput
    )

    def _run(
        self,
        base_path: str,
        structure: list[str],
    ) -> str:
        """Create directory structure.

        Args:
            base_path: Base path where directories should be created
            structure: List of directory paths to create

        Returns:
            Success message with created directories or error message
        """
        logger.info(f"Creating directory structure at {base_path}")

        base_path_obj = Path(base_path)
        base_path_obj.mkdir(parents=True, exist_ok=True)

        created_dirs = []
        errors = []

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

        return (
            f"Successfully created {len(created_dirs)} directories:\n"
            + "\n".join(f"  - {d}" for d in created_dirs)
        )

