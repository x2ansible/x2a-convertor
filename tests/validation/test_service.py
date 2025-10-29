"""Tests for ValidationService."""

from unittest.mock import Mock

import pytest

from src.validation.results import ValidationResult
from src.validation.service import ValidationService


class TestValidationService:
    """Tests for ValidationService orchestration."""

    def test_validate_all_success(self):
        """Test validation when all validators pass."""
        mock_validator1 = Mock()
        mock_validator1.name = "validator1"
        mock_validator1.validate.return_value = ValidationResult(
            True, "ok", "validator1"
        )

        mock_validator2 = Mock()
        mock_validator2.name = "validator2"
        mock_validator2.validate.return_value = ValidationResult(
            True, "ok", "validator2"
        )

        service = ValidationService([mock_validator1, mock_validator2])
        results = service.validate_all("/path")

        assert not service.has_errors(results)
        assert len(results) == 2
        assert results["validator1"].success
        assert results["validator2"].success

    def test_validate_all_one_fails(self):
        """Test validation when one validator fails."""
        mock_validator1 = Mock()
        mock_validator1.name = "validator1"
        mock_validator1.validate.return_value = ValidationResult(
            True, "ok", "validator1"
        )

        mock_validator2 = Mock()
        mock_validator2.name = "validator2"
        mock_validator2.validate.return_value = ValidationResult(
            False, "error", "validator2"
        )

        service = ValidationService([mock_validator1, mock_validator2])
        results = service.validate_all("/path")

        assert service.has_errors(results)
        error_report = service.format_error_report(results)
        assert "validator2" in error_report
        assert "error" in error_report

    def test_validate_all_both_fail(self):
        """Test validation when multiple validators fail."""
        mock_validator1 = Mock()
        mock_validator1.name = "validator1"
        mock_validator1.validate.return_value = ValidationResult(
            False, "error1", "validator1"
        )

        mock_validator2 = Mock()
        mock_validator2.name = "validator2"
        mock_validator2.validate.return_value = ValidationResult(
            False, "error2", "validator2"
        )

        service = ValidationService([mock_validator1, mock_validator2])
        results = service.validate_all("/path")

        assert service.has_errors(results)
        error_report = service.format_error_report(results)
        assert "validator1" in error_report
        assert "validator2" in error_report
        assert "error1" in error_report
        assert "error2" in error_report

    def test_format_error_report_empty_when_all_pass(self):
        """Test that error report is empty when all validations pass."""
        mock_validator = Mock()
        mock_validator.name = "validator1"
        mock_validator.validate.return_value = ValidationResult(
            True, "ok", "validator1"
        )

        service = ValidationService([mock_validator])
        results = service.validate_all("/path")

        assert service.format_error_report(results) == ""

    def test_get_success_message_with_warnings(self):
        """Test success message when there are warnings."""
        mock_validator = Mock()
        mock_validator.name = "validator1"
        mock_validator.validate.return_value = ValidationResult(
            True, "passed with warnings: something minor", "validator1"
        )

        service = ValidationService([mock_validator])
        results = service.validate_all("/path")

        message = service.get_success_message(results)
        assert "Validation passed with warnings" in message
        assert "validator1" in message

    def test_get_success_message_clean(self):
        """Test success message when there are no warnings."""
        mock_validator = Mock()
        mock_validator.name = "validator1"
        mock_validator.validate.return_value = ValidationResult(
            True, "all good", "validator1"
        )

        service = ValidationService([mock_validator])
        results = service.validate_all("/path")

        message = service.get_success_message(results)
        assert message == "All validations passed"

    def test_has_errors_false_with_empty_results(self):
        """Test has_errors with empty results."""
        service = ValidationService([])
        results = {}

        assert not service.has_errors(results)

    def test_validate_all_calls_each_validator(self):
        """Test that validate_all calls each validator's validate method."""
        mock_validator1 = Mock()
        mock_validator1.name = "val1"
        mock_validator1.validate.return_value = ValidationResult(True, "ok", "val1")

        mock_validator2 = Mock()
        mock_validator2.name = "val2"
        mock_validator2.validate.return_value = ValidationResult(True, "ok", "val2")

        service = ValidationService([mock_validator1, mock_validator2])
        service.validate_all("/test/path")

        mock_validator1.validate.assert_called_once_with("/test/path")
        mock_validator2.validate.assert_called_once_with("/test/path")
