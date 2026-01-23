"""Core data structures for infrastructure migration

This package provides:
- Document handling utilities
- Migration checklist management system
- Ansible domain types
- Migration state interfaces
- AAP discovery result types
- Telemetry tracking types
"""

from .aap_discovery import AAPDiscoveryResult
from .ansible_module import AnsibleModule
from .checklist import (
    SUMMARY_SUCCESS_MESSAGE,
    Checklist,
    ChecklistItem,
    ChecklistStatus,
)
from .document import DocumentFile
from .migration_state import MigrationStateInterface
from .telemetry import AgentMetrics, Telemetry, telemetry_context

__all__ = [
    "SUMMARY_SUCCESS_MESSAGE",
    "AAPDiscoveryResult",
    "AgentMetrics",
    "AnsibleModule",
    "Checklist",
    "ChecklistItem",
    "ChecklistStatus",
    "DocumentFile",
    "MigrationStateInterface",
    "Telemetry",
    "telemetry_context",
]
