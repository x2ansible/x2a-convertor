"""Recursive file search tool.

Adapted from the now-deprecated
`langchain_community.tools.file_management.file_search.FileSearchTool`.
"""

import fnmatch
import os
from pathlib import Path as PathLib
from typing import ClassVar

from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from tools.base_tool import X2ATool


class FileSearchInput(BaseModel):
    """Input for FileSearchTool."""

    dir_path: str = Field(
        default=".",
        description="Subdirectory to search in.",
    )
    pattern: str = Field(
        description="Unix shell regex, where * matches everything.",
    )


class FileSearchTool(X2ATool):
    """Tool that searches for files in a subdirectory that match a regex pattern."""

    name: str = "file_search"
    description: str = (
        "Recursively search for files in a subdirectory that match the regex pattern"
    )
    args_schema: ArgsSchema | None = FileSearchInput
    DEBUG_LOG_ARGS: ClassVar[list[str]] = ["dir_path", "pattern"]

    # pyrefly: ignore
    def _run(self, pattern: str, dir_path: str = ".") -> str:
        matches = []
        try:
            for root, _, filenames in os.walk(dir_path):
                for filename in fnmatch.filter(filenames, pattern):
                    absolute_path = PathLib(root) / filename
                    relative_path = os.path.relpath(absolute_path, dir_path)
                    matches.append(relative_path)
            if matches:
                return "\n".join(matches)
            return f"No files found for pattern {pattern} in directory {dir_path}"
        except Exception as e:
            return "Error: " + str(e)
