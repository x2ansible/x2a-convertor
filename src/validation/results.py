"""Validation result types.

This module defines structured result types for validation operations,
replacing primitive tuples with type-safe, testable value objects.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    """Immutable validation result.

    Replaces the (bool, str) tuple pattern with a structured type that
    provides better semantics and testability.
    """

    success: bool
    message: str
    validator_name: str

    @property
    def failed(self) -> bool:
        """Check if validation failed."""
        return not self.success

    def format_error(self) -> str:
        """Format error message for error reports.

        Returns empty string if validation succeeded.
        """
        if self.success:
            return ""
        return f"## {self.validator_name} Errors\n```\n{self.message}\n```"
