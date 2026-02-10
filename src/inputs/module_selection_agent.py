"""Module selection agent for analyze workflow.

This module contains the agent that selects which module to migrate
based on user input and LLM analysis of the migration plan.
"""

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.inputs.analyze_state import MigrationState, ModuleSelection
from src.types.telemetry import AgentMetrics
from src.utils.technology import Technology


class ModuleSelectionAgent(BaseAgent[MigrationState]):
    """Agent that selects module to migrate based on user input and LLM analysis.

    Uses structured output to parse user requirements against the migration plan
    and identify the target module path, technology, and name.
    """

    SYSTEM_PROMPT_NAME = "analyze_select_module_system"
    USER_PROMPT_NAME = "analyze_select_module_task"

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

        normalized_path = self._normalize_path(response.path)
        technology = Technology(response.technology)

        self._record_metrics(metrics, technology, normalized_path)

        self._log.info(
            f"Selected path: '{normalized_path}' technology: '{technology.value}'"
        )

        return state.update(
            path=normalized_path,
            technology=technology,
            name=response.name,
        )

    def _build_messages(self, state: MigrationState) -> list[dict[str, str]]:
        """Build LLM messages for module selection."""
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
