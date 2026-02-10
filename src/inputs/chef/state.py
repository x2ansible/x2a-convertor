"""State management for Chef analysis workflow.

This module defines the state object for the Chef analysis phase,
following the pattern from src/exporters/state.py.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

from src.types import BaseState

from .models import StructuredAnalysis


@dataclass
class ChefState(BaseState):
    """State object for Chef analysis workflow.

    Inherits from BaseState for common fields (user_message, path, telemetry,
    failed, failure_reason).

    Chef analysis-specific attributes:
        specification: Generated migration specification
        dependency_paths: Paths to fetched cookbook dependencies
        export_path: Path where dependencies were exported
        structured_analysis: Aggregate analysis from all Chef files
        execution_tree_summary: Precomputed execution tree for sharing between agents
    """

    # Fields inherited from BaseState:
    # - user_message: str
    # - path: str
    # - telemetry: Telemetry | None (kw_only)
    # - failed: bool (kw_only)
    # - failure_reason: str (kw_only)

    # Chef analysis-specific fields
    specification: str = field(kw_only=True)
    dependency_paths: list[str] = field(kw_only=True)
    export_path: str | None = field(default=None, kw_only=True)
    structured_analysis: StructuredAnalysis | None = field(default=None, kw_only=True)
    execution_tree_summary: str = field(default="", kw_only=True)

    @property
    def all_paths(self) -> list[Path]:
        """Get all paths (main path + dependencies) as Path objects."""
        return [Path(x) for x in [self.path, *self.dependency_paths]]

    def update(self, **kwargs) -> "ChefState":
        """Create a new ChefState instance with updated fields.

        Args:
            **kwargs: Fields to update (must be valid ChefState attributes)

        Returns:
            New ChefState instance with updated fields
        """
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "ChefState":
        """Mark this analysis as failed with a reason.

        Args:
            reason: Human-readable failure reason

        Returns:
            New ChefState with failed=True and failure_reason set
        """
        return self.update(failed=True, failure_reason=reason)
