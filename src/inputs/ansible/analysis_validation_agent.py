"""Analysis validation agent for Ansible analysis workflow.

This module contains the agent that validates the migration plan
against the structured analysis from task, handler, variable, and template files.
"""

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.inputs.ansible.state import AnsibleAnalysisState
from src.types.telemetry import AgentMetrics


class AnalysisValidationAgent(BaseAgent[AnsibleAnalysisState]):
    """Agent that validates migration plan against structured analysis.

    Uses direct LLM invocation (no tools) to check consistency
    between the migration specification and the structured analysis.
    """

    SYSTEM_PROMPT_NAME = "ansible_analysis_validation_system"
    USER_PROMPT_NAME = "ansible_analysis_validation_task"

    def execute(
        self, state: AnsibleAnalysisState, metrics: AgentMetrics | None
    ) -> AnsibleAnalysisState:
        """Validate migration plan against structured analysis."""
        self._log.info("Validating migration plan against structured analysis")

        if not state.structured_analysis:
            self._log.warning("No structured analysis available, skipping validation")
            return state

        messages = self._build_messages(state)
        validation_response = self.invoke_llm(messages, metrics)

        if validation_response.startswith("VALIDATED:"):
            self._log.info("Specification validated successfully")
            return state

        self._log.info("Validation found issues, updating specification")
        updated_spec = (
            f"{state.specification}\n\n## VALIDATION NOTES ##\n{validation_response}"
        )
        return state.update(specification=updated_spec)

    def _build_messages(self, state: AnsibleAnalysisState) -> list[dict[str, str]]:
        """Build LLM messages for validation."""
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            specification=state.specification,
            analysis_summary=state.execution_summary,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
