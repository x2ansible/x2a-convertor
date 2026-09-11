"""Directory listing tool.

Adapted from the now-deprecated
`langchain_community.tools.file_management.list_dir.ListDirectoryTool`.
"""

from pathlib import Path as PathLib
from typing import ClassVar

from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from tools.base_tool import X2ATool


class DirectoryListingInput(BaseModel):
    """Input for ListDirectoryTool."""

    dir_path: str = Field(default=".", description="Subdirectory to list.")


class ListDirectoryTool(X2ATool):
    """Tool that lists files and directories in a specified folder."""

    name: str = "list_directory"
    description: str = "List files and directories in a specified folder"
    args_schema: ArgsSchema | None = DirectoryListingInput
    DEBUG_LOG_ARGS: ClassVar[list[str]] = ["dir_path"]

    # pyrefly: ignore
    def _run(self, dir_path: str = ".") -> str:
        try:
            entries = [entry.name for entry in PathLib(dir_path).iterdir()]
            if entries:
                return "\n".join(entries)
            return f"No files found in directory {dir_path}"
        except Exception as e:
            return "Error: " + str(e)
