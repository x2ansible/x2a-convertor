"""Report writer agent for Chef analysis workflow.

This module contains the ReAct agent that generates migration
specifications using structured analysis and file exploration tools.
"""

from collections.abc import Callable
from typing import ClassVar

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.inputs.chef.state import ChefState
from src.inputs.tree_analysis import TreeSitterAnalyzer
from src.types.telemetry import AgentMetrics


class ReportWriterAgent(BaseAgent[ChefState]):
    """Agent that generates migration specification using structured analysis.

    Uses file management tools to explore the cookbook and generates
    a detailed migration specification based on the structured analysis.
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
    ]

    SYSTEM_PROMPT_NAME = "chef_analysis_system"
    USER_PROMPT_NAME = "chef_analysis_task"

    def execute(self, state: ChefState, metrics: AgentMetrics | None) -> ChefState:
        """Generate migration specification using structured analysis.

        Args:
            state: Current chef state with structured_analysis and execution_tree_summary
            metrics: Telemetry metrics collector

        Returns:
            Updated state with specification set, or marked failed on invalid response
        """
        self._log.info("Generating migration specification")

        data_list = self._build_file_listing(state)
        tree_sitter_report = self._generate_tree_sitter_report(state.path)

        messages = self._build_messages(state, data_list, tree_sitter_report)

        result = self.invoke_react(state, messages, metrics)

        response_messages = result.get("messages", [])
        if len(response_messages) < 2:
            return state.mark_failed("Invalid response from Chef agent")

        self._log.info("Migration specification generated")
        return state.update(specification=response_messages[-1].content)

    def _build_file_listing(self, state: ChefState) -> str:
        """Build file listing from structured analysis."""
        if not state.structured_analysis:
            return ""
        return "\n".join(state.structured_analysis.analyzed_file_paths)

    def _generate_tree_sitter_report(self, path: str) -> str:
        """Generate tree-sitter analysis report for the cookbook."""
        analyzer = TreeSitterAnalyzer()
        try:
            return analyzer.report_directory(path)
        except Exception as e:
            self._log.warning(f"Failed to generate tree-sitter report: {e}")
            return "Tree-sitter analysis not available"

    def _build_messages(
        self,
        state: ChefState,
        data_list: str,
        tree_sitter_report: str,
    ) -> list[dict[str, str]]:
        """Build LLM messages for report generation."""
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            path=state.path,
            user_message=state.user_message,
            directory_listing=data_list,
            tree_sitter_report=tree_sitter_report,
            execution_tree=state.execution_tree_summary,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
