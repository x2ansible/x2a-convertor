import re
import shutil
import tempfile
import yaml

from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.yaml.dumper import AnsibleDumper
from ansible_risk_insight import ARIScanner, Config
from ansible_risk_insight.scanner import LoadType
from dataclasses import dataclass
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any, Optional, List, Tuple

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


class TaskfileValidator:
    """Validates Ansible taskfiles using ARI and reports errors with line numbers.

    Can be used as a context manager for automatic cleanup:
        with TaskfileValidator() as validator:
            success, message = validator.validate("tasks.yml")
    """

    def __init__(self, rules: Optional[List[str]] = None):
        """
        Initialize validator with specific rules.

        Args:
            rules: List of rule IDs to check. If None, uses default set.
        """
        if rules is None:
            rules = [
                "P001",  # Module Name Validation
                "P002",  # Module Argument Key Validation
                "P003",  # Module Argument Value Validation
                "P004",  # Variable Validation
                "R301",  # Non-FQCN Use
                "R303",  # Task Without Name
                "R306",  # Undefined Variables
                "R116",  # Insecure File Permissions
            ]

        # Use system temp directory for ARI data
        ari_tmp = Path(tempfile.gettempdir()) / "x2a-convertor" / "ari-data"
        ari_tmp.mkdir(parents=True, exist_ok=True)

        self.data_dir = ari_tmp
        self.config = Config(
            data_dir=str(ari_tmp),
            rules=rules,
        )
        self.scanner = ARIScanner(self.config, silent=True)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup temporary files."""
        self.cleanup()
        return False

    def __del__(self):
        """Destructor - cleanup on garbage collection."""
        self.cleanup()

    def cleanup(self):
        """Clean up temporary ARI data directory."""
        if hasattr(self, "data_dir") and self.data_dir and self.data_dir.exists():
            try:
                shutil.rmtree(self.data_dir)
            except Exception:
                # Ignore cleanup errors
                pass

    def validate(self, taskfile_path: str) -> Tuple[bool, str]:
        """
        Validate a taskfile and return simple pass/fail with error messages.

        Args:
            taskfile_path: Path to the YAML taskfile

        Returns:
            Tuple of (success: bool, message: str)
            - If validation passes: (True, "All checks passed")
            - If validation fails: (False, formatted error messages with line numbers)

        Example:
            >>> validator = TaskfileValidator()
            >>> success, message = validator.validate("tasks.yml")
            >>> if not success:
            ...     print(message)
            tasks.yml:3 [fqcn] Module 'apt' should use FQCN
            tasks.yml:8 [name-missing] Task is missing a name
        """
        path_obj = Path(taskfile_path)
        if not path_obj.exists():
            return False, f"ERROR: File not found: {taskfile_path}"

        # Read the taskfile
        with open(path_obj) as f:
            taskfile_yaml_content = f.read()

        # Run ARI validation
        try:
            result = self.scanner.evaluate(
                type=LoadType.TASKFILE,
                name=path_obj.name,
                taskfile_yaml=taskfile_yaml_content,
                taskfile_only=True,
            )
        except Exception as e:
            return False, f"ERROR: Validation failed: {str(e)}"

        # Get scanner data to access task objects with line numbers
        scandata = self.scanner.get_last_scandata()

        # Check for task loading errors
        if not result or not result.targets:
            return False, "ERROR: No validation results returned"

        # Get the taskfile object
        target = result.targets[0]
        taskfile_spec = None

        if target.nodes:
            node = target.nodes[0]
            if hasattr(node, "node") and hasattr(node.node, "spec"):
                taskfile_spec = node.node.spec

        # Check task loading errors first
        if taskfile_spec and hasattr(taskfile_spec, "task_loading"):
            task_loading = taskfile_spec.task_loading
            if task_loading.get("failure", 0) > 0:
                error_lines = [
                    f"ERROR: {task_loading['failure']} task(s) failed to load:"
                ]
                for error in task_loading.get("errors", []):
                    error_lines.append(f"  - {error}")
                return False, "\n".join(error_lines)

        # Get task definitions with line numbers
        tasks = scandata.root_definitions.get("definitions", {}).get("tasks", [])
        task_map = {task.key: task for task in tasks}

        # Collect errors
        errors = []

        for node in target.nodes:
            if not hasattr(node, "rules"):
                continue

            for rule_result in node.rules:
                # Check if rule matched AND found an issue
                if not rule_result.matched:
                    continue

                # Determine if there's an actual issue based on the rule type
                has_issue = False
                rule = rule_result.rule
                detail = rule_result.detail or {}

                # For R301 (FQCN), only flag if module name differs from FQCN
                if rule.rule_id == "R301" and detail:
                    if "module" in detail and "fqcn" in detail:
                        has_issue = detail["module"] != detail["fqcn"]
                elif rule_result.verdict:
                    # verdict=True usually means issue found for error-detection rules
                    has_issue = True
                elif rule_result.detail:
                    # If there's detail content, it's likely an issue
                    has_issue = True

                if not has_issue:
                    continue

                # Get task information from the node
                task_name = "unknown task"
                line_num = "?"

                # Try to get task from node spec
                node_spec = getattr(node.node, "spec", None)
                if node_spec and hasattr(node_spec, "key"):
                    task_key = node_spec.key
                    if task_key in task_map:
                        task = task_map[task_key]
                        task_name = task.name or "unnamed task"
                        if task.line_num_in_file:
                            line_num = task.line_num_in_file[0]
                    # For nodes without task_map entry, try to get info from spec directly
                    elif hasattr(node_spec, "name"):
                        task_name = node_spec.name or "unnamed task"
                        if (
                            hasattr(node_spec, "line_num_in_file")
                            and node_spec.line_num_in_file
                        ):
                            line_num = node_spec.line_num_in_file[0]

                # Format error message
                error_msg = f"{path_obj.name}:{line_num} [{rule.rule_id}] Task '{task_name}' has the following issue: '{rule.description}'"

                if detail:
                    # Add specific details if available
                    if "module" in detail and "fqcn" in detail:
                        error_msg += f" - {detail['module']} → {detail['fqcn']}"
                    elif "undefined_variables" in detail:
                        vars_list = ", ".join(detail["undefined_variables"])
                        error_msg += f" - Variables: {vars_list}"

                errors.append(error_msg)

        # Return results
        if not errors:
            return True, "All checks passed"

        error_count = len(errors)
        error_message = f"Found {error_count} issue(s):\n" + "\n".join(errors)
        return False, error_message


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
        self._validator = TaskfileValidator()

    def _is_taskfile(self, file_path: str) -> bool:
        """Check if file path indicates an Ansible taskfile.

        Returns:
            True if parent directory is 'tasks' and has .yml/.yaml extension
        """
        path = Path(file_path)
        return path.parent.name == "tasks" and path.suffix in (".yml", ".yaml")

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
        if parsed_yaml is None or not self._is_taskfile(file_path):
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

    def _format_ari_errors(self, file_path: str, validation_message: str) -> str:
        """Format ARI validation errors in XML structure for LLM consumption.

        Args:
            file_path: Path to the file that was validated
            validation_message: Error message from ARI validator

        Returns:
            XML-formatted error message with fix workflow
        """
        output = []
        output.append("<ansible_lint_errors>")
        output.append(f"<file_path>{file_path}</file_path>")
        output.append("")
        output.append("<validation_errors>")
        output.append(validation_message)
        output.append("</validation_errors>")
        output.append("")
        output.append("<fix_workflow>")
        output.append("1. Review each error with its line number and rule ID")
        output.append("2. Common fixes:")
        output.append("   - [R301] Non-FQCN → Replace 'apt' with 'ansible.builtin.apt'")
        output.append("   - [R303] Task Without Name → Add 'name:' field to task")
        output.append(
            "   - [R306] Undefined Variables → Check variable names and define them"
        )
        output.append("   - [P001] Invalid Module → Use correct module name")
        output.append(
            "   - [P002] Invalid Argument → Check module documentation for correct parameter names"
        )
        output.append("   - [R116] Insecure Permissions → Use mode: '0644' or stricter")
        output.append("3. Read the current file content to see the full context")
        output.append("4. Fix the specific issues at the reported line numbers")
        output.append("5. Call ansible_write again with the corrected yaml_content")
        output.append("6. Repeat until all validation checks pass")
        output.append("</fix_workflow>")
        output.append("</ansible_lint_errors>")

        return "\n".join(output)

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

            # Run ARI validation if this is a taskfile
            if self._is_taskfile(file_path):
                slog.debug("Running ARI validation on taskfile")
                try:
                    success, validation_message = self._validator.validate(file_path)
                    if not success:
                        slog.info(f"ARI validation failed for '{file_path}'")
                        # Format ARI errors in XML structure for LLM
                        structured_error = self._format_ari_errors(
                            file_path, validation_message
                        )
                        return f"WARNING: File was written but has validation issues:\n\n{structured_error}"
                    slog.debug("ARI validation passed")
                except Exception as e:
                    slog.warning(f"ARI validation failed with exception: {str(e)}")
                    # Don't fail the write operation if ARI validation has an error
                    return (
                        f"{result}\n\nNote: ARI validation could not be run: {str(e)}"
                    )
        else:
            slog.info(f"Failed to write Ansible yaml for '{file_path}'")

        return result
