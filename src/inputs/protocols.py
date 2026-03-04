"""Common interfaces for infrastructure analyzers and exporters.

This module defines protocols (interfaces) that all infrastructure analyzers
and migration exporters must implement, enabling polymorphism and consistent behavior.
"""

from typing import Protocol, runtime_checkable

from src.types.document import DocumentFile
from src.types.migration_state import MigrationStateInterface


@runtime_checkable
class InfrastructureAnalyzer(Protocol):
    """Common interface for all infrastructure analyzers.

    All analyzers (Chef, Puppet, Salt, PowerShell) must implement this protocol.
    This enables polymorphic usage in analyze.py.

    Example:
        analyzer: InfrastructureAnalyzer = ChefSubagent(model)
        specification = analyzer.invoke(path, user_message)
    """

    def invoke(self, path: str, user_message: str) -> str:
        """Analyze infrastructure and return migration specification.

        Args:
            path: Path to infrastructure code (cookbook, manifest, state, script)
            user_message: User's migration requirements/instructions

        Returns:
            Migration specification as markdown string
        """
        ...


@runtime_checkable
class MigrationExporter(Protocol):
    """Common interface for all migration exporters.

    All exporters must implement this protocol to enable polymorphic
    usage in migrate.py via the TechnologyRegistry.

    Example:
        exporter: MigrationExporter = ToAnsibleSubagent(model=model, module=module)
        result = exporter.invoke(path, user_message, ...)
    """

    def invoke(
        self,
        path: str,
        user_message: str,
        module_migration_plan: DocumentFile,
        high_level_migration_plan: DocumentFile,
        directory_listing: list[str],
    ) -> MigrationStateInterface:
        """Execute migration and return result state.

        Args:
            path: Path to source infrastructure code
            user_message: User requirements
            module_migration_plan: Detailed migration plan document
            high_level_migration_plan: High-level strategy document
            directory_listing: Files in source directory

        Returns:
            MigrationStateInterface with output, failure status, and reason
        """
        ...
