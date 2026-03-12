"""Technology registry for mapping technologies to their analyzer and exporter factories.

This module provides a central registry that maps Technology enum values to
their corresponding analyzer and exporter factory callables. Adding a new
technology (Salt, Puppet) requires only creating the analyzer package and
registering it here.
"""

from collections.abc import Callable
from typing import Any, ClassVar

from src.types.technology import Technology


class TechnologyRegistry:
    """Registry mapping technologies to analyzer and exporter factories.

    Analyzer factories: Callable[[model], InfrastructureAnalyzer]
    Exporter factories: Callable[[model, AnsibleModule], MigrationExporter]
    """

    _analyzers: ClassVar[dict[Technology, Callable]] = {}
    _exporters: ClassVar[dict[Technology, Callable]] = {}

    @classmethod
    def register_analyzer(cls, technology: Technology, factory: Callable) -> None:
        """Register an analyzer factory for a technology."""
        cls._analyzers[technology] = factory

    @classmethod
    def register_exporter(cls, technology: Technology, factory: Callable) -> None:
        """Register an exporter factory for a technology."""
        cls._exporters[technology] = factory

    @classmethod
    def get_analyzer(cls, technology: Technology, model: Any = None) -> Any:
        """Get an analyzer instance for the given technology.

        Args:
            technology: The source technology
            model: Optional LLM model to pass to the factory

        Returns:
            An InfrastructureAnalyzer instance

        Raises:
            ValueError: If no analyzer is registered for the technology
        """
        factory = cls._analyzers.get(technology)
        if factory is None:
            raise ValueError(
                f"No analyzer registered for technology: {technology.value}"
            )
        return factory(model=model)

    @classmethod
    def get_exporter(
        cls, technology: Technology, model: Any = None, module: Any = None
    ) -> Any:
        """Get an exporter instance for the given technology.

        Args:
            technology: The source technology
            model: Optional LLM model to pass to the factory
            module: AnsibleModule value object

        Returns:
            A MigrationExporter instance

        Raises:
            ValueError: If no exporter is registered for the technology
        """
        factory = cls._exporters.get(technology)
        if factory is None:
            raise ValueError(
                f"No exporter registered for technology: {technology.value}"
            )
        return factory(model=model, module=module)

    @classmethod
    def reset(cls) -> None:
        """Clear all registrations. Useful for testing."""
        cls._analyzers.clear()
        cls._exporters.clear()


def register_defaults() -> None:
    """Register all built-in technology analyzers and exporters.

    This is called at module load time to ensure all technologies
    are available when the application starts.
    """
    from src.exporters.to_ansible import ToAnsibleSubagent
    from src.inputs.ansible import AnsibleSubagent
    from src.inputs.chef import ChefSubagent
    from src.inputs.powershell import PowerShellSubagent

    TechnologyRegistry.register_analyzer(Technology.CHEF, ChefSubagent)
    TechnologyRegistry.register_exporter(Technology.CHEF, ToAnsibleSubagent)

    TechnologyRegistry.register_analyzer(Technology.POWERSHELL, PowerShellSubagent)
    TechnologyRegistry.register_exporter(Technology.POWERSHELL, ToAnsibleSubagent)

    TechnologyRegistry.register_analyzer(Technology.ANSIBLE, AnsibleSubagent)
    TechnologyRegistry.register_exporter(Technology.ANSIBLE, ToAnsibleSubagent)


register_defaults()
