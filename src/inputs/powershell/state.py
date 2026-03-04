"""State management for PowerShell analysis workflow.

This module defines the state object for the PowerShell analysis phase,
following the pattern from src/inputs/chef/state.py.
"""

from dataclasses import dataclass, field, replace

from src.types import BaseState

from .models import PowerShellStructuredAnalysis


@dataclass
class PowerShellAnalysisState(BaseState):
    """State object for PowerShell analysis workflow.

    Inherits from BaseState for common fields (user_message, path, telemetry,
    failed, failure_reason).

    PowerShell analysis-specific attributes:
        specification: Generated migration specification
        dependency_modules: Import-Module references found
        structured_analysis: Aggregate analysis from all PowerShell files
        execution_summary: Precomputed summary for sharing between agents
    """

    specification: str = field(kw_only=True)
    dependency_modules: list[str] = field(default_factory=list, kw_only=True)
    structured_analysis: PowerShellStructuredAnalysis | None = field(
        default=None, kw_only=True
    )
    execution_summary: str = field(default="", kw_only=True)

    def update(self, **kwargs) -> "PowerShellAnalysisState":
        """Create a new PowerShellAnalysisState with updated fields."""
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "PowerShellAnalysisState":
        """Mark this analysis as failed with a reason."""
        return self.update(failed=True, failure_reason=reason)
