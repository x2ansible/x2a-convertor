from typing import Any, Optional
from dataclasses import dataclass

import yaml
from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.yaml.dumper import AnsibleDumper
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AnsibleYAMLValidationError:
    """Structured error information for Ansible YAML validation failures.

    This class extracts detailed error information from AnsibleError exceptions
    and formats it in an XML structure that's easy for LLMs to parse and fix.
    """

    file_path: str
    error_message: str
    yaml_content: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    problem: Optional[str] = None
    problematic_line: Optional[str] = None

    @classmethod
    def from_ansible_error(
        cls, error: AnsibleError, file_path: str, yaml_content: str
    ) -> "AnsibleYAMLValidationError":
        """Extract detailed information from an AnsibleError exception.

        Args:
            error: The AnsibleError exception caught during YAML parsing
            file_path: Path to the file being validated
            yaml_content: The YAML content that failed validation

        Returns:
            AnsibleYAMLValidationError with extracted details
        """
        error_message = str(error)
        line_number = None
        column_number = None
        problem = None
        problematic_line = None

        # Check if we have detailed error info in the exception chain
        if error.__cause__ and hasattr(error.__cause__, "problem_mark"):
            mark = error.__cause__.problem_mark
            line_number = mark.line + 1  # Convert from 0-indexed to 1-indexed
            column_number = mark.column + 1

            if hasattr(error.__cause__, "problem"):
                problem = error.__cause__.problem

            # Extract the problematic line from the content
            lines = yaml_content.split("\n")
            if 0 < line_number <= len(lines):
                problematic_line = lines[line_number - 1]

        return cls(
            file_path=file_path,
            error_message=error_message,
            yaml_content=yaml_content,
            line_number=line_number,
            column_number=column_number,
            problem=problem,
            problematic_line=problematic_line,
        )

    def to_xml_string(self) -> str:
        """Format the error as an XML structure for LLM consumption.

        Returns:
            XML-formatted error message with all available details
        """
        output = []

        output.append("<ansible_yaml_error>")
        output.append(f"<file_path>{self.file_path}</file_path>")
        output.append("")
        output.append("<error_details>")
        output.append(f"<message>{self.error_message}</message>")

        if self.line_number is not None:
            output.append(f"<line_number>{self.line_number}</line_number>")

        if self.column_number is not None:
            output.append(f"<column_number>{self.column_number}</column_number>")

        if self.problem:
            output.append(f"<problem>{self.problem}</problem>")

        output.append("</error_details>")

        # Show the problematic line with pointer
        if self.problematic_line is not None and self.column_number is not None:
            output.append("")
            output.append("<problematic_location>")
            output.append(f"<line_number>{self.line_number}</line_number>")
            output.append(f"<line_content>{self.problematic_line}</line_content>")
            pointer = " " * (self.column_number - 1) + "^"
            output.append(f"<column_pointer>{pointer}</column_pointer>")
            output.append("</problematic_location>")

        # Include the full YAML content for context
        output.append("")
        output.append("<yaml_content>")
        output.append(self.yaml_content)
        output.append("</yaml_content>")

        output.append("")
        output.append("<fix_workflow>")
        output.append("1. Read the error message and problematic line above")
        output.append("2. Fix the yaml content")
        output.append("3. Call ansible_write again with the corrected yaml_content")
        output.append("4. Repeat until you get success message")
        output.append("</fix_workflow>")

        output.append("</ansible_yaml_error>")

        return "\n".join(output)

    def __str__(self) -> str:
        """Default string representation uses XML format for LLM compatibility."""
        return self.to_xml_string()


class AnsibleWriteInput(BaseModel):
    """Input schema for Ansible YAML write tool."""

    file_path: str = Field(description="The path to write the Ansible YAML file to")
    yaml_content: str = Field(
        description="YAML-formatted string (NOT JSON). Example: '---\\n- name: Task\\n  ansible.builtin.apt:\\n    name: nginx'"
    )


class AnsibleWriteTool(BaseTool):
    """Validates and writes Ansible YAML files with Jinja2 support."""

    name: str = "ansible_write"
    description: str = (
        "Validates and writes Ansible YAML files (.yml, .yaml). "
        "yaml_content must be YAML string, NOT JSON. "
        "Returns XML error with line numbers if validation fails. "
        "NEVER use write_file for .yml/.yaml files."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleWriteInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._write_tool = WriteFileTool()
        self._loader = DataLoader()

    # pyrefly: ignore
    def _run(self, file_path: str, yaml_content: str) -> str:
        """Validate Ansible YAML content and write to file."""

        slog = logger.bind(phase="AnsibleWriteTool", file_path=file_path)
        slog.debug(f"AnsibleWriteTool called on {file_path}")

        try:
            parsed_yaml = self._loader.load(data=yaml_content, json_only=False)

            # Allow empty/null for things like empty vars files with just comments
            # Check if content is truly empty (not just whitespace/comments)
            stripped_content = yaml_content.strip()
            if parsed_yaml is None and stripped_content:
                # If it starts with --- and only has comments, allow it
                lines_without_comments = [
                    line.strip()
                    for line in stripped_content.split("\n")
                    if line.strip()
                    and not line.strip().startswith("#")
                    and line.strip() != "---"
                ]
                if lines_without_comments:
                    slog.debug("Failed on empty content")
                    return "ERROR: The provided yaml content is either null or empty. The file was not written."

            try:
                # Since YAML can be valid JSON, we need to check if the input is JSON and not allow it
                parsed_json = self._loader.load(data=yaml_content, json_only=True)
                if parsed_json is not None:
                    slog.debug("Failed on JSON instead of YAML")
                    return "ERROR: JSON input is not allowed, expecting yaml content instead. The file was not written."
            except Exception:
                # expected to fail
                pass

            # Re-format YAML using AnsibleDumper to ensure proper formatting
            # This will fix common formatting issues while preserving Jinja2 templates
            if parsed_yaml is not None:
                formatted_yaml = yaml.dump(
                    parsed_yaml,
                    Dumper=AnsibleDumper,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    width=160,
                )
                self._write_tool.invoke(
                    {"file_path": file_path, "text": formatted_yaml}
                )
            else:
                # For empty/comment-only files, write original content
                self._write_tool.invoke({"file_path": file_path, "text": yaml_content})

            slog.info("Successfully wrote valid Ansible YAML")
            return f"Successfully wrote valid Ansible YAML to {file_path}."
        except AnsibleError as e:
            slog.info(f"Failed to write Ansible yaml for '{file_path}'")
            # Create structured error with line numbers and hints for the LLM
            structured_error = AnsibleYAMLValidationError.from_ansible_error(
                error=e, file_path=file_path, yaml_content=yaml_content
            )

            slog.debug(f"Failed on YAML validation: {structured_error.to_xml_string()}")

            # Return XML-formatted error for LLM to parse and fix
            return f"ERROR: YAML validation failed. The file was not written.\n\n{structured_error.to_xml_string()}"
        except Exception as e:
            slog.debug(f"Failed on generic error: {str(e)}\nContent: {yaml_content}")
            return f"ERROR: when writing Ansible YAML file, the file was not written. Fix following error and try again:\n```{str(e)}```."
