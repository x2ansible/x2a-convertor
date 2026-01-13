"""AAP Private Automation Hub (Galaxy) REST API client.

This module provides a client for discovering collections in AAP's Private
Automation Hub. It extends BaseAAPClient to share authentication and SSL
configuration with the Controller API client.

Galaxy API endpoints:
- /api/galaxy/content/{repository}/v3/collections/
- /api/galaxy/content/{repository}/v3/collections/{namespace}/{name}/
- /api/galaxy/content/{repository}/v3/collections/{namespace}/{name}/versions/{version}/
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests
from jinja2 import Template

from src.config import AAPSettings
from src.publishers.base_client import BaseAAPClient
from src.utils.logging import get_logger
from src.utils.text import html_to_markdown

logger = get_logger(__name__)

# Jinja template for brief collection summary (used in lists)
COLLECTION_SUMMARY_TEMPLATE = Template(
    """
- {{ collection.fqcn }} (v{{ collection.version }})
  Description: {{ collection.description }}
{% if collection.roles %}
  Roles: {{ collection.roles[:5] | map(attribute='name') | join(', ') }}{% if collection.roles | length > 5 %} ... and {{ collection.roles | length - 5 }} more{% endif %}

{% endif %}
{% if collection.modules %}
  Modules: {{ collection.modules[:5] | map(attribute='name') | join(', ') }}{% if collection.modules | length > 5 %} ... and {{ collection.modules | length - 5 }} more{% endif %}

{% endif %}
""".strip()
)

# Jinja template for full collection markdown (used in details)
COLLECTION_MARKDOWN_TEMPLATE = Template(
    """
## Collection: {{ collection.fqcn }} (v{{ collection.version }})

**Description**: {{ collection.description }}

### Installation

```bash
{{ collection.install_command }}
```
{% if collection.download_url %}
**Download URL**: {{ collection.download_url }}
{% endif %}
{% if collection.repository_url %}
**Repository**: {{ collection.repository_url }}
{% endif %}
{% if collection.roles %}

### Available Roles:
{% for role in collection.roles %}

#### Role: `{{ collection.fqcn }}.{{ role.name }}`

{{ role.description }}
{% if role.readme_markdown %}

{{ role.readme_markdown }}
{% endif %}
{% endfor %}
{% endif %}
{% if collection.modules %}

### Available Modules:
{% for mod in collection.modules %}
- `{{ collection.fqcn }}.{{ mod.name }}`: {{ mod.description }}
{% endfor %}
{% endif %}
{% if collection.dependencies %}

### Dependencies:
{% for dep, ver in collection.dependencies.items() %}
- `{{ dep }}`: {{ ver }}
{% endfor %}
{% endif %}
{% if collection.collection_readme_markdown %}

### Collection Documentation

{{ collection.collection_readme_markdown }}
{% endif %}
""".strip()
)


@dataclass(frozen=True)
class CollectionRole:
    """A role within a collection."""

    name: str
    description: str
    readme_markdown: str = ""


@dataclass(frozen=True)
class CollectionModule:
    """A module/plugin within a collection."""

    name: str
    description: str
    module_type: str = "module"


@dataclass(frozen=True)
class CollectionContents:
    """Parsed contents from a collection version."""

    roles: tuple[CollectionRole, ...]
    modules: tuple[CollectionModule, ...]
    description: str
    collection_readme_markdown: str

    @classmethod
    def empty(cls) -> CollectionContents:
        """Return empty contents."""
        return cls(
            roles=(),
            modules=(),
            description="",
            collection_readme_markdown="",
        )


@dataclass(frozen=True)
class AAPCollection:
    """Represents a collection discovered in AAP with full analysis."""

    namespace: str
    name: str
    version: str
    description: str
    download_url: str = ""
    repository_url: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)
    roles: tuple[CollectionRole, ...] = field(default_factory=tuple)
    modules: tuple[CollectionModule, ...] = field(default_factory=tuple)
    collection_readme_markdown: str = ""

    @property
    def fqcn(self) -> str:
        """Fully Qualified Collection Name."""
        return f"{self.namespace}.{self.name}"

    @property
    def install_command(self) -> str:
        """Ansible Galaxy install command for this collection."""
        cmd = f"ansible-galaxy collection install {self.fqcn}:{self.version}"
        if self.repository_url:
            cmd += f" --server={self.repository_url}"
        return cmd

    def to_summary(self) -> str:
        """Render collection as brief summary for lists."""
        return COLLECTION_SUMMARY_TEMPLATE.render(collection=self)

    def to_markdown(self) -> str:
        """Render collection as full markdown details."""
        return COLLECTION_MARKDOWN_TEMPLATE.render(collection=self)

    @classmethod
    def from_api(
        cls,
        namespace: str,
        name: str,
        version_data: dict[str, Any],
        contents: CollectionContents,
        repository_url: str = "",
    ) -> AAPCollection:
        """Create from Galaxy API response.

        Args:
            namespace: Collection namespace
            name: Collection name
            version_data: The highest_version dict from collection response
            contents: Parsed contents from _get_collection_contents
            repository_url: Base URL of the Galaxy repository
        """
        download_url = version_data.get("download_url", "") or version_data.get(
            "href", ""
        )
        return cls(
            namespace=namespace,
            name=name,
            version=version_data.get("version", ""),
            description=contents.description,
            download_url=download_url,
            repository_url=repository_url,
            dependencies=version_data.get("metadata", {}).get("dependencies", {}),
            roles=contents.roles,
            modules=contents.modules,
            collection_readme_markdown=contents.collection_readme_markdown,
        )


class GalaxyClient(BaseAAPClient):
    """Client for AAP Private Automation Hub Galaxy API.

    Extends BaseAAPClient to share session, auth, and SSL configuration.
    Uses Token auth format (vs Bearer for Controller API).
    """

    def __init__(self, settings: AAPSettings | None = None) -> None:
        super().__init__(settings)

    @property
    def _base_url(self) -> str:
        """Return the Galaxy API base URL."""
        url = self._settings.galaxy_url
        if not url:
            msg = "Galaxy URL not configured (AAP_CONTROLLER_URL not set)"
            raise ValueError(msg)
        return url.rstrip("/")

    @property
    def _api_prefix(self) -> str:
        """Return the Galaxy API path prefix with repository."""
        return f"/content/{self._settings.galaxy_repository}/v3"

    @property
    def _auth_header_format(self) -> str:
        """Galaxy API uses Bearer auth format (same as Controller)."""
        return "Bearer"

    def list_collections(self) -> list[AAPCollection]:
        """List all collections in the configured repository.

        Returns:
            List of collections with basic metadata (no content details).
        """
        collections: list[AAPCollection] = []
        url = self._url(self._api("/collections/"))

        while url:
            data = self._request("GET", url, use_full_url=True)
            for item in data.get("data", []):
                namespace = item.get("namespace", "")
                name = item.get("name", "")
                highest_version = item.get("highest_version", {})
                collections.append(
                    AAPCollection(
                        namespace=namespace,
                        name=name,
                        version=highest_version.get("version", ""),
                        description=item.get("description", ""),
                    )
                )
            url = data.get("links", {}).get("next")

        logger.info(
            f"Found {len(collections)} collections in repository "
            f"'{self._settings.galaxy_repository}'"
        )
        return collections

    def get_collection_detail(self, namespace: str, name: str) -> AAPCollection | None:
        """Get full details of a collection including roles and modules.

        Args:
            namespace: Collection namespace (e.g., 'ansible')
            name: Collection name (e.g., 'netcommon')

        Returns:
            Collection with full content details, or None if not found.
        """
        try:
            collection_data = self._request("GET", f"/collections/{namespace}/{name}/")

            highest_version = collection_data.get("highest_version", {})
            version = highest_version.get("version", "")

            if not version:
                return None

            contents = self._get_collection_contents(namespace, name, version)

            return AAPCollection.from_api(
                namespace=namespace,
                name=name,
                version_data=highest_version,
                contents=contents,
                repository_url=self._base_url,
            )
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def _get_collection_contents(
        self, namespace: str, name: str, version: str
    ) -> CollectionContents:
        """Fetch the contents manifest including docs_blob with README.

        Uses the Galaxy v3 API to get full documentation including role READMEs
        with variables tables.
        """
        try:
            version_data = self._request(
                "GET", f"/collections/{namespace}/{name}/versions/{version}/"
            )
            contents_list = version_data.get("metadata", {}).get("contents", [])

            docs_blob_data = self._request(
                "GET", f"/collections/{namespace}/{name}/versions/{version}/docs-blob/"
            )
            docs_blob = docs_blob_data.get("docs_blob", {})

            docs_by_name = {
                item.get("content_name"): item for item in docs_blob.get("contents", [])
            }

            roles: list[CollectionRole] = []
            modules: list[CollectionModule] = []

            for item in contents_list:
                content_type = item.get("content_type", "")
                content_name = item.get("name", "")
                description = item.get("description") or ""

                if content_type == "role":
                    doc = docs_by_name.get(content_name, {})
                    roles.append(
                        CollectionRole(
                            name=content_name,
                            description=description,
                            readme_markdown=html_to_markdown(
                                doc.get("readme_html", "")
                            ),
                        )
                    )
                elif content_type == "module":
                    modules.append(
                        CollectionModule(name=content_name, description=description)
                    )

            collection_readme = docs_blob.get("collection_readme", {})

            return CollectionContents(
                roles=tuple(roles),
                modules=tuple(modules),
                description=version_data.get("metadata", {}).get("description", ""),
                collection_readme_markdown=html_to_markdown(
                    collection_readme.get("html", "")
                ),
            )
        except Exception as e:
            logger.warning(
                f"Could not fetch contents for {namespace}.{name}:{version}: {e}"
            )
            return CollectionContents.empty()

    def search_collections(self, keywords: list[str]) -> list[AAPCollection]:
        """Search collections by keywords.

        Args:
            keywords: List of keywords to search for (nginx, redis, etc.)

        Returns:
            List of matching collections.
        """
        all_collections = self.list_collections()
        matched: list[AAPCollection] = []

        for collection in all_collections:
            searchable = (
                f"{collection.namespace} {collection.name} {collection.description}"
            ).lower()
            if any(kw.lower() in searchable for kw in keywords):
                matched.append(collection)

        return matched
