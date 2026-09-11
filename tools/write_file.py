"""Write-to-disk tool.

Adapted from the now-deprecated
`langchain_community.tools.file_management.write.WriteFileTool`.
"""

from pathlib import Path
from typing import ClassVar

from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from tools.base_tool import X2ATool


class WriteFileInput(BaseModel):
    """Input for WriteFileTool."""

    file_path: str = Field(description="name of file")
    text: str = Field(description="text to write to file")
    append: bool = Field(
        default=False, description="Whether to append to an existing file."
    )


class WriteFileTool(X2ATool):
    """Tool that writes a file to disk."""

    name: str = "write_file"
    description: str = "Write file to disk"
    args_schema: ArgsSchema | None = WriteFileInput
    DEBUG_LOG_ARGS: ClassVar[list[str]] = ["file_path", "append"]

    # pyrefly: ignore
    def _run(self, file_path: str, text: str, append: bool = False) -> str:
        try:
            write_path = Path(file_path)
            write_path.parent.mkdir(exist_ok=True, parents=True)
            mode = "a" if append else "w"
            with write_path.open(mode, encoding="utf-8") as f:
                f.write(text)
            return f"File written successfully to {file_path}."
        except Exception as e:
            return "Error: " + str(e)
