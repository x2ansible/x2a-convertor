"""Grep tool for searching file contents by regex pattern."""

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from tools.base_tool import X2ATool


class GrepFileInput(BaseModel):
    pattern: str = Field(description="Regex pattern to search for in file contents")
    path: str = Field(default=".", description="Directory or file to search in")
    include: str | None = Field(
        default=None,
        description="Glob filter for filenames (e.g. '*.yml', '*.py')",
    )


MAX_GREP_RESULTS = 20


class GrepFileTool(X2ATool):
    name: str = "grep_file"
    description: str = (
        "Search file contents for a regex pattern. "
        "Returns matching lines in 'file:line:content' format (max 20 results). "
        "Use this to find patterns across many files at once — "
        "e.g. all tasks using the shell module, all become directives, "
        "or any hardcoded values. Supports optional filename glob filter."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = GrepFileInput

    # pyrefly: ignore
    def _run(self, pattern: str, path: str = ".", include: str | None = None) -> str:
        target = Path(path)
        if not target.exists():
            return f"Error: path not found: {path}"

        try:
            re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex pattern: {e}"

        results = self._grep(pattern, target, include)

        if not results:
            return "No matches found"

        lines = []
        for file_path, matches in sorted(results.items()):
            for line_num, content in matches:
                if len(lines) >= MAX_GREP_RESULTS:
                    lines.append(
                        f"... truncated, showing first {MAX_GREP_RESULTS} matches"
                    )
                    return "\n".join(lines)
                lines.append(f"{file_path}:{line_num}:{content}")
        return "\n".join(lines)

    def _grep(
        self, pattern: str, target: Path, include: str | None
    ) -> dict[str, list[tuple[int, str]]]:
        regex = re.compile(pattern)
        results: dict[str, list[tuple[int, str]]] = {}

        files = [target] if target.is_file() else target.rglob("*")
        for file_path in files:
            if not file_path.is_file():
                continue
            if include and not file_path.match(include):
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    results.setdefault(str(file_path), []).append((line_num, line))

        return results
