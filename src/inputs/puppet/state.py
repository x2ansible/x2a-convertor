"""State management for Puppet analysis workflow.

This module defines the state object for the Puppet analysis phase,
following the pattern from src/inputs/chef/state.py.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

from src.types import BaseState

from .models import (
    CredentialAnalysisResult,
    HieraHierarchy,
    PuppetStructuredAnalysis,
)


@dataclass
class PuppetState(BaseState):
    """State object for Puppet analysis workflow.

    Inherits from BaseState for common fields (user_message, path, telemetry,
    failed, failure_reason).
    """

    specification: str = field(kw_only=True)
    dependency_paths: list[str] = field(kw_only=True, default_factory=list)
    dependency_info: list[dict] = field(kw_only=True, default_factory=list)
    export_path: str | None = field(default=None, kw_only=True)
    hiera_hierarchy: HieraHierarchy | None = field(default=None, kw_only=True)
    structured_analysis: PuppetStructuredAnalysis | None = field(
        default=None, kw_only=True
    )
    execution_tree_summary: str = field(default="", kw_only=True)
    credentials_analysis: list[CredentialAnalysisResult] | None = field(
        default=None, kw_only=True
    )
    variables_summary: str = field(default="", kw_only=True)

    @property
    def all_paths(self) -> list[Path]:
        return [Path(x) for x in [self.path, *self.dependency_paths]]

    def update(self, **kwargs) -> "PuppetState":
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "PuppetState":
        return self.update(failed=True, failure_reason=reason)
