"""Collection installation service for AAP Private Hub and public Galaxy.

This service handles installing Ansible collections from requirements.yml,
supporting both AAP Private Automation Hub (with Bearer token auth) and
public Galaxy as a fallback.

Since ansible-galaxy's KeycloakToken tries to exchange tokens at auth_url
(which fails with AAP Controller OAuth tokens), this service uses a
download-and-install workaround for Private Hub collections.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin

import requests
import yaml

from src.config import AAPSettings
from src.utils.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Value Objects (Immutable)
# =============================================================================


@dataclass(frozen=True)
class CollectionSpec:
    """Specification for a collection to install."""

    namespace: str
    name: str
    version: str | None = None

    @property
    def fqcn(self) -> str:
        """Fully Qualified Collection Name."""
        return f"{self.namespace}.{self.name}"

    @property
    def spec_string(self) -> str:
        """Collection spec string for ansible-galaxy."""
        if self.version:
            return f"{self.fqcn}:{self.version}"
        return self.fqcn

    @classmethod
    def from_requirement(cls, item: str | dict) -> CollectionSpec | None:
        """Parse a collection from requirements.yml format.

        Args:
            item: Either a string "namespace.name" or dict with 'name' and optional 'version'

        Returns:
            CollectionSpec or None if invalid
        """
        name, version = cls._extract_name_and_version(item)
        if not name or "." not in name:
            return None

        namespace, coll_name = name.split(".", 1)
        return cls(namespace=namespace, name=coll_name, version=version)

    @staticmethod
    def _extract_name_and_version(item: str | dict) -> tuple[str, str | None]:
        """Extract name and version from requirement item."""
        if isinstance(item, str):
            return item, None
        if isinstance(item, dict):
            return item.get("name", ""), item.get("version")
        return "", None


@dataclass(frozen=True)
class InstallResult:
    """Result of a collection installation attempt."""

    collection: CollectionSpec
    success: bool
    source: str = ""  # "private_hub", "public_galaxy", or error message
    version_installed: str | None = None

    @classmethod
    def private_hub_success(
        cls, collection: CollectionSpec, version: str
    ) -> InstallResult:
        """Create successful Private Hub install result."""
        return cls(
            collection=collection,
            success=True,
            source="private_hub",
            version_installed=version,
        )

    @classmethod
    def public_galaxy_success(cls, collection: CollectionSpec) -> InstallResult:
        """Create successful public Galaxy install result."""
        return cls(collection=collection, success=True, source="public_galaxy")

    @classmethod
    def not_found(cls, collection: CollectionSpec) -> InstallResult:
        """Create not found result."""
        return cls(collection=collection, success=False, source="not_found")

    @classmethod
    def failed(cls, collection: CollectionSpec, reason: str) -> InstallResult:
        """Create failed result with reason."""
        return cls(collection=collection, success=False, source=reason)


@dataclass(frozen=True)
class DownloadInfo:
    """Download information for a collection from Private Hub."""

    url: str
    version: str


@dataclass(frozen=True)
class HighestVersionInfo:
    """Parsed highest version from Galaxy API response."""

    version: str

    @classmethod
    def from_json(cls, data: dict) -> HighestVersionInfo | None:
        """Parse from API response."""
        version = data.get("version", "")
        if not version:
            return None
        return cls(version=version)


@dataclass(frozen=True)
class CollectionMetadata:
    """Parsed collection metadata from Galaxy API response."""

    highest_version: HighestVersionInfo | None

    @classmethod
    def from_json(cls, data: dict) -> CollectionMetadata:
        """Parse from API response."""
        hv_data = data.get("highest_version", {})
        return cls(
            highest_version=HighestVersionInfo.from_json(hv_data) if hv_data else None
        )


@dataclass(frozen=True)
class VersionDetails:
    """Parsed version details from Galaxy API response."""

    download_url: str | None

    @classmethod
    def from_json(cls, data: dict) -> VersionDetails:
        """Parse from API response."""
        return cls(download_url=data.get("download_url"))


@dataclass(frozen=True)
class InstallResultSummary:
    """Summary of installation results."""

    success_count: int
    fail_count: int
    failures: tuple[InstallResult, ...]

    @property
    def all_succeeded(self) -> bool:
        """Check if all installations succeeded."""
        return self.fail_count == 0

    @classmethod
    def from_results(cls, results: list[InstallResult]) -> InstallResultSummary:
        """Create summary from results list."""
        failures = tuple(r for r in results if not r.success)
        return cls(
            success_count=len(results) - len(failures),
            fail_count=len(failures),
            failures=failures,
        )


# =============================================================================
# URL Builder
# =============================================================================


@dataclass(frozen=True)
class GalaxyURLBuilder:
    """Builds Galaxy API URLs with proper path handling."""

    base_url: str
    repository: str = "published"

    def collection_url(self, namespace: str, name: str) -> str:
        """Build URL for collection metadata."""
        path = f"/content/{self.repository}/v3/collections/{namespace}/{name}/"
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))

    def version_url(self, namespace: str, name: str, version: str) -> str:
        """Build URL for specific version details."""
        path = f"/content/{self.repository}/v3/collections/{namespace}/{name}/versions/{version}/"
        return urljoin(self.base_url.rstrip("/") + "/", path.lstrip("/"))


# =============================================================================
# Installation Strategy Protocol
# =============================================================================


class InstallStrategy(Protocol):
    """Protocol for collection installation strategies."""

    def install(
        self, collection: CollectionSpec, tmpdir: Path | None = None
    ) -> InstallResult | None:
        """Attempt to install collection. Returns result on success, None to try next."""
        ...


# =============================================================================
# Collection Manager
# =============================================================================


@dataclass
class CollectionManager:
    """Service for managing Ansible collection installations.

    Supports AAP Private Hub with Bearer token authentication and falls back
    to public Galaxy for collections not found in Private Hub.

    Usage:
        # With AAP settings
        manager = CollectionManager.from_settings(aap_settings)
        results = manager.install_from_requirements(Path("requirements.yml"))

        # Without AAP (public Galaxy only)
        manager = CollectionManager()
        results = manager.install_from_requirements(Path("requirements.yml"))
    """

    galaxy_url: str | None = None
    token: str | None = None
    verify_ssl: bool = True
    repository: str = "published"
    _session: requests.Session | None = field(default=None, repr=False)

    @classmethod
    def from_settings(cls, settings: AAPSettings) -> CollectionManager:
        """Create a CollectionManager from AAP settings.

        Args:
            settings: AAP configuration settings

        Returns:
            Configured CollectionManager instance
        """
        if not settings.is_galaxy_enabled():
            return cls()

        # Extract token value from SecretStr
        token_value: str | None = None
        if settings.oauth_token is not None:
            token_value = settings.oauth_token.get_secret_value()

        return cls(
            galaxy_url=settings.galaxy_url,
            token=token_value,
            verify_ssl=settings.verify_ssl,
            repository=settings.galaxy_repository,
        )

    def _get_session(self) -> requests.Session:
        """Get or create configured HTTP session."""
        if self._session is not None:
            return self._session

        self._session = self._create_session()
        return self._session

    def _create_session(self) -> requests.Session:
        """Create and configure HTTP session."""
        session = requests.Session()
        if self.token:
            session.headers["Authorization"] = f"Bearer {self.token}"
        if not self.verify_ssl:
            session.verify = False
        return session

    @property
    def is_private_hub_enabled(self) -> bool:
        """Check if Private Hub is configured."""
        return bool(self.galaxy_url and self.token)

    @property
    def _url_builder(self) -> GalaxyURLBuilder:
        """Get URL builder for Galaxy API."""
        return GalaxyURLBuilder(
            base_url=self.galaxy_url or "", repository=self.repository
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def install_from_requirements(self, requirements_file: Path) -> list[InstallResult]:
        """Install all collections from a requirements.yml file.

        Args:
            requirements_file: Path to requirements.yml

        Returns:
            List of installation results
        """
        slog = logger.bind(service="collection_manager")

        if not requirements_file.exists():
            slog.warning(f"Requirements file not found: {requirements_file}")
            return []

        collections = self._parse_requirements(requirements_file, slog)
        if not collections:
            return []

        slog.info(f"Installing {len(collections)} collections from {requirements_file}")

        # Use standard ansible-galaxy if no Private Hub
        if not self.is_private_hub_enabled:
            slog.info("Private Hub not configured, using ansible-galaxy")
            return self._install_all_with_galaxy(requirements_file, collections)

        # Use strategy-based installation for Private Hub
        slog.info(f"Using Private Hub: {self.galaxy_url}")
        return self._install_collections_with_strategies(collections)

    def install_collection(self, collection: CollectionSpec) -> InstallResult:
        """Install a single collection using strategy pattern.

        Args:
            collection: Collection specification

        Returns:
            Installation result
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            return self._install_single_collection(collection, Path(tmpdir))

    # -------------------------------------------------------------------------
    # Strategy-based Installation
    # -------------------------------------------------------------------------

    def _install_collections_with_strategies(
        self, collections: list[CollectionSpec]
    ) -> list[InstallResult]:
        """Install collections using strategy pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            return [self._install_single_collection(c, tmppath) for c in collections]

    def _install_single_collection(
        self, collection: CollectionSpec, tmpdir: Path
    ) -> InstallResult:
        """Install single collection trying strategies in order."""
        slog = logger.bind(service="collection_manager", collection=collection.fqcn)

        # Try Private Hub first (if enabled)
        if self.is_private_hub_enabled:
            result = self._try_private_hub_install(collection, tmpdir, slog)
            if result is not None:
                return result

        # Try public Galaxy
        result = self._try_public_galaxy_install(collection, slog)
        if result is not None:
            return result

        # Not found anywhere
        return InstallResult.not_found(collection)

    def _try_private_hub_install(
        self, collection: CollectionSpec, tmpdir: Path, slog
    ) -> InstallResult | None:
        """Attempt Private Hub install. Returns None to try next strategy."""
        download_info = self._get_download_info(collection)
        if download_info is None:
            slog.debug(f"{collection.fqcn} not found in Private Hub")
            return None

        slog.info(f"Found {collection.fqcn} v{download_info.version} in Private Hub")

        try:
            tarball = self._download_tarball(
                download_info.url, tmpdir, collection, download_info.version
            )
            if self._install_tarball(tarball):
                return InstallResult.private_hub_success(
                    collection, download_info.version
                )
            slog.warning(f"Tarball install failed for {collection.fqcn}")
            return None

        except requests.RequestException as e:
            slog.warning(f"Download failed for {collection.fqcn}: {e}")
            return None
        except subprocess.SubprocessError as e:
            slog.warning(f"Install failed for {collection.fqcn}: {e}")
            return None

    def _try_public_galaxy_install(
        self, collection: CollectionSpec, slog
    ) -> InstallResult | None:
        """Attempt public Galaxy install. Returns None if failed."""
        slog.info(f"Trying public Galaxy for {collection.fqcn}")

        if self._install_from_galaxy(collection):
            return InstallResult.public_galaxy_success(collection)

        slog.debug(f"{collection.fqcn} not found in public Galaxy")
        return None

    # -------------------------------------------------------------------------
    # Requirements Parsing
    # -------------------------------------------------------------------------

    def _parse_requirements(
        self, requirements_file: Path, slog
    ) -> list[CollectionSpec]:
        """Parse collections from requirements.yml."""
        with requirements_file.open() as f:
            data = yaml.safe_load(f) or {}

        collections_data = data.get("collections", [])
        if not collections_data:
            slog.info("No collections in requirements.yml")
            return []

        # Use list comprehension with filter
        parsed = [CollectionSpec.from_requirement(item) for item in collections_data]
        valid = [spec for spec in parsed if spec is not None]

        invalid_count = len(parsed) - len(valid)
        if invalid_count > 0:
            slog.warning(f"Skipped {invalid_count} invalid collection specs")

        return valid

    # -------------------------------------------------------------------------
    # Galaxy API Interaction
    # -------------------------------------------------------------------------

    def _get_download_info(self, collection: CollectionSpec) -> DownloadInfo | None:
        """Get download info from Private Hub API."""
        if not self.galaxy_url:
            return None

        metadata = self._fetch_collection_metadata(collection)
        if metadata is None:
            return None

        version = self._resolve_version(collection, metadata)
        if version is None:
            return None

        return self._fetch_version_download_url(collection, version)

    def _fetch_collection_metadata(
        self, collection: CollectionSpec
    ) -> CollectionMetadata | None:
        """Fetch collection metadata from Galaxy API."""
        url = self._url_builder.collection_url(collection.namespace, collection.name)

        try:
            resp = self._get_session().get(url)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return CollectionMetadata.from_json(resp.json())

        except requests.HTTPError:
            return None
        except requests.RequestException:
            return None

    def _resolve_version(
        self, collection: CollectionSpec, metadata: CollectionMetadata
    ) -> str | None:
        """Resolve which version to install."""
        # Explicit version specified - use it
        if collection.version:
            return collection.version

        # Use highest version from metadata
        if metadata.highest_version is None:
            return None

        return metadata.highest_version.version

    def _fetch_version_download_url(
        self, collection: CollectionSpec, version: str
    ) -> DownloadInfo | None:
        """Fetch download URL for specific version."""
        url = self._url_builder.version_url(
            collection.namespace, collection.name, version
        )

        try:
            resp = self._get_session().get(url)
            resp.raise_for_status()
            details = VersionDetails.from_json(resp.json())

            if details.download_url is None:
                return None

            return DownloadInfo(url=details.download_url, version=version)

        except requests.HTTPError:
            return None
        except requests.RequestException:
            return None

    # -------------------------------------------------------------------------
    # Installation Execution
    # -------------------------------------------------------------------------

    def _install_all_with_galaxy(
        self, requirements_file: Path, collections: list[CollectionSpec]
    ) -> list[InstallResult]:
        """Install all collections using standard ansible-galaxy."""
        cmd = [
            "ansible-galaxy",
            "collection",
            "install",
            "-r",
            str(requirements_file),
            "--force",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False
            )
            success = result.returncode == 0
            source = "public_galaxy" if success else f"failed: {result.stderr[:100]}"
            return [
                InstallResult(collection=c, success=success, source=source)
                for c in collections
            ]

        except subprocess.TimeoutExpired:
            return [InstallResult.failed(c, "timeout") for c in collections]

    def _download_tarball(
        self,
        download_url: str,
        output_dir: Path,
        collection: CollectionSpec,
        version: str,
    ) -> Path:
        """Download collection tarball from Private Hub."""
        output_path = (
            output_dir / f"{collection.namespace}-{collection.name}-{version}.tar.gz"
        )
        resp = self._get_session().get(download_url, stream=True)
        resp.raise_for_status()

        with output_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return output_path

    def _install_tarball(self, tarball_path: Path) -> bool:
        """Install collection from local tarball."""
        cmd = ["ansible-galaxy", "collection", "install", str(tarball_path), "--force"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
        return result.returncode == 0

    def _install_from_galaxy(self, collection: CollectionSpec) -> bool:
        """Install collection from public Galaxy."""
        cmd = [
            "ansible-galaxy",
            "collection",
            "install",
            collection.spec_string,
            "--force",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, check=False
        )
        return result.returncode == 0
