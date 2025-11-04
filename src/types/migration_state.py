"""Migration state interface for consistent failure handling across technologies.

This module defines the abstract base class that all technology-specific migration states
(Chef, Puppet, Salt) must implement to ensure consistent error handling.
"""

from abc import ABC, abstractmethod


class MigrationStateInterface(ABC):
    """Abstract base class that all migration states must implement.

    This ABC ensures consistent failure tracking and reporting
    across different source technologies (Chef, Puppet, Salt).

    Subclasses must implement:
    - did_fail() -> bool method
    - get_failure_reason() -> str method
    - get_output() -> str method

    Expected attributes on subclasses:
    - failed: bool
    - failure_reason: str
    - last_output: str
    """

    @abstractmethod
    def did_fail(self) -> bool:
        """Check if the migration failed.

        Returns:
            True if migration failed, False otherwise
        """
        pass

    @abstractmethod
    def get_failure_reason(self) -> str:
        """Get the reason for migration failure.

        Returns:
            Human-readable failure reason string, empty if not failed
        """
        pass

    @abstractmethod
    def get_output(self) -> str:
        """Get the final migration output/summary.

        Returns:
            Migration output string (success or failure summary)
        """
        pass
