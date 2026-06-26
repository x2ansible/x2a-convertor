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
    ChecklistStats,
    ChecklistStatus,
)
from .credential import CredentialConfig
from .document import DocumentFile
from .file_analysis_state import FileAnalysisState
from .metadata import MetadataCollection, ModuleMetadata
from .migration_state import MigrationStateInterface
from .rule_file import RuleCollection, RuleFile
from .rules import RuleSection, RulesOutput
from .technology import Technology
from .telemetry import AgentMetrics, Telemetry, telemetry_context

__all__ = [
    "SUMMARY_SUCCESS_MESSAGE",
    "AAPDiscoveryResult",
    "AgentMetrics",
    "AnsibleModule",
    "BaseState",
    "Checklist",
    "ChecklistItem",
    "ChecklistStats",
    "ChecklistStatus",
    "CredentialConfig",
    "DocumentFile",
    "FileAnalysisState",
    "MetadataCollection",
    "MigrationStateInterface",
    "ModuleMetadata",
    "RuleCollection",
    "RuleFile",
    "RuleSection",
    "RulesOutput",
    "Technology",
    "Telemetry",
    "telemetry_context",
]
