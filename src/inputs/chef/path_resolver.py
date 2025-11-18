"""Chef path resolution service.

This module provides stateless path resolution for Chef files (recipes, providers, attributes).
Pure functions with no side effects.
"""

from pathlib import Path

from .value_objects import CookbookName, RecipeName, ResourceTypeName


class ChefPathResolver:
    """Resolves Chef recipe, provider, and attributes file paths.

    Stateless service that searches through dependency directories to find
    Chef files based on domain names.
    """

    @staticmethod
    def resolve_recipe_path(
        recipe_name: RecipeName, dependency_paths: list[str]
    ) -> Path | None:
        """Resolve recipe name to full file path.

        Args:
            recipe_name: RecipeName value object
            dependency_paths: List of directory paths to search

        Returns:
            Path if found, None otherwise
        """
        cookbook_name = CookbookName(recipe_name.cookbook)

        for dep_path in dependency_paths:
            dep_dir = Path(dep_path)
            recipe_path = ChefPathResolver._find_recipe_in_directory(
                dep_dir, cookbook_name, recipe_name
            )
            if recipe_path:
                return recipe_path

        return None

    @staticmethod
    def _find_recipe_in_directory(
        dep_dir: Path, cookbook: CookbookName, recipe: RecipeName
    ) -> Path | None:
        """Find recipe file in a directory."""
        if not dep_dir.is_dir():
            return None

        # Check if dep_dir itself is a cookbook
        recipes_dir_path = dep_dir / "recipes"
        if recipes_dir_path.exists() and cookbook.matches_directory(dep_dir.name):
            recipe_path = Path(recipes_dir_path / recipe.file_name)
            if recipe_path.exists():
                return recipe_path

        # Check subdirectories
        for item in dep_dir.iterdir():
            if not item.is_dir():
                continue

            cookbook_dir = Path(item)
            if cookbook.matches_directory(cookbook_dir.name):
                recipe_path = Path(cookbook_dir / "recipes" / recipe.file_name)
                if recipe_path.exists():
                    return recipe_path

        return None

    @staticmethod
    def resolve_provider_path(
        resource_type: ResourceTypeName, dependency_paths: list[str]
    ) -> Path | None:
        """Resolve custom resource type to provider file path.

        Args:
            resource_type: ResourceTypeName value object
            dependency_paths: List of directory paths to search

        Returns:
            Path if found, None otherwise
        """
        if not resource_type.is_valid():
            return None

        for (
            cookbook_name,
            provider_name,
        ) in resource_type.get_cookbook_provider_combinations():
            cookbook = CookbookName(cookbook_name)

            for dep_path in dependency_paths:
                dep_dir = Path(dep_path)
                provider_path = ChefPathResolver._find_provider_in_directory(
                    dep_dir, cookbook, provider_name
                )
                if provider_path:
                    return provider_path

        return None

    @staticmethod
    def _find_provider_in_directory(
        dep_dir: Path, cookbook: CookbookName, provider_name: str
    ) -> Path | None:
        """Find provider file in a directory."""
        if not dep_dir.is_dir():
            return None

        # Check if dep_dir itself is a cookbook
        providers_dir_path = dep_dir / "providers"
        if providers_dir_path.exists() and cookbook.matches_directory(dep_dir.name):
            provider_path = Path(providers_dir_path / f"{provider_name}.rb")
            if provider_path.exists():
                return provider_path

        # Check subdirectories
        for item in dep_dir.iterdir():
            if not item.is_dir():
                continue

            cookbook_dir = Path(item)
            if cookbook.matches_directory(cookbook_dir.name):
                provider_path = Path(cookbook_dir / "providers" / f"{provider_name}.rb")
                if provider_path.exists():
                    return provider_path

        return None

    @staticmethod
    def resolve_attributes_path(
        cookbook_name: CookbookName, dependency_paths: list[str]
    ) -> Path | None:
        """Resolve cookbook name to attributes/default.rb file path.

        Args:
            cookbook_name: CookbookName value object
            dependency_paths: List of directory paths to search

        Returns:
            Path if found, None otherwise
        """
        for dep_path in dependency_paths:
            dep_dir = Path(dep_path)
            attributes_path = ChefPathResolver._find_attributes_in_directory(
                dep_dir, cookbook_name
            )
            if attributes_path:
                return attributes_path

        return None

    @staticmethod
    def _find_attributes_in_directory(
        dep_dir: Path, cookbook: CookbookName
    ) -> Path | None:
        """Find attributes/default.rb file in a directory."""
        if not dep_dir.is_dir():
            return None

        # Check if dep_dir itself is a cookbook
        attributes_dir_path = dep_dir / "attributes"
        if attributes_dir_path.exists() and cookbook.matches_directory(dep_dir.name):
            attributes_path = Path(attributes_dir_path / "default.rb")
            if attributes_path.exists():
                return attributes_path

        # Check subdirectories
        for item in dep_dir.iterdir():
            if not item.is_dir():
                continue

            cookbook_dir = Path(item)
            if cookbook.matches_directory(cookbook_dir.name):
                attributes_path = Path(cookbook_dir / "attributes" / "default.rb")
                if attributes_path.exists():
                    return attributes_path

        return None
