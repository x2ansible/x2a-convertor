"""
Policy Lock File Parser

Parses Chef Policyfile.lock.json to extract dependency information.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)


class CookbookDependency(TypedDict):
    """Dependency information for a cookbook"""

    name: str
    identifier: str
    version: str


class CookbookInfo:
    """Information about a cookbook from policy lock"""

    def __init__(self, name: str, data: Dict):
        self.name = name
        self.version = data.get("version")
        self.identifier = data.get("identifier")
        self.cache_key = data.get("cache_key")
        self.origin = data.get("origin")
        self.source = data.get("source")
        self.source_options = data.get("source_options", {})

    @property
    def is_local(self) -> bool:
        """Check if cookbook is local (not from supermarket)"""
        return self.cache_key is None and self.source is not None

    @property
    def is_supermarket(self) -> bool:
        """Check if cookbook is from Chef Supermarket"""
        if not self.cache_key:
            return False
        return "supermarket.chef.io" in self.cache_key

    def __repr__(self):
        source_type = "local" if self.is_local else "supermarket"
        return f"<CookbookInfo {self.name}@{self.version} ({source_type})>"


class PolicyLockParser:
    """Parser for Policyfile.lock.json"""

    def __init__(self, lock_file_path: str):
        """
        Initialize parser with policy lock file path

        Args:
            lock_file_path: Path to Policyfile.lock.json

        Raises:
            FileNotFoundError: If policy lock file does not exist
            json.JSONDecodeError: If policy lock file is invalid JSON
        """
        logger.info(f"Initializing PolicyLockParser with file: {lock_file_path}")
        self.lock_file_path = Path(lock_file_path)

        if not self.lock_file_path.exists():
            logger.error(f"Policy lock file does not exist: {lock_file_path}")
            raise FileNotFoundError(f"Policy lock file not found: {lock_file_path}")

        logger.debug(f"Reading policy lock file: {self.lock_file_path}")
        try:
            with open(self.lock_file_path, "r") as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {lock_file_path}: {e}")
            raise

        # Parse cookbook_locks
        self.cookbooks: Dict[str, CookbookInfo] = {}
        cookbook_locks = self.data.get("cookbook_locks", {})

        logger.debug(f"Parsing {len(cookbook_locks)} cookbook entries")
        for name, data in cookbook_locks.items():
            cookbook_info = CookbookInfo(name, data)
            self.cookbooks[name] = cookbook_info
            logger.debug(f"Parsed cookbook: {cookbook_info}")

        local_count = sum(1 for cb in self.cookbooks.values() if cb.is_local)
        supermarket_count = sum(
            1 for cb in self.cookbooks.values() if cb.is_supermarket
        )

        logger.info(
            f"Successfully parsed {len(self.cookbooks)} cookbooks from policy lock "
            + f"({local_count} local, {supermarket_count} from supermarket)"
        )

    def get_cookbook_by_path(self, source_path: str) -> Optional[CookbookInfo]:
        """
        Find cookbook by its source path

        Args:
            source_path: Source path to match (e.g., "cookbooks/cache")

        Returns:
            CookbookInfo if found, None otherwise
        """
        logger.debug(f"Searching for cookbook with source path: {source_path}")
        for cookbook in self.cookbooks.values():
            if cookbook.source == source_path:
                logger.debug(
                    f"Found cookbook '{cookbook.name}' matching source path: {source_path}"
                )
                return cookbook
        logger.debug(f"No cookbook found with source path: {source_path}")
        return None

    def get_cookbook_by_name(self, name: str) -> Optional[CookbookInfo]:
        """
        Get cookbook by name

        Args:
            name: Cookbook name

        Returns:
            CookbookInfo if found, None otherwise
        """
        return self.cookbooks.get(name)

    def get_cookbook_dependencies(self, cookbook_name: str) -> List[CookbookDependency]:
        """
        Get dependencies for a specific cookbook

        Args:
            cookbook_name: Name of the cookbook

        Returns:
            List of dependency dicts with name, identifier, and version
        """
        logger.debug(f"Getting dependencies for cookbook: {cookbook_name}")
        dependencies_map = self.data.get("solution_dependencies", {}).get(
            "dependencies", {}
        )

        # Find the cookbook with version
        cookbook = self.get_cookbook_by_name(cookbook_name)
        if not cookbook:
            logger.warning(f"Cookbook '{cookbook_name}' not found in policy lock")
            return []

        cookbook_key = f"{cookbook_name} ({cookbook.version})"
        logger.debug(f"Looking up dependencies for key: {cookbook_key}")

        if cookbook_key not in dependencies_map:
            logger.debug(f"No dependencies entry found for {cookbook_key}")
            return []

        # Get direct dependencies
        direct_deps = dependencies_map[cookbook_key]
        dep_names = [dep[0] for dep in direct_deps]
        logger.debug(f"Found {len(dep_names)} direct dependencies: {dep_names}")

        # Build dependency list with identifiers
        result: List[CookbookDependency] = []
        all_dep_names = self._get_transitive_deps(cookbook_name, dependencies_map)
        logger.info(
            f"Resolved {len(all_dep_names)} total dependencies (including transitive) for {cookbook_name}"
        )

        for dep_name in all_dep_names:
            dep_cb = self.get_cookbook_by_name(dep_name)
            if dep_cb:
                dep: CookbookDependency = {
                    "name": dep_cb.name,
                    "identifier": dep_cb.identifier,
                    "version": dep_cb.version,
                }
                result.append(dep)
                logger.debug(f"Added dependency: {dep_name}@{dep_cb.version}")
            else:
                logger.warning(
                    f"Dependency '{dep_name}' listed but not found in cookbook_locks"
                )

        return result

    def _get_transitive_deps(
        self, cookbook_name: str, dependencies_map: Dict
    ) -> List[str]:
        """Get all transitive dependencies (recursive)"""
        logger.debug(f"Resolving transitive dependencies for: {cookbook_name}")
        cookbook = self.get_cookbook_by_name(cookbook_name)
        if not cookbook:
            logger.debug(
                f"Cookbook '{cookbook_name}' not found, cannot resolve transitive deps"
            )
            return []

        cookbook_key = f"{cookbook_name} ({cookbook.version})"
        if cookbook_key not in dependencies_map:
            logger.debug(f"No dependencies entry for {cookbook_key}")
            return []

        direct_deps = dependencies_map[cookbook_key]
        dep_names = [dep[0] for dep in direct_deps]

        # Get transitive dependencies recursively
        all_deps = set(dep_names)
        for dep_name in dep_names:
            logger.debug(f"Resolving transitive dependencies for child: {dep_name}")
            transitive = self._get_transitive_deps(dep_name, dependencies_map)
            all_deps.update(transitive)

        logger.debug(
            f"Total transitive dependencies for {cookbook_name}: {len(all_deps)}"
        )
        return list(all_deps)
