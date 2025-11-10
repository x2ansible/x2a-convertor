import re
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Safety limits to prevent excessive resource usage and token limit issues
MAX_PATTERN_LENGTH = 1000
MAX_REPLACEMENT_LENGTH = 5000
MAX_LINE_LENGTH = 50000


class SedToolInput(BaseModel):
    """Input schema for sed-like replacement tool."""

    file_path: str = Field(description="The path to the file to modify")
    line_number: int = Field(
        description="The line number to replace (1-indexed, must be specified)"
    )
    pattern: str = Field(
        description="The pattern to search for on the specified line (can be regex or literal string)"
    )
    replacement: str = Field(description="The replacement text")
    use_regex: bool = Field(
        default=False,
        description="Whether to treat pattern as regex (True) or literal string (False)",
    )


class SedTool(BaseTool):
    """Tool to perform sed-like text replacement on a specific line in a file."""

    name: str = "sed_replace"
    description: str = (
        "Performs sed-like text replacement on a specific line in a file. "
        "Line number must be specified (1-indexed). "
        "Supports both literal string and regex patterns. "
        "Returns success message or error if pattern not found on that line."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = SedToolInput

    # pyrefly: ignore
    def _run(
        self,
        file_path: str,
        line_number: int,
        pattern: str,
        replacement: str,
        use_regex: bool = False,
    ) -> str:
        """Perform sed-like replacement on specific line in file."""

        slog = logger.bind(
            phase="SedTool", file_path=file_path, line_number=line_number
        )
        slog.debug(f"SedTool called on {file_path}:{line_number}")

        # Validate input lengths to prevent excessive resource usage
        if len(pattern) > MAX_PATTERN_LENGTH:
            return f"ERROR: Pattern length ({len(pattern)}) exceeds maximum allowed length ({MAX_PATTERN_LENGTH})."

        if len(replacement) > MAX_REPLACEMENT_LENGTH:
            return f"ERROR: Replacement length ({len(replacement)}) exceeds maximum allowed length ({MAX_REPLACEMENT_LENGTH})."

        try:
            path = Path(file_path)
            if not path.exists():
                return f"ERROR: File '{file_path}' does not exist."

            # Read the file
            with path.open(encoding="utf-8") as f:
                lines = f.readlines()

            # Validate line number
            if line_number < 1 or line_number > len(lines):
                return f"ERROR: Line number {line_number} is out of range (file has {len(lines)} lines)."

            idx = line_number - 1
            original_line = lines[idx]

            # Validate line length to prevent excessive processing
            if len(original_line) > MAX_LINE_LENGTH:
                return f"ERROR: Line {line_number} length ({len(original_line)}) exceeds maximum allowed length ({MAX_LINE_LENGTH})."

            # Perform replacement
            if use_regex:
                new_line, count = re.subn(pattern, replacement, original_line)
                if count == 0:
                    return (
                        f"ERROR: Pattern '{pattern}' not found on line {line_number}."
                    )
            else:
                if pattern not in original_line:
                    return (
                        f"ERROR: Pattern '{pattern}' not found on line {line_number}."
                    )
                new_line = original_line.replace(pattern, replacement)

            lines[idx] = new_line

            # Write back to file
            with path.open("w", encoding="utf-8") as f:
                f.writelines(lines)

            slog.info(f"Replaced text on line {line_number} in {file_path}")
            return (
                f"Successfully replaced pattern on line {line_number} in {file_path}."
            )

        except Exception as e:
            slog.error(f"Failed to perform sed replacement: {e!s}")
            return f"ERROR: {e!s}"
