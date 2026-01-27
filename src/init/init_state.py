"""State management for init workflow.

This module defines the state object for the init phase following
the agent pattern used in exporters.
"""

from dataclasses import dataclass, field, replace

from src.types import BaseState


@dataclass
class InitState(BaseState):
    """State for init phase workflow following the exporter pattern.

    Inherits from BaseState for common fields (user_message, path, telemetry,
    failed, failure_reason).

    Init-specific attributes:
        directory_listing: Files found in repository (for context)
        refresh: Flag to skip plan generation if plan exists
        migration_plan_content: Generated high-level migration plan
        migration_plan_path: Path where migration plan was written
        metadata_items: Extracted metadata for .x2ansible-metadata.json
    """

    # Fields inherited from BaseState:
    # - user_message: str
    # - path: str
    # - telemetry: Telemetry | None (kw_only)
    # - failed: bool (kw_only)
    # - failure_reason: str (kw_only)

    # Init-specific fields (all keyword-only since they follow kw_only fields from BaseState)
    directory_listing: str = field(kw_only=True)
    refresh: bool = field(default=False, kw_only=True)
    migration_plan_content: str = field(default="", kw_only=True)
    migration_plan_path: str = field(default="", kw_only=True)
    metadata_items: list[dict[str, str]] = field(default_factory=list, kw_only=True)

    def update(self, **kwargs) -> "InitState":
        """Create new InitState with updated fields (immutable pattern).

        Args:
            **kwargs: Fields to update (must be valid InitState attributes)

        Returns:
            New InitState instance with updated fields
        """
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "InitState":
        """Mark this operation as failed with a reason.

        Overrides BaseState.mark_failed() to return InitState for proper typing.

        Args:
            reason: Human-readable failure reason

        Returns:
            New InitState with failed=True and failure_reason set
        """
        return self.update(failed=True, failure_reason=reason)
