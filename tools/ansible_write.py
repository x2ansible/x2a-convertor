import contextlib
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, ClassVar

import yaml
from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.yaml.dumper import AnsibleDumper

# Monkey-patch pkg_resources to use modern importlib.metadata
# This fixes the pkg_resources deprecation warning from ansible_risk_insight
if "pkg_resources" not in sys.modules:

    def _require(package_name):
        class _Ver:
            version = version(package_name)

        return [_Ver()]

    # Create a proper module object using the type of an existing module
    ModuleType = type(sys)
    fake_pkg_resources = ModuleType("pkg_resources")
    fake_pkg_resources.require = _require
    sys.modules["pkg_resources"] = fake_pkg_resources

from ansible_risk_insight import ARIScanner, Config
from ansible_risk_insight.scanner import LoadType
from jinja2 import Environment, FileSystemLoader
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Setup Jinja2 environment
TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=False)


# ==============================================================================
# Configuration & Constants
# ==============================================================================


class TemplateNames:
    """Central repository for template file names."""

    YAML_VALIDATION_ERROR = "yaml_validation_error.xml.j2"
    PLAYBOOK_WRAPPER_ERROR = "playbook_wrapper_error.xml.j2"
    ARI_ERRORS = "ari_errors.xml.j2"
    MULTIPLE_ERRORS = "multiple_errors.xml.j2"


class AnsibleValidationRules:
    """Configuration for Ansible validation rules and their descriptions."""

    # Default rule IDs to validate
    DEFAULT_RULES: ClassVar[list[str]] = [
        "P001",  # Module Name Validation
        "P002",  # Module Argument Key Validation
        "P003",  # Module Argument Value Validation
        "P004",  # Variable Validation
        "R301",  # Non-FQCN Use
        "R303",  # Task Without Name
        "R116",  # Insecure File Permissions
    ]
    ## Disclaimer do not add R306, because is normal that fails when checking only one file
    # R306 removed - Undefined variables are often legitimate

    # Rule ID to fix suggestion mapping
    RULE_FIXES: ClassVar[dict[str, str]] = {
        "R301": "Non-FQCN: Replace short module names with FQCN (e.g., 'apt' → 'ansible.builtin.apt')",
        "R303": "Task Without Name: Add 'name:' field to task",
        "R306": "These are warnings - you can ignore if variables are defined elsewhere",
        "P001": "Use correct module name",
        "P002": "Check module documentation for correct parameter names",
        "P003": "Check module documentation for correct parameter values",
        "P004": "Fix variable syntax",
        "R116": "Use secure file permissions (e.g., mode: '0644' or stricter)",
    }

    # Playbook wrapper keys that shouldn't appear in taskfiles
    PLAYBOOK_KEYS: ClassVar[set[str]] = {"hosts", "tasks", "plays", "import_playbook"}


# ==============================================================================
# Domain Services
# ==============================================================================


class ErrorTypeDetector:
    """Detects the type of YAML validation error for appropriate formatting.

    Uses pattern matching to identify specific error types and provide
    context for error formatting.
    """

    @staticmethod
    def detect(error_message: str, problem: str | None) -> str | None:
        """Detect the error type from error message and problem description.

        Args:
            error_message: The main error message
            problem: Specific problem description from YAML parser

        Returns:
            Error type identifier or None if no specific type detected
        """
        if problem and "unhashable key" in problem.lower():
            return "unhashable_key"

        if "mapping values" in error_message.lower():
            return "mapping_values"

        return None

    @staticmethod
    def fix_unhashable_key(line: str) -> str:
        """Attempt to fix unhashable key error by quoting Jinja2 variables.

        Args:
            line: The problematic line

        Returns:
            Fixed line with quoted Jinja2 variables
        """

        # Find unquoted {{ }} patterns and quote them
        # Match patterns like: key: {{ var }}
        pattern = r"(\s+\w+):\s*({{[^}]+}})"

        def quote_jinja(match):
            key = match.group(1)
            jinja = match.group(2)
            # Check if already quoted
            if jinja.strip().startswith(('"', "'")):
                return f"{key}: {jinja}"
            return f'{key}: "{jinja}"'

        return re.sub(pattern, quote_jinja, line)


class ErrorFormattingService:
    """Service responsible for formatting validation errors using templates.

    Centralizes all error formatting logic, separating presentation from
    domain logic.
    """

    @staticmethod
    def format_yaml_validation_error(error: "AnsibleYAMLValidationError") -> str:
        """Format YAML validation error as XML for LLM consumption.

        Args:
            error: The validation error to format

        Returns:
            XML-formatted error message
        """
        # Detect error type
        error_type = ErrorTypeDetector.detect(error.error_message, error.problem)

        # Get fixed line if applicable
        fixed_line = None
        if error_type == "unhashable_key" and error.problematic_line:
            fixed_line = ErrorTypeDetector.fix_unhashable_key(error.problematic_line)

        # Prepare column pointer
        column_pointer = None
        if error.problematic_line is not None and error.column_number is not None:
            column_pointer = " " * (error.column_number - 1) + "^"

        # Render template
        template = jinja_env.get_template(TemplateNames.YAML_VALIDATION_ERROR)
        return template.render(
            file_path=error.file_path,
            error_message=error.error_message,
            line_number=error.line_number,
            column_number=error.column_number,
            problem=error.problem,
            problematic_line=error.problematic_line,
            column_pointer=column_pointer,
            error_type=error_type,
            fixed_line=fixed_line,
            yaml_content=error.yaml_content,
        )

    @staticmethod
    def format_playbook_wrapper_error(file_path: str, detected_keys: list[str]) -> str:
        """Format playbook wrapper error message.

        Args:
            file_path: Path to the file
            detected_keys: Keys detected in the YAML

        Returns:
            Formatted error message
        """
        template = jinja_env.get_template(TemplateNames.PLAYBOOK_WRAPPER_ERROR)
        return template.render(
            file_path=file_path,
            detected_keys=detected_keys,
        )

    @staticmethod
    def format_ari_errors(
        file_path: str,
        validation_message: str,
        errors: list["TaskfileValidationError"],
    ) -> str:
        """Format ARI validation errors.

        Args:
            file_path: Path to the file
            validation_message: Error message from ARI validator
            errors: List of validation errors

        Returns:
            Formatted error message
        """
        # Generate fix suggestions only for the rules that were actually found
        unique_rules = {}
        for error in errors:
            if error.rule_id not in unique_rules:
                unique_rules[error.rule_id] = error.get_fix_suggestion()

        template = jinja_env.get_template(TemplateNames.ARI_ERRORS)
        return template.render(
            file_path=file_path,
            validation_message=validation_message,
            unique_rules=unique_rules,
        )

    @staticmethod
    def format_multiple_errors(errors: list[str]) -> str:
        """Format multiple validation errors.

        Args:
            errors: List of error messages

        Returns:
            Formatted error message
        """
        template = jinja_env.get_template(TemplateNames.MULTIPLE_ERRORS)
        return template.render(
            error_count=len(errors),
            errors=errors,
        )


# ==============================================================================
# Value Objects & Data Classes
# ==============================================================================


@dataclass
class AnsibleYAMLValidationError:
    """Structured error information for Ansible YAML validation failures.

    Pure value object - contains only data extracted from exceptions.
    Formatting is handled by ErrorFormattingService.
    """

    file_path: str
    error_message: str
    yaml_content: str
    line_number: int | None = None
    column_number: int | None = None
    problem: str | None = None
    problematic_line: str | None = None

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


@dataclass
class TaskfileValidationError:
    """Structured error information for ARI taskfile validation failures.

    Pure value object - contains only data, no formatting logic.
    """

    filename: str
    line_num: str | int
    rule_id: str
    task_name: str
    rule_description: str
    detail: dict[str, Any] | None = None

    def to_string(self) -> str:
        """Format the error as a string message.

        Returns:
            Formatted error message with line number, rule ID, and details
        """
        error_msg = f"{self.filename}:{self.line_num} [{self.rule_id}] Task '{self.task_name}' has the following issue: '{self.rule_description}'"

        if self.detail:
            # Add specific details if available
            if "module" in self.detail and "fqcn" in self.detail:
                error_msg += f" - {self.detail['module']} → {self.detail['fqcn']}"
            elif "undefined_variables" in self.detail:
                vars_list = ", ".join(self.detail["undefined_variables"])
                error_msg += f" - Variables: {vars_list}"

        return error_msg

    def get_fix_suggestion(self) -> str:
        """Get the fix suggestion for this rule.

        Returns:
            Fix instruction string for this rule ID
        """
        return AnsibleValidationRules.RULE_FIXES.get(
            self.rule_id, "Review and fix the issue"
        )

    def __str__(self) -> str:
        """Default string representation."""
        return self.to_string()


class TaskfileValidator:
    """Validates Ansible taskfiles using ARI and reports errors with line numbers.

    Can be used as a context manager for automatic cleanup:
        with TaskfileValidator() as validator:
            success, message = validator.validate("tasks.yml")
    """

    def __init__(self, rules: list[str] | None = None):
        """
        Initialize validator with specific rules.

        Args:
            rules: List of rule IDs to check. If None, uses default set.
        """
        if rules is None:
            rules = AnsibleValidationRules.DEFAULT_RULES

        # Use system temp directory for ARI data
        ari_tmp = Path(tempfile.gettempdir()) / "x2a-convertor" / "ari-data"
        ari_tmp.mkdir(parents=True, exist_ok=True)

        self.data_dir = ari_tmp
        self.config = Config(
            data_dir=str(ari_tmp),
            rules=rules,
        )
        self.scanner = ARIScanner(self.config, silent=True)
        self.last_errors: list[TaskfileValidationError] = []

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
            with contextlib.suppress(Exception):
                shutil.rmtree(self.data_dir)

    def _check_task_loading_errors(self, taskfile_spec: Any) -> str | None:
        """Check for task loading errors and return error message if found.

        Args:
            taskfile_spec: The taskfile specification object

        Returns:
            Error message if loading errors found, None otherwise
        """
        if not taskfile_spec or not hasattr(taskfile_spec, "task_loading"):
            return None

        task_loading = taskfile_spec.task_loading
        if task_loading.get("failure", 0) > 0:
            error_lines = [f"ERROR: {task_loading['failure']} task(s) failed to load:"]
            for error in task_loading.get("errors", []):
                error_lines.append(f"  - {error}")
            return "\n".join(error_lines)

        return None

    def _has_actual_issue(self, rule_result: Any) -> bool:
        """Determine if a rule result represents an actual issue.

        Args:
            rule_result: The rule result object from ARI

        Returns:
            True if there's an actual issue, False otherwise
        """
        if not rule_result.matched:
            return False

        rule = rule_result.rule
        detail = rule_result.detail or {}

        # For R301 (FQCN), only flag if module name differs from FQCN
        if (
            rule.rule_id == "R301"
            and detail
            and "module" in detail
            and "fqcn" in detail
        ):
            return detail["module"] != detail["fqcn"]

        # verdict=True usually means issue found for error-detection rules
        if rule_result.verdict:
            return True

        # If there's detail content, it's likely an issue
        return bool(rule_result.detail)

    def _extract_task_info(
        self, node: Any, task_map: dict[str, Any]
    ) -> tuple[str, str | int]:
        """Extract task name and line number from a node.

        Args:
            node: The ARI node to extract info from
            task_map: Map of task keys to task objects

        Returns:
            Tuple of (task_name, line_num)
        """
        task_name = "unknown task"
        line_num: str | int = "?"

        node_spec = getattr(node.node, "spec", None)
        if not node_spec or not hasattr(node_spec, "key"):
            return task_name, line_num

        task_key = node_spec.key

        # Try to get from task_map first
        if task_key in task_map:
            task = task_map[task_key]
            task_name = task.name or "unnamed task"
            if task.line_num_in_file:
                line_num = task.line_num_in_file[0]
        # Fall back to getting info from spec directly
        elif hasattr(node_spec, "name"):
            task_name = node_spec.name or "unnamed task"
            if hasattr(node_spec, "line_num_in_file") and node_spec.line_num_in_file:
                line_num = node_spec.line_num_in_file[0]

        return task_name, line_num

    def _collect_rule_violations(
        self, target: Any, task_map: dict[str, Any], filename: str
    ) -> list[TaskfileValidationError]:
        """Collect all rule violations from validation target.

        Args:
            target: The ARI validation target
            task_map: Map of task keys to task objects
            filename: Name of the file being validated

        Returns:
            List of validation errors
        """
        errors: list[TaskfileValidationError] = []

        for node in target.nodes:
            if not hasattr(node, "rules"):
                continue

            for rule_result in node.rules:
                if not self._has_actual_issue(rule_result):
                    continue

                # Extract task information
                task_name, line_num = self._extract_task_info(node, task_map)

                # Create structured error
                rule = rule_result.rule
                detail = rule_result.detail or {}

                validation_error = TaskfileValidationError(
                    filename=filename,
                    line_num=line_num,
                    rule_id=rule.rule_id,
                    task_name=task_name,
                    rule_description=rule.description,
                    detail=detail,
                )

                errors.append(validation_error)

        return errors

    def validate(self, taskfile_path: str) -> tuple[bool, str]:
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
        with path_obj.open() as f:
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
            return False, f"ERROR: Validation failed: {e!s}"

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
        if error_msg := self._check_task_loading_errors(taskfile_spec):
            return False, error_msg

        # Get task definitions with line numbers
        tasks = scandata.root_definitions.get("definitions", {}).get("tasks", [])
        task_map = {task.key: task for task in tasks}

        # Collect rule violations
        errors = self._collect_rule_violations(target, task_map, path_obj.name)

        # Store errors for external access
        self.last_errors = errors

        # Return results
        if not errors:
            return True, "All checks passed"

        error_count = len(errors)
        error_strings = [str(e) for e in errors]
        error_message = f"Found {error_count} issue(s):\n" + "\n".join(error_strings)
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

    def _validate_not_empty(self, parsed_yaml: Any, yaml_content: str) -> str | None:
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

    def _validate_not_json(self, yaml_content: str) -> str | None:
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

    def _validate_no_playbook_wrapper(
        self, parsed_yaml: Any, file_path: str
    ) -> str | None:
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

        detected_keys = [
            key for key in AnsibleValidationRules.PLAYBOOK_KEYS if key in first_item
        ]

        if detected_keys:
            return ErrorFormattingService.format_playbook_wrapper_error(
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
            formatted_error = ErrorFormattingService.format_yaml_validation_error(
                structured_error
            )
            return f"ERROR: YAML validation failed. The file was not written.\n\n{formatted_error}"
        except Exception as e:
            return f"ERROR: when writing Ansible YAML file, the file was not written. Fix following error and try again:\n```{e!s}```."

    def _collect_blocking_errors(
        self, file_path: str, yaml_content: str, parsed_yaml: Any
    ) -> list[str]:
        """Collect blocking validation errors (not including ARI warnings).

        This allows the LLM to fix all issues at once instead of one at a time.
        ARI validation is run separately after file write and returns warnings.

        Returns:
            List of error messages (empty if no errors)
        """
        errors = []

        # Check for playbook wrapper
        if error := self._validate_no_playbook_wrapper(parsed_yaml, file_path):
            errors.append(error)

        # Try to write and check for formatting errors
        # We do this even if there are other errors to catch all issues
        try:
            if parsed_yaml is not None:
                _ = yaml.dump(
                    parsed_yaml,
                    Dumper=AnsibleDumper,
                    default_flow_style=False,
                    allow_unicode=True,
                    sort_keys=False,
                    width=160,
                )
        except AnsibleError as e:
            structured_error = AnsibleYAMLValidationError.from_ansible_error(
                error=e, file_path=file_path, yaml_content=yaml_content
            )
            formatted_error = ErrorFormattingService.format_yaml_validation_error(
                structured_error
            )
            errors.append(f"YAML Formatting Error:\n{formatted_error}")

        return errors

    def _run_ari_validation_warnings(
        self, file_path: str, yaml_content: str
    ) -> str | None:
        """Run ARI validation and return warnings if issues found.

        This runs AFTER the file has been written and returns non-blocking warnings.

        Args:
            file_path: Path to the file that was written
            yaml_content: The YAML content that was written

        Returns:
            Warning message if issues found, None if validation passed
        """
        if not self._is_taskfile(file_path):
            return None

        # Write to temp file for validation
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp:
            tmp.write(yaml_content)
            tmp_path = tmp.name

        try:
            success, validation_message = self._validator.validate(tmp_path)
            if not success:
                # Get the structured error objects and fix filenames
                validation_errors = self._validator.last_errors

                # Replace temp filename with actual filename in error objects
                tmp_filename = Path(tmp_path).name
                actual_filename = Path(file_path).name
                for error in validation_errors:
                    error.filename = actual_filename

                # Replace temp filename in validation message
                validation_message = validation_message.replace(
                    tmp_filename, actual_filename
                )

                formatted_error = ErrorFormattingService.format_ari_errors(
                    file_path, validation_message, validation_errors
                )
                return f"WARNING: File written but found {len(validation_errors)} validation issues:\n\n{formatted_error}"
        except Exception:
            pass  # Don't fail on ARI validation errors
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return None

    # pyrefly: ignore
    def _run(self, file_path: str, yaml_content: str) -> str:
        """Validate Ansible YAML content and write to file."""
        slog = logger.bind(phase="AnsibleWriteTool", file_path=file_path)
        slog.debug(f"AnsibleWriteTool called on {file_path}")

        yaml_content = yaml_content.replace("\\n", "\n")

        # STEP 1: Parse YAML (fatal error - can't continue if this fails)
        try:
            parsed_yaml = self._loader.load(data=yaml_content, json_only=False)
        except AnsibleError as e:
            slog.info(f"Failed to parse YAML for '{file_path}': {str(e)[:100]}")
            structured_error = AnsibleYAMLValidationError.from_ansible_error(
                error=e, file_path=file_path, yaml_content=yaml_content
            )
            return ErrorFormattingService.format_yaml_validation_error(structured_error)
        except Exception as e:
            slog.debug(
                f"Failed on generic parsing error: {e!s}\nContent: {yaml_content}"
            )
            return f"ERROR: when parsing YAML content, the file was not written. Fix following error and try again:\n```{e!s}```."

        # STEP 2: Basic validations
        if error := self._validate_not_empty(parsed_yaml, yaml_content):
            slog.debug("Failed on empty content")
            return error

        if error := self._validate_not_json(yaml_content):
            slog.debug("Failed on JSON instead of YAML")
            return error

        # STEP 3: Collect blocking errors (playbook wrapper, formatting issues)
        blocking_errors = self._collect_blocking_errors(
            file_path, yaml_content, parsed_yaml
        )

        if blocking_errors:
            slog.info(f"Found {len(blocking_errors)} blocking validation issues")
            # Return ALL blocking errors at once using template
            return ErrorFormattingService.format_multiple_errors(blocking_errors)

        # STEP 4: No blocking errors - write the file!
        result = self._format_and_write_yaml(parsed_yaml, file_path, yaml_content)

        if result.startswith("Successfully"):
            slog.info("Successfully wrote valid Ansible YAML")
            slog.debug("All validations passed")

            # STEP 5: Run ARI validation warnings (non-blocking)
            ari_warnings = self._run_ari_validation_warnings(file_path, yaml_content)
            if ari_warnings:
                slog.info("ARI validation found warnings")
                return ari_warnings
        else:
            slog.info(f"Failed to write Ansible yaml for '{file_path}'")

        return result
