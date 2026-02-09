"""AAP Galaxy tools for discovering collections in Private Automation Hub.

These tools allow agents to explore and discover collections in AAP's
Private Automation Hub (Galaxy API) for deduplication during migration.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.config import AAPSettings, get_settings
from src.publishers.galaxy_client import GalaxyClient
from tools.base_tool import X2ATool


class SearchCollectionsInput(BaseModel):
    """Input schema for searching collections."""

    keywords: list[str] = Field(
        description="Keywords to search for (e.g., ['nginx', 'redis', 'security'])"
    )


class GetCollectionDetailInput(BaseModel):
    """Input schema for getting collection details."""

    namespace: str = Field(description="Collection namespace (e.g., 'ansible')")
    name: str = Field(description="Collection name (e.g., 'netcommon')")


def _get_client(settings: AAPSettings | None = None) -> GalaxyClient | None:
    """Get Galaxy client if configured."""
    s = settings or get_settings().aap
    if s.is_galaxy_enabled():
        return GalaxyClient(s)
    return None


def _check_enabled(settings: AAPSettings | None = None) -> str | None:
    """Check if Galaxy is enabled. Returns error message if not."""
    s = settings or get_settings().aap
    if not s.is_galaxy_enabled():
        return (
            "AAP Galaxy is not configured. Set AAP_CONTROLLER_URL and AAP_OAUTH_TOKEN."
        )
    return None


class AAPListCollectionsTool(X2ATool):
    """Tool to list all collections in AAP Private Hub."""

    name: str = "aap_list_collections"
    description: str = (
        "List all available collections in the AAP Private Automation Hub. "
        "Returns a summary of each collection with namespace, name, version, and description. "
        "Use this to get an overview of what's available before searching for specific collections."
    )

    # pyrefly: ignore
    def _run(self) -> str:
        """List all collections in the configured repository."""
        self.log.info("AAPListCollectionsTool: listing all collections")

        error = _check_enabled()
        if error:
            return error

        try:
            client = _get_client()
            if client is None:
                return "Failed to create Galaxy client."
            collections = client.list_collections()

            if not collections:
                return "No collections found in the Private Automation Hub."
            # @TODO Pagination not implemented - this will be slow if many collections exist.
            lines = [f"Found {len(collections)} collections in Private Hub:\n"]
            for collection in collections:
                lines.append(collection.to_summary())

            return "\n".join(lines)

        except Exception as e:
            self.log.error(f"Error listing collections: {e}")
            return f"Error listing collections: {e}"


class AAPSearchCollectionsTool(X2ATool):
    """Tool to search collections by keywords."""

    name: str = "aap_search_collections"
    description: str = (
        "Search for collections in AAP Private Hub by keywords. "
        "Use this to find collections related to specific technologies "
        "(e.g., 'nginx', 'redis', 'postgresql') or patterns (e.g., 'security', 'monitoring'). "
        "Returns matching collections with their summaries."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = SearchCollectionsInput

    # pyrefly: ignore
    def _run(self, keywords: list[str]) -> str:
        """Search collections by keywords."""
        self.log.info(f"AAPSearchCollectionsTool: searching for {keywords}")

        error = _check_enabled()
        if error:
            return error

        if not keywords:
            return "No keywords provided. Please specify keywords to search for."

        try:
            client = _get_client()
            if client is None:
                return "Failed to create Galaxy client."
            collections = client.search_collections(keywords)

            if not collections:
                return f"No collections found matching keywords: {', '.join(keywords)}"

            lines = [
                f"Found {len(collections)} collections matching '{', '.join(keywords)}':\n"
            ]
            for collection in collections:
                lines.append(collection.to_summary())

            return "\n".join(lines)

        except Exception as e:
            self.log.error(f"Error searching collections: {e}")
            return f"Error searching collections: {e}"


class AAPGetCollectionDetailTool(X2ATool):
    """Tool to get detailed information about a collection."""

    name: str = "aap_get_collection_detail"
    description: str = (
        "Get detailed information about a specific collection including its roles, "
        "modules, and variables. Use this after finding a relevant collection to "
        "understand what it provides and how it can be used in the migration."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = GetCollectionDetailInput

    # pyrefly: ignore
    def _run(self, namespace: str, name: str) -> str:
        """Get collection details including roles and modules."""
        self.log.info(
            f"AAPGetCollectionDetailTool: getting details for {namespace}.{name}"
        )

        error = _check_enabled()
        if error:
            return error

        try:
            client = _get_client()
            if client is None:
                return "Failed to create Galaxy client."
            collection = client.get_collection_detail(namespace, name)

            if not collection:
                return f"Collection '{namespace}.{name}' not found in Private Hub."

            return collection.to_markdown()

        except Exception as e:
            self.log.error(f"Error getting collection details: {e}")
            return f"Error getting collection details: {e}"
