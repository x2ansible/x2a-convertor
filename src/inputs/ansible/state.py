"""State management for Ansible analysis workflow.

This module defines the state object for the Ansible analysis phase,
following the pattern from src/inputs/powershell/state.py.
"""

from dataclasses import dataclass, field, replace

from src.types import BaseState

from .models import AnsibleStructuredAnalysis


@dataclass
class AnsibleAnalysisState(BaseState):
    """State object for Ansible analysis workflow.

    Inherits from BaseState for common fields (user_message, path, telemetry,
    failed, failure_reason).

    Ansible analysis-specific attributes:
        specification: Generated migration specification
        structured_analysis: Aggregate analysis from all Ansible files
        execution_summary: Precomputed summary for sharing between agents
        collection_dependencies: Existing collection dependencies from requirements.yml
    """

    specification: str = field(kw_only=True)
    collection_dependencies: list[str] = field(default_factory=list, kw_only=True)
    structured_analysis: AnsibleStructuredAnalysis | None = field(
        default=None, kw_only=True
    )
    execution_summary: str = field(default="", kw_only=True)

    def update(self, **kwargs) -> "AnsibleAnalysisState":
        """Create a new AnsibleAnalysisState with updated fields."""
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "AnsibleAnalysisState":
        """Mark this analysis as failed with a reason."""
        return self.update(failed=True, failure_reason=reason)
