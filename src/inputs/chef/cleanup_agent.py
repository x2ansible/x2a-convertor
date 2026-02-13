"""Cleanup agent for Chef analysis workflow.

This module contains the agent that cleans up the migration
specification after validation notes have been appended.
"""

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.inputs.chef.state import ChefState
from src.types.telemetry import AgentMetrics


class CleanupAgent(BaseAgent[ChefState]):
    """Agent that cleans up the migration specification.

    Uses direct LLM invocation (no tools) to consolidate and clean
    the specification after validation notes have been appended.
    """

    SYSTEM_PROMPT_NAME = "chef_analysis_cleanup_system"
    USER_PROMPT_NAME = "chef_analysis_cleanup_task"

    def execute(self, state: ChefState, metrics: AgentMetrics | None) -> ChefState:
        """Clean up the messy specification with validation updates.

        Args:
            state: Current chef state with specification containing validation notes
            metrics: Telemetry metrics collector

        Returns:
            Updated state with cleaned specification
        """
        self._log.info("Cleaning up migration specification")

        messages = self._build_messages(state.specification)
        cleaned = self.invoke_llm(messages, metrics)

        if not cleaned:
            self._log.warning("No valid response from cleanup agent")
            return state

        return state.update(specification=cleaned)

    def _build_messages(self, specification: str) -> list[dict[str, str]]:
        """Build LLM messages for cleanup."""
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            messy_specification=specification
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
