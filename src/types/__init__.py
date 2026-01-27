"""Core data structures for infrastructure migration

This package provides:
- Base state classes for all workflow phases
- Document handling utilities
- Migration checklist management system
- Ansible domain types
- Migration state interfaces
- AAP discovery result types
- Telemetry tracking types
- Metadata extraction types
"""

from .aap_discovery import AAPDiscoveryResult
from .ansible_module import AnsibleModule
from .base_state import BaseState
from .checklist import (
    SUMMARY_SUCCESS_MESSAGE,
    Checklist,
    ChecklistItem,
    ChecklistStatus,
)
from .document import DocumentFile
from .metadata import MetadataCollection, ModuleMetadata
from .migration_state import MigrationStateInterface
from .telemetry import AgentMetrics, Telemetry, telemetry_context

__all__ = [
    "SUMMARY_SUCCESS_MESSAGE",
    "AAPDiscoveryResult",
    "AgentMetrics",
    "AnsibleModule",
    "BaseState",
    "Checklist",
    "ChecklistItem",
    "ChecklistStatus",
    "DocumentFile",
    "MetadataCollection",
    "MigrationStateInterface",
    "ModuleMetadata",
    "Telemetry",
    "telemetry_context",
]
