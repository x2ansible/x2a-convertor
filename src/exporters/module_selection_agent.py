"""Module selection agent for export workflow.

This module contains the agent that selects which module to migrate
based on user input and LLM analysis of the migration plans.
"""

from pathlib import Path

from pydantic import BaseModel

from prompts.get_prompt import get_prompt
from src.exporters.export_agent import ExportAgent
from src.exporters.state import ExportState
from src.types.telemetry import AgentMetrics
from src.utils.list_files import list_files


class SourceMetadata(BaseModel):
    """Structured output for module selection in export phase."""

    path: str


class ModuleSelectionAgent(ExportAgent[ExportState]):
    """Agent that selects module path based on user input and LLM analysis.

    Uses structured output to parse user requirements against the migration plans
    and identify the target module path.

    When generated metadata is available, uses metadata-aware prompts that
    provide the LLM with structured module information for more accurate selection.
    """

    _NAME = "Module Selector"

    SYSTEM_PROMPT_NAME = "export_source_metadata_system"
    USER_PROMPT_NAME = "export_source_metadata_task"

    def execute(self, state: ExportState, metrics: AgentMetrics | None) -> ExportState:
        """Select module path based on user input and LLM analysis.

        Args:
            state: Current export state with user_message and migration plans
            metrics: Telemetry metrics collector

        Returns:
            Updated state with path and directory_listing set, or marked as failed
        """
        self._log.info("Selecting module to migrate")

        messages = self._build_messages(state)
        response = self.invoke_structured(SourceMetadata, messages, metrics)

        self._log.debug(f"LLM module selection response: {response}")
        assert isinstance(response, SourceMetadata)

        raw_path = response.path

        if not self._is_valid_path(raw_path):
            error_msg = (
                f"Module path from the module migration plan not found: {raw_path}"
            )
            self._log.error(error_msg)
            return state.mark_failed(error_msg).update(last_output=error_msg)

        directory_listing = list_files(path=raw_path)

        self._log.info(
            f"Selected path: '{raw_path}' with {len(directory_listing)} files"
        )

        return state.update(path=raw_path, directory_listing=directory_listing)

    def _build_messages(self, state: ExportState) -> list[dict[str, str]]:
        """Build LLM messages for module selection."""

        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format(
            high_level_migration_plan=state.high_level_migration_plan.to_document(),
            module_migration_plan=state.module_migration_plan.to_document(),
        )
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            user_message=state.user_message,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

    def _is_valid_path(self, path: str) -> bool:
        """Check if the selected path exists.

        Args:
            path: Path to validate

        Returns:
            True if path exists, False otherwise
        """
        if not path:
            return False
        return Path(path).exists()
