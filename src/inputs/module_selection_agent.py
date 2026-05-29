"""Module selection agent for analyze workflow.

This module contains the agent that selects which module to migrate
based on user input and LLM analysis of the migration plan.
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.const import METADATA_FILENAME
from src.inputs.analyze_state import MigrationState, ModuleSelection
from src.inputs.input_agent import InputAgent
from src.types.document import DocumentFile
from src.types.technology import Technology
from src.types.telemetry import AgentMetrics


class ModuleSelectionAgent(InputAgent[MigrationState]):
    """Agent that selects module to migrate based on user input and LLM analysis.

    Uses structured output to parse user requirements against the migration plan
    and identify the target module path, technology, and name.

    When generated metadata is available, uses metadata-aware prompts that
    provide the LLM with structured module information for more accurate selection.
    """

    _NAME = "Module Selector"

    SYSTEM_PROMPT_NAME = "analyze_select_module_system"
    USER_PROMPT_NAME = "analyze_select_module_task"

    METADATA_SYSTEM_PROMPT_NAME = "analyze_select_module_metadata_system"
    METADATA_USER_PROMPT_NAME = "analyze_select_module_metadata_task"

    def execute(
        self, state: MigrationState, metrics: AgentMetrics | None
    ) -> MigrationState:
        """Select module to migrate based on user input and LLM analysis.

        Args:
            state: Current migration state with user_message and migration_plan_content
            metrics: Telemetry metrics collector

        Returns:
            Updated state with path, technology, and name set
        """
        self._log.info("Selecting module to migrate")

        messages = self._build_messages(state)
        response = self.invoke_structured(ModuleSelection, messages, metrics)

        self._log.debug(f"LLM select_module response: {response}")
        assert isinstance(response, ModuleSelection)

        # Check if LLM indicated module not found
        if response.name == "NOT_FOUND" or response.path == "NOT_FOUND":
            self._log.error(
                f"Module not found in available modules for request: '{state.user_message}'"
            )
            return state.mark_failed(
                f"Module '{state.user_message}' not found in available modules. "
                f"Please verify the module name and try again."
            )

        normalized_path = self._normalize_path(response.path)
        technology = response.technology
        self._record_metrics(metrics, technology, normalized_path)

        if not Path(normalized_path).exists():
            self._log.error(f"Selected module path does not exist: {normalized_path}")
            return state.mark_failed(
                f"Module path not found: '{normalized_path}'. "
                f"Verify the module name and path in the migration plan."
            )

        self._log.info(
            f"Selected path: '{normalized_path}' technology: '{technology.value}'"
        )

        return state.update(
            path=normalized_path,
            technology=technology,
            name=response.name,
        )

    @property
    def generated_metadata(self) -> str | None:
        """Read generated project metadata JSON if available."""
        try:
            doc = DocumentFile.from_path(METADATA_FILENAME)
            return doc.content
        except ValueError:
            self._log.debug("No generated metadata file found, using migration plan")
            return None

    def _build_messages(self, state: MigrationState) -> list[dict[str, str]]:
        """Build LLM messages for module selection.

        Uses metadata-aware prompts when generated metadata exists,
        falling back to migration-plan-based prompts otherwise.
        """
        metadata = self.generated_metadata
        if metadata:
            return self._build_metadata_messages(state, metadata)

        return self._build_plan_messages(state)

    def _build_metadata_messages(
        self, state: MigrationState, metadata: str
    ) -> list[dict[str, str]]:
        """Build messages using metadata-aware prompts."""
        self._log.info("Using generated metadata for module selection")
        system_message = get_prompt(self.METADATA_SYSTEM_PROMPT_NAME).format(
            modules_json=metadata
        )
        user_prompt = get_prompt(self.METADATA_USER_PROMPT_NAME).format(
            user_message=state.user_message
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

    def _build_plan_messages(self, state: MigrationState) -> list[dict[str, str]]:
        """Build messages using migration-plan-based prompts."""
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format(
            migration_plan_content=state.migration_plan_content
        )
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            user_message=state.user_message
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

    def _normalize_path(self, raw_path: str) -> str:
        """Normalize path: convert absolute to relative, strip trailing slash."""
        if raw_path.startswith("/"):
            raw_path = f".{raw_path}"

        if raw_path.endswith("/") and len(raw_path) > 1:
            raw_path = raw_path.rstrip("/")

        return raw_path

    def _record_metrics(
        self,
        metrics: AgentMetrics | None,
        technology: Technology,
        path: str,
    ) -> None:
        """Record telemetry metrics for the selection."""
        if not metrics:
            return
        metrics.record_metric("technology", technology.value)
        metrics.record_metric("path", path)
