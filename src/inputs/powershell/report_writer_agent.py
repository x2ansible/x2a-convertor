"""Report writer agent for PowerShell analysis workflow.

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
from src.inputs.powershell.state import PowerShellAnalysisState
from src.types.telemetry import AgentMetrics


class ReportWriterAgent(BaseAgent[PowerShellAnalysisState]):
    """Agent that generates migration specification from PowerShell analysis.

    Uses file management tools to explore the source and generates
    a detailed migration specification based on the structured analysis.
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
    ]

    SYSTEM_PROMPT_NAME = "powershell_analysis_system"
    USER_PROMPT_NAME = "powershell_analysis_task"

    def execute(
        self, state: PowerShellAnalysisState, metrics: AgentMetrics | None
    ) -> PowerShellAnalysisState:
        """Generate migration specification using structured analysis."""
        self._log.info("Generating migration specification")

        file_listing = self._build_file_listing(state)
        messages = self._build_messages(state, file_listing)

        result = self.invoke_react(state, messages, metrics)

        response_messages = result.get("messages", [])
        if len(response_messages) < 2:
            return state.mark_failed("Invalid response from PowerShell agent")

        self._log.info("Migration specification generated")
        return state.update(specification=response_messages[-1].content)

    def _build_file_listing(self, state: PowerShellAnalysisState) -> str:
        """Build file listing from structured analysis."""
        if not state.structured_analysis:
            return ""
        return "\n".join(state.structured_analysis.analyzed_file_paths)

    def _build_messages(
        self,
        state: PowerShellAnalysisState,
        file_listing: str,
    ) -> list[dict[str, str]]:
        """Build LLM messages for report generation."""
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            path=state.path,
            user_message=state.user_message,
            directory_listing=file_listing,
            execution_summary=state.execution_summary,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
