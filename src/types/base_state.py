"""Base state for all migration workflow phases.

Provides common fields and behaviors shared across init, analyze, and migrate phases.
"""

from abc import ABC
from dataclasses import dataclass, field

from src.types.telemetry import Telemetry


@dataclass
class BaseState(ABC):
    """Base state class with common fields for all migration phases.

    This provides the foundation for init, analyze, and migrate phases,
    ensuring consistent telemetry tracking and basic metadata across
    the entire migration workflow.

    Common attributes:
        user_message: Original user requirements/instructions
        path: Path to the source infrastructure code being analyzed
        telemetry: Telemetry collector for tracking agent execution metrics
        failed: Whether the operation has failed
        failure_reason: Human-readable reason for failure
    """

    user_message: str
    path: str
    telemetry: Telemetry | None = field(default=None, kw_only=True)
    failed: bool = field(default=False, kw_only=True)
    failure_reason: str = field(default="", kw_only=True)

    def mark_failed(self, reason: str) -> "BaseState":
        """Mark this operation as failed with a reason.

        Convenience method for agents to signal failure in a clean way.

        Args:
            reason: Human-readable failure reason

        Returns:
            Self with failed=True and failure_reason set
        """
        self.failed = True
        self.failure_reason = reason
        return self

    def did_fail(self) -> bool:
        """Check if the operation failed.

        Returns:
            True if operation failed, False otherwise
        """
        return self.failed

    def get_failure_reason(self) -> str:
        """Get the reason for failure.

        Returns:
            Human-readable failure reason string, empty if not failed
        """
        return self.failure_reason
