"""Common interfaces for infrastructure analyzers.

This module defines protocols (interfaces) that all infrastructure analyzers
(Chef, Puppet, Salt) must implement, enabling polymorphism and consistent behavior.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class InfrastructureAnalyzer(Protocol):
    """Common interface for all infrastructure analyzers.

    All analyzers (Chef, Puppet, Salt) must implement this protocol.
    This enables polymorphic usage in analyze.py.

    Example:
        analyzer: InfrastructureAnalyzer = ChefSubagent(model)
        specification = analyzer.invoke(path, user_message)
    """

    def invoke(self, path: str, user_message: str) -> str:
        """Analyze infrastructure and return migration specification.

        Args:
            path: Path to infrastructure code (cookbook, manifest, state)
            user_message: User's migration requirements/instructions

        Returns:
            Migration specification as markdown string
        """
        ...
