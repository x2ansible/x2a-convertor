"""Line-scoped file reading tool.

Replaces `langchain_community.tools.file_management.read.ReadFileTool`, which
always returns the entire file. Large source files can blow past context
budgets and encourage agents to paste whole files into prompts instead of
reading the parts they need. This tool requires the model to reason about
which lines it actually needs by exposing `start_line`/`end_line`, and caps
the number of lines returned per call.
"""

from pathlib import Path

from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from tools.base_tool import X2ATool

MAX_LINES_PER_READ = 5000


class ReadFileInput(BaseModel):
    file_path: str = Field(description="Path of the file to read")
    start_line: int = Field(
        default=1,
        ge=1,
        description="First line to read (1-indexed, inclusive). Defaults to 1.",
    )
    end_line: int | None = Field(
        default=None,
        description=(
            f"Last line to read (1-indexed, inclusive). Defaults to "
            f"start_line + {MAX_LINES_PER_READ - 1}. A single call returns "
            f"at most {MAX_LINES_PER_READ} lines -- for larger files, make "
            "multiple calls with different start_line/end_line ranges."
        ),
    )


class ReadFileTool(X2ATool):
    name: str = "read_file"
    description: str = (
        "Read a range of lines from a file on disk. "
        f"Each call returns at most {MAX_LINES_PER_READ} lines -- use "
        "start_line/end_line to page through larger files instead of trying "
        "to read everything at once."
    )
    args_schema: ArgsSchema | None = ReadFileInput

    # pyrefly: ignore
    def _run(
        self,
        file_path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"Error: no such file or directory: {file_path}"
        if not path.is_file():
            return f"Error: not a file: {file_path}"

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            return f"Error: {e}"

        return self._render_range(lines, start_line, end_line, file_path)

    def _render_range(
        self,
        lines: list[str],
        start_line: int,
        end_line: int | None,
        file_path: str,
    ) -> str:
        total = len(lines)
        if start_line > total:
            return (
                f"Error: start_line {start_line} is beyond end of file "
                f"({total} lines total)"
            )

        requested_end = end_line if end_line is not None else total
        capped_end = min(requested_end, start_line + MAX_LINES_PER_READ - 1, total)

        selected = lines[start_line - 1 : capped_end]
        content = "\n".join(selected)

        if capped_end < total:
            content += (
                f"\n[... showing lines {start_line}-{capped_end} of {total} "
                f"total; call again with start_line={capped_end + 1} to "
                "continue ...]"
            )

        return content
