"""Metadata extraction agent for init workflow.

This module contains the agent that extracts module metadata
from a migration plan using structured LLM output.
"""

import json
from pathlib import Path

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.const import METADATA_FILENAME
from src.init.init_state import InitState
from src.types import MetadataCollection
from src.types.telemetry import AgentMetrics


class MetadataExtractionAgent(BaseAgent[InitState]):
    """Agent that extracts module metadata from migration plan.

    Uses structured output to parse the migration plan content
    and generate generated-project-metadata.json.
    """

    SYSTEM_PROMPT_NAME = "init_metadata_extraction_system"
    USER_PROMPT_NAME = "init_metadata_extraction_task"

    def execute(self, state: InitState, metrics: AgentMetrics | None) -> InitState:
        """Extract metadata from migration plan using structured output.

        Args:
            state: Current init state with migration_plan_content
            metrics: Telemetry metrics collector

        Returns:
            Updated state with metadata_items populated
        """
        self._log.info("Extracting module metadata from migration plan")

        if not state.migration_plan_content:
            self._log.error(
                "No migration plan content available for metadata extraction"
            )
            return state.mark_failed(
                "Cannot extract metadata: migration plan content is empty"
            )

        messages = self._build_messages(state.migration_plan_content)
        response = self.invoke_structured(MetadataCollection, messages, metrics)

        self._log.debug(f"LLM metadata extraction response: {response}")

        metadata_list = [module.model_dump() for module in response.modules]
        self._record_metrics(metrics, response, metadata_list)
        self._write_metadata_file(metadata_list)

        return state.update(metadata_items=metadata_list)

    def _build_messages(self, migration_plan_content: str) -> list[dict[str, str]]:
        """Build LLM messages for metadata extraction."""
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            migration_plan_content=migration_plan_content
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

    def _record_metrics(
        self,
        metrics: AgentMetrics | None,
        response: MetadataCollection,
        metadata_list: list[dict],
    ) -> None:
        """Record telemetry metrics for the extraction."""
        if not metrics:
            return
        metrics.record_metric("modules_found", len(response.modules))
        metrics.record_metric("metadata_modules", len(metadata_list))

    def _write_metadata_file(self, metadata_list: list[dict]) -> None:
        """Write metadata to generated-project-metadata.json."""
        metadata_file_path = Path(METADATA_FILENAME)
        with metadata_file_path.open("w") as f:
            json.dump(metadata_list, f, indent=2)

        self._log.info(
            f"Metadata file created: {METADATA_FILENAME} ({len(metadata_list)} modules)"
        )
