"""AAP Discovery Agent for finding reusable collections.

This agent queries AAP Private Automation Hub to discover collections
that are relevant to the current migration, enabling deduplication.

After LLM discovery, it uses LLM structured output to extract collection
references and GalaxyClient to get exact versions for requirements.yml.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.config import get_settings
from src.exporters.base_agent import BaseAgent
from src.exporters.state import ChefState
from src.model import (
    get_last_ai_message,
    get_model,
    get_runnable_config,
    report_tool_calls,
)
from src.publishers.galaxy_client import AAPCollection, GalaxyClient
from src.types.aap_discovery import (
    AAPDiscoveryResult,
    CollectionExtractionOutput,
    DiscoveredCollection,
    ExtractedCollectionRef,
)
from src.utils.logging import get_logger
from tools.aap_galaxy import (
    AAPGetCollectionDetailTool,
    AAPListCollectionsTool,
    AAPSearchCollectionsTool,
)

logger = get_logger(__name__)


# =============================================================================
# Value Objects
# =============================================================================


@dataclass(frozen=True)
class VerificationResult:
    """Result of verifying a single collection."""

    ref: ExtractedCollectionRef
    collection: DiscoveredCollection | None
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if verification succeeded."""
        return self.collection is not None

    @classmethod
    def found(
        cls, ref: ExtractedCollectionRef, collection: DiscoveredCollection
    ) -> VerificationResult:
        """Create successful verification result."""
        return cls(ref=ref, collection=collection)

    @classmethod
    def not_found(cls, ref: ExtractedCollectionRef) -> VerificationResult:
        """Create not found result."""
        return cls(ref=ref, collection=None)

    @classmethod
    def failed(cls, ref: ExtractedCollectionRef, error: str) -> VerificationResult:
        """Create failed result with error."""
        return cls(ref=ref, collection=None, error=error)


# =============================================================================
# Agent
# =============================================================================


class AAPDiscoveryAgent(BaseAgent):
    """Agent that discovers relevant collections in AAP Private Automation Hub.

    This agent uses Galaxy tools to explore the Private Hub and find collections
    that are relevant to the current migration, enabling deduplication.

    The agent:
    1. Analyzes the migration plan to understand what's being migrated
    2. Searches for relevant collections using keywords
    3. Gets detailed information about promising collections
    4. Extracts structured collection data with versions
    5. Returns collections that can be reused in the migration
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: AAPListCollectionsTool(),
        lambda: AAPSearchCollectionsTool(),
        lambda: AAPGetCollectionDetailTool(),
    ]

    SYSTEM_PROMPT_NAME = "export_aap_discovery_system"
    USER_PROMPT_NAME = "export_aap_discovery_task"
    EXTRACTION_PROMPT_NAME = "export_aap_extract_collections"

    def __init__(self, model=None) -> None:
        super().__init__(model)
        self._settings = get_settings().aap
        self._extraction_model = model or get_model()

    def __call__(self, state: ChefState) -> ChefState:
        """Execute AAP discovery and update state with results.

        Args:
            state: Current migration state

        Returns:
            Updated ChefState with aap_discovery populated
        """
        slog = logger.bind(phase="aap_discovery")

        if not self._settings.is_galaxy_enabled():
            slog.info("AAP discovery skipped (not configured)")
            return state.update(aap_discovery=AAPDiscoveryResult.disabled())

        slog.info("Starting AAP collection discovery")

        try:
            discovery_content = self._run_discovery_agent(state, slog)
            collections = self._extract_and_verify_collections(discovery_content, slog)

            self._log_discovery_results(collections, slog)

            return state.update(
                aap_discovery=AAPDiscoveryResult.success(discovery_content, collections)
            )

        except Exception as e:
            slog.warning(f"AAP discovery failed: {e}")
            return state.update(aap_discovery=AAPDiscoveryResult.failed(str(e)))

    # -------------------------------------------------------------------------
    # Discovery Execution
    # -------------------------------------------------------------------------

    def _run_discovery_agent(self, state: ChefState, slog) -> str:
        """Run the discovery agent to find relevant collections."""
        agent = self._create_react_agent(state)

        system_prompt = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            module=state.module,
            high_level_migration_plan=state.high_level_migration_plan.content,
            migration_plan=state.module_migration_plan.content,
        )

        result = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            },
            get_runnable_config(),
        )
        slog.info(f"Discovery agent tools: {report_tool_calls(result).to_string()}")

        message = get_last_ai_message(result)
        if message is None:
            return ""
        return str(message.content)

    # -------------------------------------------------------------------------
    # Collection Extraction
    # -------------------------------------------------------------------------

    def _extract_and_verify_collections(
        self, content: str, slog
    ) -> list[DiscoveredCollection]:
        """Extract collection references and verify them in Private Hub."""
        refs = self._extract_collection_refs(content, slog)
        if not refs:
            return []

        slog.debug(
            f"LLM extracted {len(refs)} collection references: {[r.fqcn for r in refs]}"
        )

        return self._verify_collections(refs, slog)

    def _extract_collection_refs(
        self, content: str, slog
    ) -> list[ExtractedCollectionRef]:
        """Extract collection references from LLM output using structured output."""
        extraction_prompt = get_prompt(self.EXTRACTION_PROMPT_NAME).format(
            discovery_content=content
        )

        try:
            structured_model = self._extraction_model.with_structured_output(
                CollectionExtractionOutput
            )
            extraction_result = structured_model.invoke(
                extraction_prompt, config=get_runnable_config()
            )
            # Type guard: structured output should return CollectionExtractionOutput
            if isinstance(extraction_result, CollectionExtractionOutput):
                return extraction_result.collections
            return []

        except Exception as e:
            slog.warning(f"LLM extraction failed: {e}")
            return []

    # -------------------------------------------------------------------------
    # Collection Verification (Functional Pattern)
    # -------------------------------------------------------------------------

    def _verify_collections(
        self, refs: list[ExtractedCollectionRef], slog
    ) -> list[DiscoveredCollection]:
        """Verify collections exist in Private Hub using functional map/filter."""
        client = self._create_galaxy_client(slog)
        if client is None:
            return []

        # Map: verify each reference
        verification_results = [
            self._verify_single_collection(ref, client, slog) for ref in refs
        ]

        # Filter: keep only successful verifications (collection is non-None when success)
        return [
            r.collection
            for r in verification_results
            if r.success and r.collection is not None
        ]

    def _create_galaxy_client(self, slog) -> GalaxyClient | None:
        """Create Galaxy client for verification."""
        try:
            return GalaxyClient(self._settings)
        except Exception as e:
            slog.warning(f"Could not create GalaxyClient: {e}")
            return None

    def _verify_single_collection(
        self, ref: ExtractedCollectionRef, client: GalaxyClient, slog
    ) -> VerificationResult:
        """Verify a single collection exists in Private Hub."""
        try:
            detail = client.get_collection_detail(ref.namespace, ref.name)
            if detail is None:
                slog.warning(f"{ref.fqcn} not found in Private Hub, skipping")
                return VerificationResult.not_found(ref)

            collection = self._to_discovered_collection(ref, detail)
            slog.debug(f"Verified {ref.fqcn} v{detail.version} in Private Hub")
            return VerificationResult.found(ref, collection)

        except Exception as e:
            slog.debug(f"Error fetching {ref.fqcn}: {e}")
            return VerificationResult.failed(ref, str(e))

    def _to_discovered_collection(
        self, ref: ExtractedCollectionRef, detail: AAPCollection
    ) -> DiscoveredCollection:
        """Transform API detail to DiscoveredCollection (pure function)."""
        return DiscoveredCollection(
            namespace=ref.namespace,
            name=ref.name,
            version=detail.version,
            description=detail.description,
            roles=tuple(r.name for r in detail.roles),
        )

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------

    def _log_discovery_results(
        self, collections: list[DiscoveredCollection], slog
    ) -> None:
        """Log discovery results summary."""
        if collections:
            slog.info(
                f"Discovered {len(collections)} collections: "
                f"{', '.join(c.fqcn for c in collections)}"
            )
            return

        slog.info("No Private Hub collections discovered")
