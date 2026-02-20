"""Tests for validation validators."""

from unittest.mock import Mock

from src.validation.validators import AnsibleLintValidator, RoleStructureValidator
from tests.tools.test_ansible_lint import _make_match
from tools.ansible_lint import (
    ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE,
    LintClassification,
)


class TestAnsibleLintValidator:
    """Tests for AnsibleLintValidator."""

    def test_validate_success(self):
        """Test successful validation when lint is clean."""
        validator = AnsibleLintValidator()
        validator.tool = Mock()
        validator.tool.lint_and_classify.return_value = LintClassification(
            critical_matches=[], warning_matches=[]
        )

        result = validator.validate("/fake/path")

        assert result.success
        assert result.validator_name == "ansible-lint"
        assert result.failed is False
        assert result.message == ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE
        validator.tool.lint_and_classify.assert_called_once_with("/fake/path")

    def test_validate_warnings_only(self):
        """Test that warnings-only classification returns success=True."""
        validator = AnsibleLintValidator()
        validator.tool = Mock()

        warning_match = _make_match(
            "no-changed-when", "Commands should have changed_when"
        )
        validator.tool.lint_and_classify.return_value = LintClassification(
            critical_matches=[], warning_matches=[warning_match]
        )

        result = validator.validate("/fake/path")

        assert result.success
        assert result.failed is False
        assert "warning" in result.message.lower()
        assert result.validator_name == "ansible-lint"

    def test_validate_critical_errors(self):
        """Test that critical errors return success=False."""
        validator = AnsibleLintValidator()
        validator.tool = Mock()

        critical_match = _make_match("syntax-check", "Syntax error", "VERY_HIGH")
        validator.tool.lint_and_classify.return_value = LintClassification(
            critical_matches=[critical_match], warning_matches=[]
        )

        result = validator.validate("/fake/path")

        assert not result.success
        assert result.failed is True
        assert result.validator_name == "ansible-lint"

    def test_validate_mixed_critical_and_warnings(self):
        """Test that critical + warnings returns success=False."""
        validator = AnsibleLintValidator()
        validator.tool = Mock()

        critical_match = _make_match("load-failure", "Load failure", "VERY_HIGH")
        warning_match = _make_match("no-changed-when", "Missing changed_when")
        validator.tool.lint_and_classify.return_value = LintClassification(
            critical_matches=[critical_match], warning_matches=[warning_match]
        )

        result = validator.validate("/fake/path")

        assert not result.success
        assert result.failed is True

    def test_format_error_on_failure(self):
        """Test error formatting for critical errors."""
        validator = AnsibleLintValidator()
        validator.tool = Mock()

        critical_match = _make_match("syntax-check", "Syntax error", "VERY_HIGH")
        validator.tool.lint_and_classify.return_value = LintClassification(
            critical_matches=[critical_match], warning_matches=[]
        )

        result = validator.validate("/fake/path")

        formatted = result.format_error()
        assert "## ansible-lint Errors" in formatted


class TestRoleStructureValidator:
    """Tests for RoleStructureValidator."""

    def test_validate_success(self):
        """Test successful validation."""
        validator = RoleStructureValidator()
        validator.tool = Mock()
        validator.tool.run.return_value = (
            "Role validation passed (check mode execution successful)"
        )

        result = validator.validate("/fake/path")

        assert result.success
        assert result.failed is False
        assert result.validator_name == "role-check"

    def test_validate_with_warnings(self):
        """Test validation with warnings (should still pass)."""
        validator = RoleStructureValidator()
        validator.tool = Mock()
        validator.tool.run.return_value = "Role validation passed with warnings"

        result = validator.validate("/fake/path")

        assert result.success  # Should pass despite warnings
        assert "warning" in result.message.lower()
        assert result.validator_name == "role-check"

    def test_validate_failure(self):
        """Test failed validation."""
        validator = RoleStructureValidator()
        validator.tool = Mock()
        validator.tool.run.return_value = "Validation failed: undefined variable"

        result = validator.validate("/fake/path")

        assert not result.success
        assert result.failed is True
        assert "failed" in result.message.lower()

    def test_validate_error(self):
        """Test validation error."""
        validator = RoleStructureValidator()
        validator.tool = Mock()
        validator.tool.run.return_value = "Error: something went wrong"

        result = validator.validate("/fake/path")

        assert not result.success
        assert "Error" in result.message

    def test_format_error_on_failure(self):
        """Test error formatting."""
        validator = RoleStructureValidator()
        validator.tool = Mock()
        validator.tool.run.return_value = "Validation failed: test error"

        result = validator.validate("/fake/path")

        formatted = result.format_error()
        assert "## role-check Errors" in formatted
        assert "test error" in formatted


class TestValidationResult:
    """Tests for ValidationResult value object."""

    def test_format_error_when_success(self):
        """Test that format_error returns empty string on success."""
        from src.validation.results import ValidationResult

        result = ValidationResult(
            success=True, message="all good", validator_name="test"
        )

        assert result.format_error() == ""

    def test_format_error_when_failed(self):
        """Test error formatting when validation failed."""
        from src.validation.results import ValidationResult

        result = ValidationResult(
            success=False, message="test error", validator_name="test-validator"
        )

        formatted = result.format_error()
        assert "## test-validator Errors" in formatted
        assert "test error" in formatted
        assert "```" in formatted  # Should be wrapped in code block

    def test_failed_property(self):
        """Test failed property."""
        from src.validation.results import ValidationResult

        success_result = ValidationResult(True, "ok", "test")
        failed_result = ValidationResult(False, "error", "test")

        assert not success_result.failed
        assert failed_result.failed
