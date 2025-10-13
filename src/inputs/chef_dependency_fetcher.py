"""
Chef Dependency Fetcher

Uses chef-cli export to download cookbook dependencies from Chef Supermarket
and make them available for analysis.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from src.inputs.policy_lock_parser import PolicyLockParser, CookbookDependency

logger = logging.getLogger(__name__)


class ChefDependencyManager:
    """Fetches Chef cookbook dependencies using chef-cli export"""

    @property
    def cookbook_path(self):
        return self._cookbook_path

    def __init__(self, cookbook_path: str):
        """
        Initialize dependency fetcher

        Args:
            cookbook_path: Path to cookbook directory containing Policyfile.lock.json
        """
        logger.info(f"Initializing ChefDependencyManager for path: {cookbook_path}")

        self._cookbook_path = Path(cookbook_path)
        self.export_dir: Optional[Path] = None

        # Verify chef-cli is available
        if not shutil.which("chef-cli"):
            logger.error("chef-cli not found in PATH")
            raise RuntimeError("chef-cli not found in PATH. Install Chef Workstation.")

        logger.debug("chef-cli found in PATH")

        # Find and parse Policyfile.lock.json
        self.policy_lock_path = self._find_policy_lock()
        if not self.policy_lock_path:
            logger.error(
                f"Policyfile.lock.json not found in {cookbook_path} or parent directories"
            )
            raise RuntimeError("Policyfile.lock.json cannot be found.")

        logger.info(f"Using policy lock file: {self.policy_lock_path}")
        self.policy_lock = PolicyLockParser(str(self.policy_lock_path))

        # Detect cookbook name from path
        self.cookbook_name = self._detect_cookbook_name()
        if self.cookbook_name:
            logger.info(
                f"Initialized ChefDependencyManager for cookbook: {self.cookbook_name}"
            )
        else:
            logger.warning("Could not detect cookbook name from path")

    def _find_policy_lock(self) -> Optional[Path]:
        """Find Policyfile.lock.json in current directory or up to 3 levels up"""
        logger.debug(
            f"Searching for Policyfile.lock.json starting from {self.cookbook_path}"
        )
        current_path = self.cookbook_path

        for level in range(5):
            lock_file = current_path / "Policyfile.lock.json"
            logger.debug(f"Checking for policy lock at: {lock_file} (level {level})")
            if lock_file.exists():
                absolute_path = lock_file.resolve()
                logger.info(f"Found Policyfile.lock.json at {absolute_path}")
                return absolute_path
            current_path = current_path.parent
        logger.warning(
            f"No Policyfile.lock.json found within 3 levels of {self.cookbook_path}"
        )
        return None

    def _detect_cookbook_name(self) -> Optional[str]:
        """Detect cookbook name by matching path against policy lock"""
        logger.debug("Detecting cookbook name from path")
        cookbook = self.policy_lock.get_cookbook_by_path(str(self.cookbook_path))
        if not cookbook:
            logger.warning(
                f"No cookbook found in policy lock matching path: {self.cookbook_path}"
            )
            return None

        logger.info(
            f"Detected cookbook '{cookbook.name}' (version {cookbook.version}) from policy lock"
        )
        return cookbook.name

    def has_dependencies(self) -> Tuple[bool, List[CookbookDependency]]:
        """
        Check if cookbook has dependencies

        Returns:
            Tuple of (has_dependencies, dependencies_list)
        """
        if not self.cookbook_name:
            logger.debug("No cookbook name detected, cannot check dependencies")
            return (False, [])

        logger.debug(f"Checking dependencies for cookbook: {self.cookbook_name}")
        deps = self.policy_lock.get_cookbook_dependencies(self.cookbook_name)
        if not deps:
            logger.info(f"Cookbook '{self.cookbook_name}' has no dependencies")
            return (False, [])

        logger.info(
            f"Cookbook '{self.cookbook_name}' has {len(deps)} dependencies: {[d['name'] for d in deps]}"
        )
        return (True, deps)

    def fetch_dependencies(self) -> None:
        """Download dependencies using chef-cli export"""
        logger.info("Fetching dependencies using chef-cli export")

        # Use a temp directory for chef-cli export to avoid path conflicts
        temp_export_dir = Path(tempfile.mkdtemp(prefix="chef-export-"))
        logger.info(f"Created temporary export directory: {temp_export_dir}")

        try:
            cmd = [
                "chef-cli",
                "export",
                str(self.policy_lock_path),
                str(temp_export_dir),
            ]

            logger.info(f"Running chef-cli command: {' '.join(cmd)}")
            logger.debug(f"Working directory: {self.cookbook_path}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.cookbook_path),
            )

            if result.returncode != 0:
                logger.error(
                    f"chef-cli export failed with return code {result.returncode}"
                )
                logger.error(f"stderr: {result.stderr.strip()}")
                if result.stdout:
                    logger.debug(f"stdout: {result.stdout.strip()}")
                raise RuntimeError(f"chef-cli export failed: {result.stderr.strip()}")

            logger.info("chef-cli export completed successfully")
            if result.stdout:
                logger.debug(f"chef-cli output: {result.stdout.strip()}")

            # Now copy to migration-dependencies in the repo
            self.export_dir = Path("migration-dependencies")

            # Clean up if it already exists
            if self.export_dir.exists():
                logger.info(
                    f"Removing existing migration-dependencies directory: {self.export_dir}"
                )
                shutil.rmtree(self.export_dir)

            # Copy from temp to migration-dependencies
            logger.info(f"Copying dependencies from temp to {self.export_dir}")
            shutil.copytree(temp_export_dir, self.export_dir)
            logger.info(f"Dependencies copied to {self.export_dir}")

        finally:
            # Clean up temp directory
            if temp_export_dir.exists():
                logger.debug(f"Cleaning up temporary directory: {temp_export_dir}")
                shutil.rmtree(temp_export_dir)

    def get_dependencies_paths(self, deps: List[CookbookDependency]) -> List[str]:
        """
        Get paths to downloaded dependency cookbooks

        Args:
            deps: List of dependencies from has_dependencies()

        Returns:
            List of paths to individual cookbook directories
        """
        logger.debug(f"Resolving paths for {len(deps)} dependencies")

        if not self.export_dir:
            logger.warning("No export directory set, cannot resolve dependency paths")
            return []

        artifacts_path = self.export_dir / "cookbook_artifacts"
        if not artifacts_path.exists():
            logger.error(f"cookbook_artifacts directory not found at {artifacts_path}")
            return []

        logger.debug(f"Looking for cookbook artifacts in: {artifacts_path}")
        paths = []
        missing_deps = []

        for dep in deps:
            dep_dir = artifacts_path / f"{dep['name']}-{dep['identifier']}"
            if not dep_dir.exists():
                logger.warning(f"Dependency directory not found: {dep_dir}")
                missing_deps.append(f"{dep['name']}@{dep['version']}")
                continue

            paths.append(str(dep_dir))
            logger.debug(
                f"Found dependency path: {dep['name']}@{dep['version']} -> {dep_dir}"
            )

        if missing_deps:
            logger.warning(
                f"Missing {len(missing_deps)} dependencies: {', '.join(missing_deps)}"
            )

        logger.info(f"Resolved {len(paths)}/{len(deps)} dependency paths successfully")
        return paths

    @property
    def export_path(self):
        return self.export_dir

    def cleanup(self):
        """Remove export directory"""
        if not self.export_dir:
            logger.debug("No export directory to cleanup")
            return

        if not self.export_dir.exists():
            logger.debug(f"Export directory already removed: {self.export_dir}")
            self.export_dir = None
            return

        try:
            logger.info(f"Cleaning up export directory: {self.export_dir}")
            shutil.rmtree(self.export_dir)
            logger.info(f"Successfully removed export directory: {self.export_dir}")
        except Exception as e:
            logger.error(f"Failed to cleanup export directory {self.export_dir}: {e}")
        finally:
            self.export_dir = None

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure cleanup"""
        self.cleanup()
