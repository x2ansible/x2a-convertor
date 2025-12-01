"""
Chef dependency resolution strategies.

Provides different strategies for resolving and fetching Chef cookbook dependencies:
- PolicyDependencyStrategy: For Policyfile.lock.json based cookbooks
- BerksDependencyStrategy: For Berksfile + metadata.rb based cookbooks

Uses the Strategy pattern to support multiple dependency management approaches
while maintaining a common interface.
"""

import json
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from src.inputs.policy_lock_parser import PolicyLockParser
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BaseDependencyStrategy(ABC):
    """Base class for Chef dependency resolution strategies."""

    def __init__(self, cookbook_path: str):
        """
        Initialize strategy with cookbook path.

        Args:
            cookbook_path: Path to the cookbook directory
        """
        self._cookbook_path = Path(cookbook_path)
        self._export_dir: Path | None = None

    @property
    def cookbook_path(self) -> Path:
        """Get cookbook path."""
        return self._cookbook_path

    @property
    def export_dir(self) -> Path | None:
        """Get export directory (migration-dependencies)."""
        return self._export_dir

    @classmethod
    @abstractmethod
    def can_handle(cls, cookbook_path: Path) -> bool:
        """
        Check if this strategy can handle the given cookbook.

        Args:
            cookbook_path: Path to cookbook directory

        Returns:
            True if this strategy can handle the cookbook
        """

    @abstractmethod
    def detect_cookbook_name(self) -> str | None:
        """
        Detect the cookbook name from available files.

        Returns:
            Cookbook name or None if not found
        """

    @abstractmethod
    def has_dependencies(self) -> tuple[bool, list]:
        """
        Check if cookbook has external dependencies.

        Returns:
            Tuple of (has_dependencies: bool, dependencies: list)
        """

    @abstractmethod
    def fetch_dependencies(self) -> None:
        """
        Fetch external dependencies to migration-dependencies directory.

        Raises:
            RuntimeError: If dependency fetching fails
        """

    @abstractmethod
    def get_dependency_paths(self, deps: list) -> list[str]:
        """
        Get paths to downloaded dependency cookbooks.

        Args:
            deps: List of dependencies from has_dependencies()

        Returns:
            List of absolute paths to dependency directories
        """

    def cleanup(self) -> None:
        """Remove migration-dependencies directory."""
        if not self._export_dir:
            return

        if self._export_dir.exists():
            shutil.rmtree(self._export_dir)
            logger.debug(f"Cleaned up {self._export_dir}")

        self._export_dir = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup."""
        self.cleanup()


class PolicyDependencyStrategy(BaseDependencyStrategy):
    """Strategy for Policyfile-based cookbooks."""

    def __init__(self, cookbook_path: str):
        """Initialize policy dependency strategy."""
        super().__init__(cookbook_path)
        self._policy_lock_path: Path | None = None
        self._parser: PolicyLockParser | None = None

    @classmethod
    def can_handle(cls, cookbook_path: Path) -> bool:
        """
        Check for Policyfile.lock.json within 5 levels up.

        Args:
            cookbook_path: Path to cookbook directory

        Returns:
            True if Policyfile.lock.json found
        """
        current = cookbook_path
        for _ in range(5):
            if (current / "Policyfile.lock.json").exists():
                return True
            if current.parent == current:  # Root directory
                break
            current = current.parent
        return False

    def _find_policy_lock(self) -> Path | None:
        """
        Search for Policyfile.lock.json up to 5 levels up.

        Returns:
            Path to Policyfile.lock.json or None
        """
        if self._policy_lock_path:
            return self._policy_lock_path

        current = self._cookbook_path
        for level in range(5):
            policy_lock = current / "Policyfile.lock.json"
            logger.debug(f"Checking for policy lock at: {policy_lock} (level {level})")
            if policy_lock.exists():
                absolute_path = policy_lock.resolve()
                self._policy_lock_path = absolute_path
                logger.info(f"Found Policyfile.lock.json at {absolute_path}")
                return absolute_path
            if current.parent == current:
                break
            current = current.parent

        logger.warning(
            f"No Policyfile.lock.json found within 5 levels of {self._cookbook_path}"
        )
        return None

    def _get_parser(self) -> PolicyLockParser:
        """Get or create PolicyLockParser."""
        if self._parser:
            return self._parser

        policy_lock = self._find_policy_lock()
        if not policy_lock:
            raise RuntimeError("Policyfile.lock.json not found")

        self._parser = PolicyLockParser(str(policy_lock))
        return self._parser

    def detect_cookbook_name(self) -> str | None:
        """
        Detect cookbook name from Policyfile.lock.json.

        Returns:
            Cookbook name or None
        """
        try:
            parser = self._get_parser()
            cookbook = parser.get_cookbook_by_path(str(self._cookbook_path))
            if cookbook:
                logger.info(
                    f"Detected cookbook '{cookbook.name}' (version {cookbook.version})"
                )
                return cookbook.name
        except Exception as e:
            logger.warning(f"Failed to detect cookbook name: {e}")

        return None

    def has_dependencies(self) -> tuple[bool, list]:
        """
        Check if cookbook has external dependencies.

        Returns:
            Tuple of (has_dependencies: bool, dependencies: list)
        """
        try:
            parser = self._get_parser()
            cookbook = parser.get_cookbook_by_path(str(self._cookbook_path))
            if not cookbook:
                logger.warning(
                    f"Cookbook not found in policy lock: {self._cookbook_path}"
                )
                return (False, [])

            deps = parser.get_cookbook_dependencies(cookbook.name)
            if deps:
                logger.info(
                    f"Cookbook '{cookbook.name}' has {len(deps)} dependencies: "
                    f"{[d.name for d in deps]}"
                )
            else:
                logger.info(f"Cookbook '{cookbook.name}' has no dependencies")

            return (len(deps) > 0, deps)

        except Exception as e:
            logger.error(f"Failed to check dependencies: {e}")
            return (False, [])

    def fetch_dependencies(self) -> None:
        """
        Fetch dependencies using chef-cli.

        Workflow:
        1. chef-cli install (resolve dependencies)
        2. chef-cli export (download to migration-dependencies)
        """
        policy_lock = self._find_policy_lock()
        if not policy_lock:
            raise RuntimeError("Policyfile.lock.json not found")

        policy_dir = policy_lock.parent
        logger.info(f"Fetching dependencies from {policy_dir}")

        # Verify chef-cli is available
        if not shutil.which("chef-cli"):
            raise RuntimeError(
                "chef-cli not found in PATH. Install Chef Workstation: "
                "https://www.chef.io/downloads/tools/workstation"
            )

        # Verify Policyfile.rb exists
        policyfile_rb = policy_dir / "Policyfile.rb"
        if not policyfile_rb.exists():
            raise RuntimeError(
                f"Policyfile.rb not found at {policyfile_rb}. "
                "Cannot install dependencies without Policyfile.rb"
            )

        # Step 1: chef-cli install
        install_cmd = ["chef-cli", "install", str(policyfile_rb)]
        logger.info(f"Running chef-cli install: {' '.join(install_cmd)}")

        try:
            install_result = subprocess.run(
                install_cmd,
                cwd=str(self._cookbook_path),
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
            logger.info("chef-cli install completed successfully")
            logger.debug(f"chef-cli install output: {install_result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            logger.error(f"chef-cli install failed: {e.stderr}")
            raise RuntimeError(f"chef-cli install failed: {e.stderr.strip()}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("chef-cli install timed out after 300 seconds") from e

        # Step 2: chef-cli export to temp directory
        temp_export_dir = Path(tempfile.mkdtemp(prefix="chef-export-"))
        logger.info(f"Created temporary export directory: {temp_export_dir}")

        try:
            export_cmd = [
                "chef-cli",
                "export",
                str(policy_lock),
                str(temp_export_dir),
            ]
            logger.info(f"Running chef-cli export: {' '.join(export_cmd)}")

            export_result = subprocess.run(
                export_cmd,
                cwd=str(self._cookbook_path),
                capture_output=True,
                text=True,
                timeout=300,
                check=True,
            )
            logger.info("chef-cli export completed successfully")
            if export_result.stdout:
                logger.debug(f"chef-cli output: {export_result.stdout.strip()}")

            # Copy to migration-dependencies
            self._export_dir = Path("migration-dependencies")

            if self._export_dir.exists():
                logger.info(f"Removing existing directory: {self._export_dir}")
                shutil.rmtree(self._export_dir)

            logger.info(f"Copying dependencies to {self._export_dir}")
            shutil.copytree(temp_export_dir, self._export_dir)
            logger.info("Dependencies copied successfully")

        except subprocess.CalledProcessError as e:
            logger.error(f"chef-cli export failed: {e.stderr}")
            raise RuntimeError(f"chef-cli export failed: {e.stderr.strip()}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError("chef-cli export timed out after 300 seconds") from e
        finally:
            # Clean up temp directory
            if temp_export_dir.exists():
                logger.debug(f"Cleaning up temporary directory: {temp_export_dir}")
                shutil.rmtree(temp_export_dir)

    def get_dependency_paths(self, deps: list) -> list[str]:
        """
        Get paths to downloaded dependency cookbooks.

        Args:
            deps: List of CookbookDependency objects

        Returns:
            List of absolute paths to dependency directories
        """
        if not self._export_dir:
            logger.warning("No export directory set, cannot resolve dependency paths")
            return []

        cookbook_artifacts = self._export_dir / "cookbook_artifacts"
        if not cookbook_artifacts.exists():
            logger.error(
                f"cookbook_artifacts directory not found at {cookbook_artifacts}"
            )
            return []

        logger.debug(f"Looking for cookbook artifacts in: {cookbook_artifacts}")
        paths = []
        missing_deps = []

        for dep in deps:
            dep_name = dep.name if hasattr(dep, "name") else dep["name"]
            dep_identifier = (
                dep.identifier if hasattr(dep, "identifier") else dep.get("identifier")
            )

            # Find directory matching pattern: {name}-{identifier}
            dep_dir = cookbook_artifacts / f"{dep_name}-{dep_identifier}"

            if not dep_dir.exists():
                logger.warning(f"Dependency directory not found: {dep_dir}")
                missing_deps.append(dep_name)
                continue

            paths.append(str(dep_dir.absolute()))
            logger.debug(f"Found dependency: {dep_name} at {dep_dir}")

        if missing_deps:
            logger.warning(
                f"Missing {len(missing_deps)} dependencies: {', '.join(missing_deps)}"
            )

        logger.info(f"Resolved {len(paths)}/{len(deps)} dependency paths")
        return paths


class BerksDependencyStrategy(BaseDependencyStrategy):
    """Strategy for Berkshelf-based cookbooks."""

    def __init__(self, cookbook_path: str):
        """Initialize Berkshelf dependency strategy."""
        super().__init__(cookbook_path)
        self._berks_list_cache: dict | None = None
        self._berks_installed: bool = False

    @classmethod
    def can_handle(cls, cookbook_path: Path) -> bool:
        """
        Check for Berksfile and metadata.rb.

        Args:
            cookbook_path: Path to cookbook directory

        Returns:
            True if both Berksfile and metadata.rb exist
        """
        has_berksfile = (cookbook_path / "Berksfile").exists()
        has_metadata = (cookbook_path / "metadata.rb").exists()
        return has_berksfile and has_metadata

    def _ensure_berks_installed(self) -> None:
        """
        Ensure berks install has been run.

        Runs `berks install` to resolve and download dependencies to ~/.berkshelf.
        This is idempotent - only runs once even if called multiple times.

        Raises:
            RuntimeError: If berks command fails
        """
        # Skip if already installed
        if self._berks_installed:
            logger.debug("berks install already completed, skipping")
            return

        # Check if berks is available
        if not shutil.which("berks"):
            raise RuntimeError(
                "berks command not found. Install Chef Workstation: "
                "https://www.chef.io/downloads/tools/workstation"
            )

        # Run berks install
        logger.info("Running berks install to resolve dependencies")
        try:
            install_cmd = ["berks", "install"]
            logger.debug(f"Running: {' '.join(install_cmd)} in {self._cookbook_path}")
            subprocess.run(
                install_cmd,
                cwd=str(self._cookbook_path),
                check=True,
                capture_output=True,
                text=True,
            )
            self._berks_installed = True
            logger.debug("berks install completed successfully")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"berks install failed: {e.stderr}") from e

    def _get_berks_list(self) -> dict:
        """
        Get cookbook list from berks using JSON output.

        Ensures dependencies are installed first, then uses `berks list --format json`
        to get all cookbooks and their metadata.

        Returns:
            Parsed berks list output

        Raises:
            RuntimeError: If berks command fails
        """
        if self._berks_list_cache:
            return self._berks_list_cache

        # Ensure berks install has been run
        self._ensure_berks_installed()

        # Run berks list to get JSON metadata
        logger.info("Running berks list to get cookbook dependencies")

        try:
            cmd = ["berks", "list", "--format", "json"]
            logger.debug(f"Running: {' '.join(cmd)} in {self._cookbook_path}")
            result = subprocess.run(
                cmd,
                cwd=str(self._cookbook_path),
                check=True,
                capture_output=True,
                text=True,
            )

            self._berks_list_cache = json.loads(result.stdout)
            logger.debug(
                f"berks list returned {len(self._berks_list_cache.get('cookbooks', []))} cookbooks"
            )
            return self._berks_list_cache

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"berks list failed: {e.stderr}") from e
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse berks list output: {e}") from e

    def detect_cookbook_name(self) -> str | None:
        """
        Detect cookbook name from berks list.

        The main cookbook is identified by location "source at ."

        Returns:
            Cookbook name or None
        """
        try:
            berks_data = self._get_berks_list()
            cookbooks = berks_data.get("cookbooks", [])

            # Find main cookbook (location is "source at .")
            for cookbook in cookbooks:
                location = cookbook.get("location", "")
                if "source at ." in location:
                    name = cookbook.get("name")
                    if name:
                        logger.info(f"Detected main cookbook: {name}")
                        return name

            logger.warning("Could not find main cookbook in berks list")
            return None

        except Exception as e:
            logger.warning(f"Failed to detect cookbook name: {e}")
            return None

    def has_dependencies(self) -> tuple[bool, list]:
        """
        Check if cookbook has external dependencies using berks list.

        Dependencies are all cookbooks EXCEPT the main one (with "source at .").

        Returns:
            Tuple of (has_dependencies: bool, dependencies: list)
            Each dependency is a dict with: name, version, location (optional)
        """
        try:
            berks_data = self._get_berks_list()
            cookbooks = berks_data.get("cookbooks", [])

            # Filter out the main cookbook
            dependencies = []
            for cookbook in cookbooks:
                location = cookbook.get("location", "")

                # Skip the main cookbook (source at .)
                if "source at ." in location:
                    continue

                # Add all other cookbooks as dependencies
                dep = {
                    "name": cookbook.get("name"),
                    "version": cookbook.get("version"),
                }

                # Add location if it exists (helps identify local vs supermarket)
                if location:
                    dep["location"] = location

                dependencies.append(dep)

            if dependencies:
                dep_names = [d["name"] for d in dependencies]
                logger.info(
                    f"Found {len(dependencies)} dependencies: {', '.join(dep_names)}"
                )
            else:
                logger.info("No dependencies found")

            return (len(dependencies) > 0, dependencies)

        except Exception as e:
            logger.error(f"Failed to check dependencies: {e}")
            return (False, [])

    def fetch_dependencies(self) -> None:
        """
        Fetch dependencies using berks.

        Workflow:
        1. berks install (resolve and download to ~/.berkshelf) - via _ensure_berks_installed()
        2. berks vendor migration-dependencies/cookbooks (copy to local dir)
        """
        logger.info(f"Fetching dependencies from {self._cookbook_path}")

        # Step 1: Ensure berks install has been run
        self._ensure_berks_installed()

        # Step 2: berks vendor
        self._export_dir = Path("migration-dependencies")
        cookbooks_dir = self._export_dir / "cookbooks"

        if self._export_dir.exists():
            logger.info(f"Removing existing directory: {self._export_dir}")
            shutil.rmtree(self._export_dir)

        try:
            vendor_cmd = ["berks", "vendor", str(cookbooks_dir.absolute())]
            logger.debug(f"Running: {' '.join(vendor_cmd)} in {self._cookbook_path}")
            subprocess.run(
                vendor_cmd,
                cwd=str(self._cookbook_path),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info(f"Vendored dependencies to {cookbooks_dir}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"berks vendor failed: {e.stderr}") from e

    def get_dependency_paths(self, deps: list) -> list[str]:
        """
        Get paths to downloaded dependency cookbooks.

        Args:
            deps: List of dependency dicts from has_dependencies()

        Returns:
            List of absolute paths to dependency directories
        """
        if not self._export_dir:
            return []

        cookbooks_dir = self._export_dir / "cookbooks"
        if not cookbooks_dir.exists():
            logger.warning(f"cookbooks directory not found: {cookbooks_dir}")
            return []

        paths = []
        for dep in deps:
            dep_name = dep.get("name") if isinstance(dep, dict) else dep.name
            if not dep_name:
                logger.warning(f"Skipping dependency with no name: {dep}")
                continue

            dep_path = cookbooks_dir / dep_name

            if dep_path.exists():
                paths.append(str(dep_path.absolute()))
                logger.debug(f"Found dependency: {dep_name} at {dep_path}")
            else:
                logger.warning(f"Dependency not found: {dep_name}")

        logger.info(f"Resolved {len(paths)}/{len(deps)} dependency paths")
        return paths
