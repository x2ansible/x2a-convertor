"""Report writer agent for Puppet analysis workflow.

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
from src.inputs.puppet.state import PuppetState
from src.inputs.tree_analysis import TreeSitterAnalyzer
from src.types.telemetry import AgentMetrics


class ReportWriterAgent(BaseAgent[PuppetState]):
    """Agent that generates migration specification using structured analysis.

    Uses file management tools to explore the module and generates
    a detailed migration specification based on the structured analysis.
    """

    _NAME = "Puppet Report Writer"

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
    ]

    SYSTEM_PROMPT_NAME = "puppet_analysis_system"
    USER_PROMPT_NAME = "puppet_analysis_task"

    def execute(self, state: PuppetState, metrics: AgentMetrics | None) -> PuppetState:
        self._log.info("Generating migration specification")

        data_list = self._build_file_listing(state)
        tree_sitter_report = self._generate_tree_sitter_report(state.path)
        variables_summary = state.variables_summary or "No Hiera variables detected."
        credentials_summary = self._build_credentials_summary(state)
        dependencies_summary = self._build_dependencies_summary(state)

        messages = self._build_messages(
            state,
            data_list,
            tree_sitter_report,
            variables_summary,
            credentials_summary,
            dependencies_summary,
        )

        result = self.invoke_react(state, messages, metrics)

        response_messages = result.get("messages", [])
        if len(response_messages) < 2:
            return state.mark_failed("Invalid response from Puppet agent")

        self._log.info("Migration specification generated")
        return state.update(specification=response_messages[-1].content)

    def _build_file_listing(self, state: PuppetState) -> str:
        if not state.structured_analysis:
            return ""
        return "\n".join(state.structured_analysis.analyzed_file_paths)

    def _generate_tree_sitter_report(self, path: str) -> str:
        analyzer = TreeSitterAnalyzer()
        try:
            return analyzer.report_directory(path)
        except Exception as e:
            self._log.warning(f"Failed to generate tree-sitter report: {e}")
            return "Tree-sitter analysis not available"

    def _build_credentials_summary(self, state: PuppetState) -> str:
        if not state.credentials_analysis:
            return "No credentials detected."

        lines: list[str] = []
        for cred_result in state.credentials_analysis:
            analysis = cred_result.analysis
            if analysis.total_detected == 0:
                continue
            lines.append(f"Total detected: {analysis.total_detected}")
            if analysis.provider_info:
                lines.append(f"Provider: {analysis.provider_info}")
            for cred in analysis.credentials:
                lines.append(f"\n### {cred.purpose}")
                lines.append(f"  Variables: {', '.join(cred.variable_names)}")
                lines.append(f"  Source files: {', '.join(cred.source_files)}")
                lines.append(f"  Storage: {cred.storage_method}")
                lines.append(f"  Usage: {cred.usage_context}")
                lines.append(f"  Ansible recommendation: {cred.ansible_recommendation}")

        return "\n".join(lines) if lines else "No credentials detected."

    def _build_dependencies_summary(self, state: PuppetState) -> str:
        if not state.dependency_info:
            return "No external dependencies (no Puppetfile found)."

        lines: list[str] = []
        for dep in state.dependency_info:
            source = dep.get("source", "unknown")
            version = dep.get("version", "")
            url = dep.get("url", "")
            if source == "git":
                lines.append(f"  {dep['name']} (git: {url}, ref: {version})")
            else:
                lines.append(f"  {dep['name']} (forge, version: {version})")

        return f"Found {len(state.dependency_info)} dependencies:\n" + "\n".join(lines)

    def _build_messages(
        self,
        state: PuppetState,
        data_list: str,
        tree_sitter_report: str,
        variables_summary: str,
        credentials_summary: str,
        dependencies_summary: str,
    ) -> list[dict[str, str]]:
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            path=state.path,
            user_message=state.user_message,
            directory_listing=data_list,
            tree_sitter_report=tree_sitter_report,
            execution_tree=state.execution_tree_summary,
            variables_summary=variables_summary,
            credentials_summary=credentials_summary,
            dependencies_summary=dependencies_summary,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
