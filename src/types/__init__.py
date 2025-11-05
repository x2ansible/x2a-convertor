"""Core data structures for infrastructure migration

This package provides:
- Document handling utilities
- Migration checklist management system
- Ansible domain types
- Migration state interfaces
"""

from .ansible_module import AnsibleModule
from .checklist import (
    SUMMARY_SUCCESS_MESSAGE,
    Checklist,
    ChecklistItem,
    ChecklistStatus,
)
from .document import DocumentFile
from .migration_state import MigrationStateInterface

__all__ = [
    "SUMMARY_SUCCESS_MESSAGE",
    "AnsibleModule",
    "Checklist",
    "ChecklistItem",
    "ChecklistStatus",
    "DocumentFile",
    "MigrationStateInterface",
]
