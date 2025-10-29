"""Validated write tool that automatically routes YAML files to ansible_write."""

from typing import Any
from pathlib import Path

from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from tools.ansible_write import AnsibleWriteTool


class ValidatedWriteInput(BaseModel):
    """Input schema for validated write tool."""

    file_path: str = Field(description="The path to write the file to")
    text: str = Field(description="The text content to write to the file")
    append: bool = Field(
        default=False, description="Whether to append to the file or overwrite"
    )


class ValidatedWriteTool(BaseTool):
    """Write tool that automatically routes YAML files to ansible_write.

    This tool transparently handles file type routing:
    - .yml/.yaml files → automatically validated with ansible_write
    - .j2 templates → written directly
    - Other files → written directly

    The model can simply call write_file for any file type, and YAML files
    will automatically get validation. If validation fails, the error is
    returned to the model which can fix and retry.
    """

    name: str = "write_file"
    description: str = (
        "Write text content to a file. Creates parent directories if needed. "
        "YAML files (.yml, .yaml) are automatically validated via ansible_write. "
        "Use for .j2 templates and non-YAML files."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = ValidatedWriteInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._write_tool = WriteFileTool()
        self._ansible_write = AnsibleWriteTool()

    # pyrefly: ignore
    def _run(self, file_path: str, text: str, append: bool = False) -> str:
        """Route to appropriate tool based on file extension.

        Args:
            file_path: Path to write to
            text: Content to write
            append: Whether to append or overwrite (ignored for YAML files)

        Returns:
            Success message or validation error for YAML files
        """
        # Check file extension
        path = Path(file_path)

        # YAML files get automatic validation via ansible_write
        if path.suffix.lower() in [".yml", ".yaml"]:
            if append:
                return (
                    "ERROR: Cannot append to YAML files. "
                    "YAML files must be written atomically for validation. "
                    "Use append=False or omit the append parameter."
                )
            # Delegate to ansible_write for validation
            return self._ansible_write._run(file_path=file_path, yaml_content=text)

        # Non-YAML files use standard write
        return self._write_tool.invoke(
            {"file_path": file_path, "text": text, "append": append}
        )
