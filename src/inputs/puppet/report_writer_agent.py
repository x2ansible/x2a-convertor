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
from src.inputs.input_agent import InputAgent
from src.inputs.puppet.state import PuppetState
from src.inputs.puppet.tools import HieraParserTool
from src.inputs.tree_analysis import TreeSitterAnalyzer
from src.types.telemetry import AgentMetrics


class ReportWriterAgent(InputAgent[PuppetState]):
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

    def extra_tools_from_state(self, state: PuppetState) -> list[BaseTool]:
        return [HieraParserTool(module_path=state.path)]

    def execute(self, state: PuppetState, metrics: AgentMetrics | None) -> PuppetState:
        self._log.info("Generating migration specification")

        data_list = self._build_file_listing(state)
        tree_sitter_report = self._generate_tree_sitter_report(state.path)
        credentials_summary = self._build_credentials_summary(state)
        dependencies_summary = self._build_dependencies_summary(state)
        custom_types_summary = self._build_custom_types_summary(state)
        puppetdb_summary = self._build_puppetdb_summary(state)
        control_repo_summary = self._build_control_repo_summary(state)

        messages = self._build_messages(
            state,
            data_list,
            tree_sitter_report,
            credentials_summary,
            dependencies_summary,
            custom_types_summary,
            puppetdb_summary,
            control_repo_summary,
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
                lines.append(f"  - {cred.purpose}: {', '.join(cred.variable_names)}")

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

        summary = f"Found {len(state.dependency_info)} dependencies:\n" + "\n".join(
            lines
        )
        if state.dependencies_dir:
            summary += (
                f"\n\nDependency source code downloaded to: {state.dependencies_dir}/"
                "\nYou can use read_file and list_directory to inspect dependency modules."
            )
        return summary

    def _build_puppetdb_summary(self, state: PuppetState) -> str:
        if not state.structured_analysis:
            return "No PuppetDB usage detected."

        exported: list[str] = []
        collectors: list[str] = []
        queries: list[str] = []

        for manifest in state.structured_analysis.manifests:
            analysis = manifest.analysis
            class_name = analysis.class_name or manifest.file_path

            for res in analysis.exported_resources:
                attrs = ", ".join(
                    f"{k}: {v}" for k, v in list(res.attributes.items())[:5]
                )
                exported.append(
                    f"  - `@@{res.resource_type}[{res.title}]` in {class_name}"
                    + (f" ({attrs})" if attrs else "")
                )

            for collector in analysis.collectors:
                collectors.append(f"  - `{collector}` in {class_name}")

            for query in analysis.puppetdb_queries:
                queries.append(f"  - `{query}` in {class_name}")

        if not exported and not collectors and not queries:
            return "No PuppetDB usage detected."

        lines: list[str] = []
        if exported:
            lines.append(f"Exported resources ({len(exported)}):")
            lines.extend(exported)
        if collectors:
            lines.append(f"\nResource collectors ({len(collectors)}):")
            lines.extend(collectors)
        if queries:
            lines.append(f"\nPuppetDB queries ({len(queries)}):")
            lines.extend(queries)

        return "\n".join(lines)

    def _build_custom_types_summary(self, state: PuppetState) -> str:
        if not state.structured_analysis or not state.structured_analysis.custom_types:
            return "No custom types, providers, facts, or functions detected."

        lines: list[str] = []
        for ct in state.structured_analysis.custom_types:
            analysis = ct.analysis
            lines.append(f"### {analysis.component_type}: {analysis.name}")
            lines.append(f"  File: {ct.file_path}")
            if analysis.note:
                lines.append(f"  Description: {analysis.note}")
            if analysis.parameters:
                lines.append("  Parameters:")
                for param in analysis.parameters:
                    lines.append(f"    - {param}")
            if analysis.ansible_equivalent:
                lines.append(f"  Ansible equivalent: {analysis.ansible_equivalent}")
            lines.append("")

        return "\n".join(lines) if lines else "No custom types detected."

    def _build_control_repo_summary(self, state: PuppetState) -> str:
        if not state.control_repo_root:
            return "Standalone module (no control repo detected)."

        lines = [
            f"Control repo root: {state.control_repo_root}",
        ]

        if state.role_class:
            lines.append(f"Role entry point: {state.role_class}")

        if state.profile_classes:
            lines.append(f"Profile chain: {' → '.join(state.profile_classes)}")

        if state.role_class and state.profile_classes:
            chain = [
                state.role_class,
                *state.profile_classes,
                state.path.split("/")[-1],
            ]
            lines.append(f"Full chain: {' → '.join(chain)}")

        if state.context_manifest_paths:
            lines.append(
                f"\nContext manifests analyzed ({len(state.context_manifest_paths)}):"
            )
            for p in state.context_manifest_paths:
                lines.append(f"  - {p}")

        return "\n".join(lines)

    def _build_messages(
        self,
        state: PuppetState,
        data_list: str,
        tree_sitter_report: str,
        credentials_summary: str,
        dependencies_summary: str,
        custom_types_summary: str,
        puppetdb_summary: str,
        control_repo_summary: str,
    ) -> list[dict[str, str]]:
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            path=state.path,
            user_message=state.user_message,
            directory_listing=data_list,
            tree_sitter_report=tree_sitter_report,
            execution_tree=state.execution_tree_summary,
            credentials_summary=credentials_summary,
            dependencies_summary=dependencies_summary,
            custom_types_summary=custom_types_summary,
            puppetdb_summary=puppetdb_summary,
            control_repo_summary=control_repo_summary,
        )
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]
