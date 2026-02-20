"""Concrete validator implementations.

This module contains validators that wrap infrastructure tools (ansible-lint,
ansible-role-check) and translate their output into domain ValidationResults.
"""

from src.validation.results import ValidationResult
from tools.ansible_lint import (
    ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE,
    AnsibleLintTool,
    IssueFormatter,
    LintClassification,
)
from tools.ansible_role_check import AnsibleRoleCheckTool


class AnsibleLintValidator:
    """Validates Ansible roles using ansible-lint.

    Uses severity-based acceptance: critical errors (syntax, parse, load
    failures) cause validation failure, while non-critical warnings
    (best-practice rules like no-changed-when) are accepted with a message.
    """

    name = "ansible-lint"

    def __init__(self):
        self.tool = AnsibleLintTool()

    def validate(self, ansible_path: str) -> ValidationResult:
        """Run ansible-lint validation with severity-based acceptance.

        Args:
            ansible_path: Path to Ansible role directory

        Returns:
            ValidationResult: success if clean or only warnings remain,
            failure only for critical errors (syntax/parse/load failures).
        """
        classification = self.tool.lint_and_classify(ansible_path)

        if classification.is_clean:
            return ValidationResult(
                success=True,
                message=ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE,
                validator_name=self.name,
            )

        if classification.has_critical_errors:
            return self._build_critical_result(classification)

        return self._build_warning_result(classification)

    def _build_critical_result(
        self, classification: LintClassification
    ) -> ValidationResult:
        message = IssueFormatter.format_issues(classification.all_matches)
        return ValidationResult(
            success=False, message=message, validator_name=self.name
        )

    def _build_warning_result(
        self, classification: LintClassification
    ) -> ValidationResult:
        warning_text = IssueFormatter.format_issues(
            classification.warning_matches,
            prefix=f"Passed with {len(classification.warning_matches)} warning(s):",
        )
        return ValidationResult(
            success=True, message=warning_text, validator_name=self.name
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
