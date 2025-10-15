import shutil

from pathlib import Path
from typing import Optional

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_community.tools.file_management.copy import CopyFileTool
from langchain_community.tools.file_management.utils import (
    FileValidationError,
    INVALID_PATH_TEMPLATE,
)


class CopyFileWithMkdirTool(CopyFileTool):
    """Extended CopyFileTool that creates parent directories if needed."""

    description: str = "Create a copy of a file in a specified location, creating parent directories if needed"

    def _run(
        self,
        source_path: str,
        destination_path: str,
        run_manager: Optional[CallbackManagerForToolRun] = None,
    ) -> str:
        try:
            source_path_ = self.get_relative_path(source_path)
        except FileValidationError:
            return INVALID_PATH_TEMPLATE.format(
                arg_name="source_path", value=source_path
            )
        try:
            destination_path_ = self.get_relative_path(destination_path)
        except FileValidationError:
            return INVALID_PATH_TEMPLATE.format(
                arg_name="destination_path", value=destination_path
            )
        try:
            dest_path = Path(destination_path_)
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(source_path_, destination_path_, follow_symlinks=False)
            return f"File copied successfully from {source_path} to {destination_path}."
        except Exception as e:
            return "Error: " + str(e)
