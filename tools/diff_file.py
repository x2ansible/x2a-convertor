import difflib
import os
from typing import Optional

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class DiffFileInput(BaseModel):
    source_path: str = Field(description="Path to the source file")
    destination_path: str = Field(description="Path to the destination file")
    context_lines: Optional[int] = Field(
        default=3, description="Number of context lines to show around differences"
    )


class DiffFileTool(BaseTool):
    name: str = "diff_file"
    description: str = (
        "Compare two files and return a unified diff showing the differences. "
        "Useful for comparing source files with generated files to identify "
        "missing or incorrect content."
    )
    args_schema = DiffFileInput

    # pyrefly: ignore
    def _run(
        self, source_path: str, destination_path: str, context_lines: int = 3
    ) -> str:
        if not os.path.exists(source_path):
            return f"Error: Source file not found: {source_path}"

        if not os.path.exists(destination_path):
            return f"Error: Destination file not found: {destination_path}"

        try:
            with open(source_path, encoding="utf-8") as f:
                source_lines = f.readlines()
        except Exception as e:
            return f"Error reading source file {source_path}: {str(e)}"

        try:
            with open(destination_path, encoding="utf-8") as f:
                dest_lines = f.readlines()
        except Exception as e:
            return f"Error reading destination file {destination_path}: {str(e)}"

        diff = difflib.unified_diff(
            source_lines,
            dest_lines,
            fromfile=source_path,
            tofile=destination_path,
            lineterm="",
            n=context_lines,
        )

        diff_output = "\n".join(diff)

        if not diff_output:
            return "No differences found between the files."

        return diff_output
