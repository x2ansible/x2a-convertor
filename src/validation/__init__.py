"""Validation framework for Ansible migrations.

This module provides a pluggable validation system inspired by Django REST Framework.
Validators are composable, testable, and follow the Open/Closed principle.
"""

from src.validation.results import ValidationResult
from src.validation.service import ValidationService
from src.validation.validators import AnsibleLintValidator, RoleStructureValidator

__all__ = [
    "ValidationResult",
    "ValidationService",
    "AnsibleLintValidator",
    "RoleStructureValidator",
]
