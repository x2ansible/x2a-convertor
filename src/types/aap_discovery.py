"""AAP Discovery result types.

This module contains the result types for AAP Private Automation Hub discovery.
The discovery step queries AAP for existing collections that can be reused
during migration, enabling deduplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel, Field


class ExtractedCollectionRef(BaseModel):
    """A collection reference extracted from discovery content by LLM."""

    namespace: str = Field(description="Collection namespace (e.g., 'redhat')")
    name: str = Field(description="Collection name (e.g., 'rhel_system_roles')")
    reason: str = Field(
        default="",
        description="Why this collection is relevant to the migration",
    )

    @property
    def fqcn(self) -> str:
        """Fully Qualified Collection Name."""
        return f"{self.namespace}.{self.name}"


class CollectionExtractionOutput(BaseModel):
    """LLM structured output for extracting collections from discovery content."""

    collections: list[ExtractedCollectionRef] = Field(
        default_factory=list,
        description="List of collections found in the discovery content",
    )


@dataclass(frozen=True)
class DiscoveredCollection:
    """A collection discovered in AAP Private Automation Hub.

    Contains structured data about the collection including version,
    which is used to generate requirements.yml with pinned versions.
    """

    namespace: str
    name: str
    version: str
    description: str = ""
    roles: tuple[str, ...] = ()

    @property
    def fqcn(self) -> str:
        """Fully Qualified Collection Name."""
        return f"{self.namespace}.{self.name}"

    def to_requirements_entry(self) -> dict:
        """Convert to requirements.yml entry format."""
        return {
            "name": self.fqcn,
            "version": self.version,
        }


@dataclass(frozen=True)
class AAPDiscoveryResult:
    """Result of AAP discovery step.

    Contains both markdown output for display and structured collection data
    for generating requirements.yml with proper versions.

    The write agent can use `requirements_yaml` directly if available,
    ensuring Private Hub collections are properly versioned.
    """

    enabled: bool
    content: str = ""
    error: str | None = None
    collections: tuple[DiscoveredCollection, ...] = field(default_factory=tuple)
    requirements_yaml: str = ""

    @classmethod
    def disabled(cls) -> AAPDiscoveryResult:
        """Create a result indicating discovery was disabled."""
        return cls(enabled=False, content="AAP discovery disabled (not configured).")

    @classmethod
    def failed(cls, error: str) -> AAPDiscoveryResult:
        """Create a result indicating discovery failed."""
        return cls(enabled=False, error=error, content=f"AAP discovery failed: {error}")

    @classmethod
    def success(
        cls,
        content: str,
        collections: list[DiscoveredCollection] | None = None,
    ) -> AAPDiscoveryResult:
        """Create a successful result with discovery content and collections.

        Args:
            content: Markdown content describing discovered collections
            collections: List of discovered collections with versions

        Returns:
            AAPDiscoveryResult with requirements_yaml generated from collections
        """
        collections = collections or []

        # Generate requirements.yaml content
        requirements_yaml = ""
        if collections:
            requirements_data = {
                "collections": [c.to_requirements_entry() for c in collections]
            }
            yaml_str = str(
                yaml.dump(requirements_data, default_flow_style=False, sort_keys=False)
            )
            requirements_yaml = "---\n" + yaml_str

        return cls(
            enabled=True,
            content=content,
            collections=tuple(collections),
            requirements_yaml=requirements_yaml,
        )

    def to_markdown(self) -> str:
        """Return the discovery result as markdown."""
        return self.content

    @property
    def has_collections(self) -> bool:
        """Check if any collections were discovered."""
        return len(self.collections) > 0
