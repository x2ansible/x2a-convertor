"""Cleanup agent for Ansible analysis workflow.

This module contains the agent that cleans up the migration
specification after validation notes have been appended.
"""

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.inputs.ansible.state import AnsibleAnalysisState
from src.types.telemetry import AgentMetrics


class CleanupAgent(BaseAgent[AnsibleAnalysisState]):
    """Agent that cleans up the migration specification.

    Uses direct LLM invocation (no tools) to consolidate and clean
    the specification after validation notes have been appended.
    """

    _NAME = "Ansible Analysis Cleanup"

    SYSTEM_PROMPT_NAME = "ansible_analysis_cleanup_system"
    USER_PROMPT_NAME = "ansible_analysis_cleanup_task"

    def execute(
        self, state: AnsibleAnalysisState, metrics: AgentMetrics | None
    ) -> AnsibleAnalysisState:
        """Clean up the specification with validation updates."""
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
