from typing import Any, Optional
from dataclasses import dataclass
import re

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
        output.append("2. Identify error type:")
        output.append("   - 'unhashable key' → Add quotes around Jinja2 variables")
        output.append(
            "   - 'mapping values not allowed' → Check for unquoted colons in strings"
        )
        output.append(
            "   - Indentation error → Align list items 2 spaces under parameter"
        )
        output.append(
            "   - 'conflicting action statements' → Split into separate tasks (one module per task)"
        )
        output.append("3. Fix the yaml_content with the specific correction")
        output.append("4. Call ansible_write again with corrected yaml_content")
        output.append("5. Repeat until you get success message")
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
        "If error returned, fix the specific YAML issue and call ansible_write AGAIN. "
        "NEVER use write_file for .yml/.yaml files."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleWriteInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._write_tool = WriteFileTool()
        self._loader = DataLoader()

    def _validate_not_empty(self, parsed_yaml: Any, yaml_content: str) -> Optional[str]:
        """Validate that YAML content is not empty.

        Returns:
            Error message if validation fails, None if validation passes.
        """
        if parsed_yaml is not None:
            return None

        stripped_content = yaml_content.strip()
        if not stripped_content:
            return None

        # Allow files with only comments and --- markers
        lines_without_comments = [
            line.strip()
            for line in stripped_content.split("\n")
            if line.strip()
            and not line.strip().startswith("#")
            and line.strip() != "---"
        ]

        if lines_without_comments:
            return "ERROR: The provided yaml content is either null or empty. The file was not written."

        return None

    def _validate_not_json(self, yaml_content: str) -> Optional[str]:
        """Validate that content is not JSON.

        Returns:
            Error message if validation fails, None if validation passes.
        """
        try:
            parsed_json = self._loader.load(data=yaml_content, json_only=True)
            if parsed_json is not None:
                return "ERROR: JSON input is not allowed, expecting yaml content instead. The file was not written."
        except Exception:
            # Expected to fail for valid YAML
            pass

        return None

    def _build_playbook_wrapper_error(
        self, file_path: str, detected_keys: list[str]
    ) -> str:
        """Build detailed error message for playbook wrapper detection."""
        return (
            f"ERROR: Task files must be FLAT lists, not playbooks.\n\n"
            f"<ansible_yaml_error>\n"
            f"<file_path>{file_path}</file_path>\n"
            f"<error_details>\n"
            f"<message>Playbook wrapper detected in task file</message>\n"
            f"<problem>Task files (.yml in tasks/ directory) must start with --- and immediately list tasks. "
            f"They cannot have playbook wrappers like 'hosts:', 'become:', or 'tasks:' keys.</problem>\n"
            f"</error_details>\n\n"
            f"<detected_structure>\n"
            f"Your YAML has: {', '.join(detected_keys)}\n"
            f"This is a PLAYBOOK structure.\n"
            f"</detected_structure>\n\n"
            f"<fix_workflow>\n"
            f"1. REMOVE the playbook wrapper (hosts, become, tasks)\n"
            f"2. Start with ---\n"
            f"3. Immediately list tasks with - name:\n"
            f"4. Each task starts at the root level (not nested under 'tasks:')\n"
            f"5. Call ansible_write again with corrected FLAT task list\n"
            f"</fix_workflow>\n\n"
            f"<correct_format>\n"
            f"---\n"
            f"- name: First task\n"
            f"  ansible.builtin.module:\n"
            f"    param: value\n"
            f"- name: Second task\n"
            f"  ansible.builtin.module:\n"
            f"    param: value\n"
            f"</correct_format>\n"
            f"</ansible_yaml_error>"
        )

    def _validate_no_playbook_wrapper(
        self, parsed_yaml: Any, file_path: str
    ) -> Optional[str]:
        """Validate that task files don't have playbook wrappers.

        Returns:
            Error message if validation fails, None if validation passes.
        """
        if parsed_yaml is None or "/tasks/" not in file_path:
            return None

        if not isinstance(parsed_yaml, list) or len(parsed_yaml) == 0:
            return None

        first_item = parsed_yaml[0]
        if not isinstance(first_item, dict):
            return None

        playbook_keys = {"hosts", "tasks", "plays", "import_playbook"}
        detected_keys = [key for key in playbook_keys if key in first_item]

        if detected_keys:
            return self._build_playbook_wrapper_error(
                file_path, list(first_item.keys())
            )

        return None

    def _format_and_write_yaml(
        self, parsed_yaml: Any, file_path: str, yaml_content: str
    ) -> str:
        """Format YAML using AnsibleDumper and write to file.

        Returns:
            Success message if write succeeds, error message if it fails.
        """
        try:
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

            return f"Successfully wrote valid Ansible YAML to {file_path}."

        except AnsibleError as e:
            structured_error = AnsibleYAMLValidationError.from_ansible_error(
                error=e, file_path=file_path, yaml_content=yaml_content
            )
            return f"ERROR: YAML validation failed. The file was not written.\n\n{structured_error.to_xml_string()}"
        except Exception as e:
            return f"ERROR: when writing Ansible YAML file, the file was not written. Fix following error and try again:\n```{str(e)}```."

    # pyrefly: ignore
    def _run(self, file_path: str, yaml_content: str) -> str:
        """Validate Ansible YAML content and write to file."""
        slog = logger.bind(phase="AnsibleWriteTool", file_path=file_path)
        slog.debug(f"AnsibleWriteTool called on {file_path}")

        yaml_content = yaml_content.replace("\\n", "\n")

        try:
            parsed_yaml = self._loader.load(data=yaml_content, json_only=False)
        except AnsibleError as e:
            slog.info(f"Failed to parse YAML for '{file_path}'")
            structured_error = AnsibleYAMLValidationError.from_ansible_error(
                error=e, file_path=file_path, yaml_content=yaml_content
            )
            slog.debug(f"Failed on YAML parsing: {structured_error.to_xml_string()}")
            return f"ERROR: YAML parsing failed. The file was not written.\n\n{structured_error.to_xml_string()}"
        except Exception as e:
            slog.debug(
                f"Failed on generic parsing error: {str(e)}\nContent: {yaml_content}"
            )
            return f"ERROR: when parsing YAML content, the file was not written. Fix following error and try again:\n```{str(e)}```."

        # Run validations
        if error := self._validate_not_empty(parsed_yaml, yaml_content):
            slog.debug("Failed on empty content")
            return error

        if error := self._validate_not_json(yaml_content):
            slog.debug("Failed on JSON instead of YAML")
            return error

        if error := self._validate_no_playbook_wrapper(parsed_yaml, file_path):
            slog.debug("Failed: detected playbook wrapper in task file")
            return error

        # Format and write the file (handles its own errors)
        result = self._format_and_write_yaml(parsed_yaml, file_path, yaml_content)

        if result.startswith("Successfully"):
            slog.info("Successfully wrote valid Ansible YAML")
        else:
            slog.info(f"Failed to write Ansible yaml for '{file_path}'")

        return result
