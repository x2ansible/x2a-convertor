"""Priorities generation agent for init workflow.

This module contains the agent that reads organizational rules from
the rules/ directory and generates INPUT-AGENTS.md and EXPORT-AGENTS.md
files with phase-specific priorities for downstream agents.

The source technology is determined by the MetadataExtractionAgent
which runs before this agent in the workflow.
"""

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.const import EXPORT_AGENTS_FILE, INPUT_AGENTS_FILE
from src.init.init_state import InitState
from src.types.priorities import PrioritiesOutput
from src.types.rule_file import RuleCollection
from src.types.technology import Technology
from src.types.telemetry import AgentMetrics


class PrioritiesGenerationAgent(BaseAgent[InitState]):
    """Agent that generates phase-specific priorities from organizational rules.

    Reads rules/*.md files and uses the source technology from state
    (set by MetadataExtractionAgent) to produce INPUT-AGENTS.md and
    EXPORT-AGENTS.md with relevant priorities.
    """

    _NAME = "Priorities Generator"

    RULES_DIRECTORY = "rules"
    SYSTEM_PROMPT_NAME = "init_priorities_generation_system"
    USER_PROMPT_NAME = "init_priorities_generation_task"

    def execute(self, state: InitState, metrics: AgentMetrics | None) -> InitState:
        """Generate priorities files from organizational rules.

        Args:
            state: Current init state with source_technology from metadata extraction
            metrics: Telemetry metrics collector

        Returns:
            Updated state (unchanged, priorities are written to files)
        """
        rules = RuleCollection.from_directory(self.RULES_DIRECTORY)
        if rules.is_empty():
            self._log.info("No rules found, skipping priorities generation")
            return state

        if not state.migration_plan_content:
            self._log.warning(
                "No migration plan content, skipping priorities generation"
            )
            return state

        technology = state.source_technology or Technology.CHEF
        self._log.info(f"Using source technology: {technology.value}")

        messages = self._build_messages(
            state.migration_plan_content, rules, technology.value
        )
        response = self.invoke_structured(PrioritiesOutput, messages, metrics)
        if not response:
            self._log.warning(
                "No response from LLM, skipping priorities file generation"
            )
            return state

        response.write_input_file(INPUT_AGENTS_FILE)
        response.write_export_file(EXPORT_AGENTS_FILE)
        self._record_metrics(metrics, response)

        return state

    def _build_messages(
        self,
        migration_plan_content: str,
        rules: RuleCollection,
        technology: str,
    ) -> list[dict[str, str]]:
        """Build LLM messages for priorities generation.

        Args:
            migration_plan_content: Full migration plan text
            rules: Collection of organizational rule files
            technology: Source technology name from metadata

        Returns:
            List of system and user message dicts
        """
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format(
            source_technology=technology,
        )
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            migration_plan_content=migration_plan_content,
            rules=rules.to_document(),
            source_technology=technology,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

    def _record_metrics(
        self, metrics: AgentMetrics | None, response: PrioritiesOutput
    ) -> None:
        """Record telemetry metrics for the generation.

        Args:
            metrics: Telemetry metrics collector (may be None)
            response: Structured output from the LLM
        """
        if not metrics:
            return

        metrics.record_metric(
            "input_priorities_sections", len(response.input_priorities)
        )
        metrics.record_metric(
            "export_priorities_sections", len(response.export_priorities)
        )
