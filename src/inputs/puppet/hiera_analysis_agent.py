"""On-demand Hiera data analysis agent.

Replaces the brute-force per-file HieraDataAnalysisService with a ReAct agent
that uses tools (grep, read, list_dir) to find and analyze only the hiera data
files relevant to the module being migrated.

Two-phase LLM approach:
  Phase 1 — invoke_react: agent explores hiera files with tools
  Phase 2 — invoke_structured: agent produces HieraAgentAnalysis from its findings
"""

import re
from collections.abc import Callable
from typing import ClassVar

from langchain_community.tools import ReadFileTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.inputs.puppet.hiera_parser import HieraConfigParser
from src.inputs.puppet.state import PuppetState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger
from src.utils.path import Path
from tools.grep_file import GrepFileTool

from .models import (
    HieraAgentAnalysis,
    HieraDataAnalysis,
    HieraDataAnalysisResult,
    HieraHierarchy,
    ManifestAnalysisResult,
    TemplateAnalysisResult,
)

logger = get_logger(__name__)

LOOKUP_PATTERN = re.compile(r"""(?:lookup|hiera)\(\s*['"]([^'"]+)['"]\s*""")


class HieraAnalysisAgent(InputAgent[PuppetState]):
    """Agent-driven hiera data analysis for large repositories.

    Instead of calling an LLM on every hiera file, this agent:
    1. Deterministically extracts lookup keys from manifest analysis
    2. Uses tools to grep/read only the relevant files
    3. Produces a structured analysis via invoke_structured
    """

    _NAME: ClassVar[str] = "HieraAnalysisAgent"

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        ReadFileTool,
        GrepFileTool,
    ]

    MAX_TOKENS_BEFORE_SUMMARY = 50000

    def execute(self, state: PuppetState, metrics: AgentMetrics | None) -> PuppetState:
        return state

    def analyze(
        self,
        data_roots: list[Path],
        manifests: list[ManifestAnalysisResult],
        templates: list[TemplateAnalysisResult],
        state: PuppetState,
        metrics: AgentMetrics | None,
    ) -> list[HieraDataAnalysisResult]:
        slog = logger.bind(agent=self._NAME)

        lookup_keys = self._extract_lookup_keys(manifests, templates)
        slog.info(f"Extracted {len(lookup_keys)} lookup keys from manifests")

        hierarchies = self._parse_hierarchies(data_roots)
        all_hiera_files = self._collect_resolved_files(hierarchies)
        slog.info(
            f"Found {len(all_hiera_files)} hiera data files across {len(data_roots)} data roots"
        )

        if not all_hiera_files:
            slog.info("No hiera data files found, skipping analysis")
            return []

        hierarchy_summary = self._format_hierarchy_summary(hierarchies)
        data_dirs = [
            str(root / "data") for root in data_roots if (root / "data").is_dir()
        ]

        messages = self._build_exploration_messages(
            module_path=str(data_roots[0]),
            hierarchy_summary=hierarchy_summary,
            lookup_keys=lookup_keys,
            data_dirs=data_dirs,
        )

        slog.info("Phase 1: Exploring hiera data with tools")
        result = self.invoke_react(state, messages, metrics)
        findings = self._extract_findings(result)
        slog.info("Phase 1 complete, structuring findings")

        slog.info("Phase 2: Producing structured analysis")
        analysis = self._produce_structured_analysis(findings, lookup_keys, metrics)

        if not analysis:
            slog.warning("Structured analysis returned None, returning empty results")
            return []

        slog.info(f"Analyzed {len(analysis.files)} relevant hiera files")
        return self._convert_to_results(analysis)

    def _extract_lookup_keys(
        self,
        manifests: list[ManifestAnalysisResult],
        templates: list[TemplateAnalysisResult],
    ) -> list[str]:
        keys: set[str] = set()

        for manifest in manifests:
            analysis = manifest.analysis

            if analysis.class_name and analysis.class_parameters:
                for param_name, param_default in analysis.class_parameters.items():
                    keys.add(f"{analysis.class_name}::{param_name}")
                    keys.update(self._extract_keys_from_value(param_default))

            for item in analysis.execution_order:
                self._extract_keys_from_execution_item(item, keys)

        for template in templates:
            keys.update(template.analysis.hiera_lookups)

        return sorted(keys)

    def _extract_keys_from_value(self, value: str) -> list[str]:
        return LOOKUP_PATTERN.findall(str(value))

    def _extract_keys_from_execution_item(self, item, keys: set[str]) -> None:
        for attr_value in (item.attributes or {}).values():
            keys.update(self._extract_keys_from_value(str(attr_value)))

        for nested in getattr(item, "execution_order", []):
            for attr_value in (getattr(nested, "attributes", {}) or {}).values():
                keys.update(self._extract_keys_from_value(str(attr_value)))

    def _parse_hierarchies(self, data_roots: list[Path]) -> list[HieraHierarchy]:
        hierarchies: list[HieraHierarchy] = []
        for root in data_roots:
            parser = HieraConfigParser(str(root))
            hierarchy = parser.parse()
            if hierarchy.levels:
                hierarchies.append(hierarchy)
        return hierarchies

    def _collect_resolved_files(self, hierarchies: list[HieraHierarchy]) -> list[str]:
        files: set[str] = set()
        for hierarchy in hierarchies:
            for level in hierarchy.levels:
                files.update(level.resolved_files)
        return sorted(files)

    def _format_hierarchy_summary(self, hierarchies: list[HieraHierarchy]) -> str:
        if not hierarchies:
            return "No hiera.yaml found"

        hierarchy = hierarchies[0]
        lines = [f"Hiera v{hierarchy.version}"]
        for level in hierarchy.levels:
            file_count = len(level.resolved_files)
            lines.append(
                f"  - {level.name}: {level.path_pattern} ({file_count} files resolved)"
            )
        return "\n".join(lines)

    def _build_exploration_messages(
        self,
        module_path: str,
        hierarchy_summary: str,
        lookup_keys: list[str],
        data_dirs: list[str],
    ) -> list[dict[str, str]]:
        system_prompt = get_prompt("puppet_hiera_agent_system").format()
        task_prompt = get_prompt("puppet_hiera_agent_task").format(
            module_path=module_path,
            hierarchy_summary=hierarchy_summary,
            lookup_keys=lookup_keys,
            data_dirs=data_dirs,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt},
        ]

    def _extract_findings(self, result: dict) -> str:
        ai_message = self.get_last_ai_message(result)
        if ai_message and ai_message.content:
            return str(ai_message.content)
        return "No findings from exploration phase."

    def _produce_structured_analysis(
        self,
        findings: str,
        lookup_keys: list[str],
        metrics: AgentMetrics | None,
    ) -> HieraAgentAnalysis | None:
        structuring_prompt = get_prompt("puppet_hiera_agent_structuring").format(
            findings=findings,
            lookup_keys=lookup_keys,
        )
        messages = [
            {"role": "user", "content": structuring_prompt},
        ]
        return self.invoke_structured(HieraAgentAnalysis, messages, metrics)

    def _convert_to_results(
        self, analysis: HieraAgentAnalysis
    ) -> list[HieraDataAnalysisResult]:
        results: list[HieraDataAnalysisResult] = []
        for file_analysis in analysis.files:
            raw_content = self._read_file_content(file_analysis.file_path)
            results.append(
                HieraDataAnalysisResult(
                    file_path=file_analysis.file_path,
                    hierarchy_level=file_analysis.hierarchy_level,
                    raw_content=raw_content,
                    analysis=HieraDataAnalysis(
                        variables=file_analysis.variables,
                        merge_behavior=file_analysis.merge_behavior,
                        lookup_options=file_analysis.lookup_options,
                        cross_level_overrides=file_analysis.cross_level_overrides,
                        notes=file_analysis.notes,
                    ),
                )
            )
        return results

    def _read_file_content(self, file_path: str) -> str:
        try:
            return Path(file_path).read_text()
        except OSError:
            return ""
