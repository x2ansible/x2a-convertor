"""
Chef Dependency Manager - Factory for dependency resolution strategies.

Automatically detects cookbook type and delegates to appropriate strategy in this priority order:
- PolicyDependencyStrategy (Policyfile.lock.json)
- BerksDependencyStrategy (Berksfile + metadata.rb)
"""

from pathlib import Path
from typing import ClassVar

from src.inputs.chef.dependency_strategies import (
    BaseDependencyStrategy,
    BerksDependencyStrategy,
    PolicyDependencyStrategy,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ChefDependencyManager:
    """
    Factory for Chef dependency resolution.

    Automatically detects cookbook type and delegates to appropriate strategy.
    Maintains backward-compatible API.
    """

    # Strategy detection order (priority)
    _STRATEGIES: ClassVar[list[type[BaseDependencyStrategy]]] = [
        PolicyDependencyStrategy,
        BerksDependencyStrategy,
    ]

    def __init__(self, cookbook_path: str) -> None:
        """
        Initialize dependency manager.

        Args:
            cookbook_path: Path to cookbook directory

        Raises:
            RuntimeError: If no compatible strategy found
        """
        self._cookbook_path = Path(cookbook_path)
        self._strategy = self._detect_strategy()

        log = logger.bind(
            cookbook_path=cookbook_path, strategy=self._strategy.__class__.__name__
        )
        log.info("Initialized ChefDependencyManager")

    def _detect_strategy(self) -> BaseDependencyStrategy:
        """
        Detect and instantiate appropriate dependency strategy.

        Detection priority:
        1. PolicyDependencyStrategy (Policyfile.lock.json)
        2. BerksDependencyStrategy (Berksfile + metadata.rb)

        Returns:
            Instantiated strategy

        Raises:
            RuntimeError: If no compatible strategy found
        """
        for strategy_class in self._STRATEGIES:
            if strategy_class.can_handle(self._cookbook_path):
                logger.info(
                    f"Using {strategy_class.__name__} for {self._cookbook_path}"
                )
                return strategy_class(str(self._cookbook_path))

        # No strategy found
        error_msg = (
            f"No compatible Chef dependency strategy found for {self._cookbook_path}. "
            "Expected one of:\n"
            "  - Policyfile.lock.json (+ Policyfile.rb)\n"
            "  - Berksfile + metadata.rb"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # Delegate all methods to strategy

    @property
    def cookbook_path(self) -> Path:
        """Get cookbook path."""
        return self._strategy.cookbook_path

    @property
    def export_dir(self) -> Path | None:
        """Get export directory."""
        return self._strategy.export_dir

    @property
    def export_path(self) -> Path | None:
        """Get export path (backward compatibility alias)."""
        return self._strategy.export_dir

    def detect_cookbook_name(self) -> str | None:
        """Detect cookbook name."""
        return self._strategy.detect_cookbook_name()

    def has_dependencies(self) -> tuple[bool, list]:
        """
        Check if cookbook has dependencies.

        Returns:
            Tuple of (has_dependencies, dependencies_list)
        """
        return self._strategy.has_dependencies()

    def fetch_dependencies(self) -> None:
        """Fetch dependencies."""
        self._strategy.fetch_dependencies()

    def get_dependency_paths(self, deps: list) -> list[str]:
        """
        Get dependency paths.

        Args:
            deps: List of dependencies from has_dependencies()

        Returns:
            List of absolute paths to dependency directories
        """
        return self._strategy.get_dependency_paths(deps)

    def get_dependencies_paths(self, deps: list) -> list[str]:
        """
        Get dependency paths (backward compatibility alias).

        Note: This method name is kept for backward compatibility.
        Use get_dependency_paths() instead.

        Args:
            deps: List of dependencies from has_dependencies()

        Returns:
            List of absolute paths to dependency directories
        """
        return self.get_dependency_paths(deps)

    def cleanup(self) -> None:
        """Cleanup temporary directories."""
        self._strategy.cleanup()

    # Context manager support

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensure cleanup."""
        self.cleanup()
