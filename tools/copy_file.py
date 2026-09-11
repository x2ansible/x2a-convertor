"""File copy tool.

Adapted from the now-deprecated
`langchain_community.tools.file_management.copy.CopyFileTool`, extended to
create parent directories if needed.
"""

import shutil
from pathlib import Path
from typing import ClassVar

from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from tools.base_tool import X2ATool


class FileCopyInput(BaseModel):
    """Input for CopyFileWithMkdirTool."""

    source_path: str = Field(description="Path of the file to copy")
    destination_path: str = Field(description="Path to save the copied file")


class CopyFileWithMkdirTool(X2ATool):
    """Tool that copies a file, creating parent directories if needed."""

    name: str = "copy_file"
    description: str = "Create a copy of a file in a specified location, creating parent directories if needed"
    args_schema: ArgsSchema | None = FileCopyInput
    DEBUG_LOG_ARGS: ClassVar[list[str]] = ["source_path", "destination_path"]

    # pyrefly: ignore
    def _run(self, source_path: str, destination_path: str) -> str:
        try:
            dest_path = Path(destination_path)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source_path, destination_path, follow_symlinks=False)
            return f"File copied successfully from {source_path} to {destination_path}."
        except Exception as e:
            return "Error: " + str(e)
