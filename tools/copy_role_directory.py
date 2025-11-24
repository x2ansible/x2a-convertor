"""Tool for copying an entire Ansible role directory."""

import shutil
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class CopyRoleDirectoryInput(BaseModel):
    """Input schema for copying a role directory."""

    source_role_path: str = Field(
        description="Source path to the Ansible role directory"
    )
    destination_path: str = Field(
        description="Destination path where the role should be copied"
    )


class CopyRoleDirectoryTool(BaseTool):
    """Copy an entire Ansible role directory to a new location.

    Recursively copies all files and subdirectories from the source role
    to the destination, preserving the role structure.
    """

    name: str = "copy_role_directory"
    description: str = (
        "Copy an entire Ansible role directory to a new location. "
        "Recursively copies all files and subdirectories (tasks/, handlers/, "
        "templates/, etc.) preserving the complete role structure. "
        "Creates parent directories if needed."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = CopyRoleDirectoryInput

    def _run(
        self,
        source_role_path: str,
        destination_path: str,
    ) -> str:
        """Copy role directory.

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

        try:
            # Create parent directory if needed
            dest_path_obj.parent.mkdir(parents=True, exist_ok=True)

            # Remove destination if it exists
            if dest_path_obj.exists():
                if dest_path_obj.is_dir():
                    shutil.rmtree(dest_path_obj)
                else:
                    dest_path_obj.unlink()

            # Copy the entire directory tree
            shutil.copytree(
                source_path_obj,
                dest_path_obj,
                dirs_exist_ok=False,
            )

            logger.info(f"Successfully copied role to {destination_path}")
            return (
                f"Successfully copied role from {source_role_path} "
                f"to {destination_path}"
            )

        except shutil.Error as e:
            error_msg = f"ERROR: Failed to copy role directory: {e}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"ERROR: Unexpected error copying role: {e}"
            logger.error(error_msg)
            return error_msg
