"""Core data structures for infrastructure migration

This package provides:
- Document handling utilities
- Migration checklist management system
"""

from .checklist import (
    SUMMARY_SUCCESS_MESSAGE,
    Checklist,
    ChecklistItem,
    ChecklistStatus,
)
from .document import DocumentFile

__all__ = [
    "DocumentFile",
    "ChecklistStatus",
    "ChecklistItem",
    "Checklist",
    "SUMMARY_SUCCESS_MESSAGE",
]
