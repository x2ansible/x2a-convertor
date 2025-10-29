"""Validation service for orchestrating multiple validators.

This module provides a service layer that coordinates multiple validators
and aggregates their results.
"""

from src.validation.results import ValidationResult


class ValidationService:
    """Orchestrates multiple validators and aggregates results.

    The service runs all registered validators and provides methods to
    check for errors and format reports for agent consumption.
    """

    def __init__(self, validators: list):
        """Initialize service with list of validators.

        Args:
            validators: List of validator instances (each must have validate() method)
        """
        self.validators = validators

    def validate_all(self, ansible_path: str) -> dict[str, ValidationResult]:
        """Run all validators and return results.

        Args:
            ansible_path: Path to Ansible role directory

        Returns:
            Dictionary mapping validator name to ValidationResult
        """
        return {
            validator.name: validator.validate(ansible_path)
            for validator in self.validators
        }

    def has_errors(self, results: dict[str, ValidationResult]) -> bool:
        """Check if any validation failed.

        Args:
            results: Dictionary of validation results

        Returns:
            True if any validator reported failure
        """
        return any(not r.success for r in results.values())

    def format_error_report(self, results: dict[str, ValidationResult]) -> str:
        """Format errors for agent consumption.

        Args:
            results: Dictionary of validation results

        Returns:
            Formatted error report string
        """
        failed = [r for r in results.values() if not r.success]

        if not failed:
            return ""

        return "\n\n".join(r.format_error() for r in failed)

    def get_success_message(self, results: dict[str, ValidationResult]) -> str:
        """Format success message including any warnings.

        Args:
            results: Dictionary of validation results

        Returns:
            Success message, possibly including warnings
        """
        messages = []
        for result in results.values():
            if result.success and "warning" in result.message.lower():
                messages.append(f"{result.validator_name}: {result.message}")

        if messages:
            return "Validation passed with warnings:\n" + "\n".join(messages)
        return "All validations passed"
