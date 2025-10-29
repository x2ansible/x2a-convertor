"""Concrete validator implementations.

This module contains validators that wrap infrastructure tools (ansible-lint,
ansible-role-check) and translate their output into domain ValidationResults.
"""

from src.validation.results import ValidationResult
from tools.ansible_lint import ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE, AnsibleLintTool
from tools.ansible_role_check import AnsibleRoleCheckTool


class AnsibleLintValidator:
    """Validates Ansible roles using ansible-lint.

    Wraps the AnsibleLintTool and provides a clean interface that returns
    structured ValidationResult objects.
    """

    name = "ansible-lint"

    def __init__(self):
        self.tool = AnsibleLintTool()

    def validate(self, ansible_path: str) -> ValidationResult:
        """Run ansible-lint validation.

        Args:
            ansible_path: Path to Ansible role directory

        Returns:
            ValidationResult with success status and message
        """
        # Use autofix=True to let ansible-lint fix simple issues (FQCN, yaml syntax)
        # Only complex issues that can't be auto-fixed will go to the LLM agent
        result = self.tool._run(ansible_path, autofix=True)
        return ValidationResult(
            success=(result == ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE),
            message=result,
            validator_name=self.name,
        )


class RoleStructureValidator:
    """Validates Ansible role structure using ansible-role-check.

    Wraps the AnsibleRoleCheckTool and handles both errors and warnings
    appropriately.
    """

    name = "role-check"

    def __init__(self):
        self.tool = AnsibleRoleCheckTool()

    def validate(self, ansible_path: str) -> ValidationResult:
        """Run role structure validation.

        Args:
            ansible_path: Path to Ansible role directory

        Returns:
            ValidationResult with success status and message.
            Warnings are treated as success.
        """
        result = self.tool.run(ansible_path)

        # Hard failures
        if "Validation failed" in result or "Error:" in result:
            return ValidationResult(False, result, self.name)

        # Warnings (check-mode limitations) are treated as success
        if "passed with warnings" in result:
            return ValidationResult(True, result, self.name)

        # Clean success
        return ValidationResult(
            True,
            "Role validation passed (check mode execution successful)",
            self.name,
        )
