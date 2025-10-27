"""Core data structures for infrastructure migration

This package provides:
- Document handling utilities
- Migration checklist management system
- Ansible domain types
"""

from .ansible_module import AnsibleModule
from .checklist import (
    SUMMARY_SUCCESS_MESSAGE,
    Checklist,
    ChecklistItem,
    ChecklistStatus,
)
from .document import DocumentFile

__all__ = [
    "AnsibleModule",
    "Checklist",
    "ChecklistItem",
    "ChecklistStatus",
    "DocumentFile",
    "SUMMARY_SUCCESS_MESSAGE",
]
