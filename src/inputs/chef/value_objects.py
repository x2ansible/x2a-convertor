"""Chef-specific value objects.

This module defines immutable, self-validating value objects that represent
Chef domain concepts.
"""

import re


class RecipeName:
    """Value object representing a Chef recipe name (cookbook::recipe).

    Chef recipes are identified by a fully-qualified name in the format
    "cookbook::recipe". If only the cookbook name is provided, the recipe
    defaults to "default".

    Examples:
        RecipeName("redis::default") → cookbook="redis", recipe="default"
        RecipeName("redis") → cookbook="redis", recipe="default"
        RecipeName("app::install") → cookbook="app", recipe="install"
    """

    def __init__(self, full_name: str):
        self._full_name = full_name
        self._cookbook, self._recipe = self._parse(full_name)

    @staticmethod
    def _parse(full_name: str) -> tuple[str, str]:
        """Parse recipe name into cookbook and recipe parts."""
        if "::" not in full_name:
            return (full_name, "default")
        parts = full_name.split("::", 1)
        return (parts[0], parts[1])

    @property
    def full_name(self) -> str:
        return self._full_name

    @property
    def cookbook(self) -> str:
        return self._cookbook

    @property
    def recipe(self) -> str:
        return self._recipe

    @property
    def file_name(self) -> str:
        return f"{self._recipe}.rb"

    def __str__(self) -> str:
        return self._full_name

    def __repr__(self) -> str:
        return f"RecipeName('{self._full_name}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RecipeName):
            return False
        return self._full_name == other._full_name

    def __hash__(self) -> int:
        return hash(self._full_name)


class CookbookName:
    """Value object representing a Chef cookbook name.

    Cookbooks can have version suffixes in directory names (e.g., "redis-1.2.3").
    This value object provides methods to match directory names against cookbook names.
    """

    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def matches_directory(self, directory_name: str) -> bool:
        """Check if a directory name matches this cookbook."""
        return self._name in directory_name or directory_name.startswith(
            f"{self._name}-"
        )

    def __str__(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return f"CookbookName('{self._name}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CookbookName):
            return False
        return self._name == other._name

    def __hash__(self) -> int:
        return hash(self._name)


class ResourceTypeName:
    """Value object representing a custom resource type name.

    Chef custom resources follow the naming convention "{cookbook}_{resource}".
    This value object parses the resource type and generates all possible
    cookbook/provider combinations.
    """

    def __init__(self, resource_type: str):
        self._resource_type = resource_type
        self._parts = resource_type.split("_")

    @property
    def full_name(self) -> str:
        return self._resource_type

    @property
    def parts(self) -> list[str]:
        return self._parts

    def is_valid(self) -> bool:
        """Check if this is a valid custom resource type name."""
        return len(self._parts) >= 2

    def get_cookbook_provider_combinations(self) -> list[tuple[str, str]]:
        """Get all possible cookbook/provider combinations."""
        if not self.is_valid():
            return []

        combinations = []
        for i in range(1, len(self._parts)):
            cookbook = "_".join(self._parts[:i])
            provider = "_".join(self._parts[i:])
            combinations.append((cookbook, provider))

        return combinations

    def __str__(self) -> str:
        return self._resource_type

    def __repr__(self) -> str:
        return f"ResourceTypeName('{self._resource_type}')"


class AttributePath:
    """Value object for Chef attribute paths.

    Chef attributes are accessed using paths like:
        node.default['redis']['port']
        node.override['app']['version']

    This value object parses these paths and extracts the key hierarchy.
    """

    def __init__(self, path_string: str):
        self._path_string = path_string
        self._keys = self._parse_path(path_string)

    @staticmethod
    def _parse_path(path_string: str) -> list[str]:
        """Parse attribute path into list of keys."""
        # Remove node.default, node.override, etc
        cleaned = re.sub(
            r"^node\.(default|override|normal|automatic)\s*", "", path_string
        )
        # Extract keys from ['key1']['key2'] format
        keys = re.findall(r"\['([^']+)'\]", cleaned)
        return keys

    @property
    def path_string(self) -> str:
        return self._path_string

    @property
    def keys(self) -> list[str]:
        return self._keys

    def is_valid(self) -> bool:
        """Check if path was parsed successfully."""
        return len(self._keys) > 0

    def __str__(self) -> str:
        return self._path_string

    def __repr__(self) -> str:
        return f"AttributePath('{self._path_string}')"
