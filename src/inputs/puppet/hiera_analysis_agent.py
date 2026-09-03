"""On-demand Hiera data analysis agent.

Two-phase LLM approach:
  Phase 1 — invoke_react: agent explores hiera files with tools
  Phase 2 — invoke_structured: agent produces HieraAgentAnalysis from its findings
"""

import re
from collections.abc import Callable
from typing import ClassVar

from langchain_community.tools import ReadFileTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.config.settings import SummaryContextSize
from src.inputs.input_agent import InputAgent
from src.inputs.puppet.state import PuppetState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger
from src.utils.path import Path
from tools.grep_file import GrepFileTool

from .models import (
    HieraAgentAnalysis,
    HieraDataAnalysis,
    HieraDataAnalysisResult,
    ManifestAnalysisResult,
    TemplateAnalysisResult,
)

logger = get_logger(__name__)

LOOKUP_PATTERN = re.compile(r"""(?:lookup|hiera)\(\s*['"]([^'"]+)['"]\s*""")


class HieraAnalysisAgent(InputAgent[PuppetState]):
    """Agent-driven hiera data analysis.

    1. Extracts lookup keys from manifest/template analysis
    2. Explores hiera files with tools (grep, read)
    3. Produces structured analysis via invoke_structured
    """

    _NAME: ClassVar[str] = "HieraAnalysisAgent"

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        ReadFileTool,
        GrepFileTool,
        ListDirectoryTool,
    ]

    SUMMARY_CONTEXT_RATIO = SummaryContextSize.MEDIUM

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

        messages = self._build_messages(
            module_path=data_roots[0].relative_to_cwd(),
            lookup_keys=lookup_keys,
            root_paths=[root.relative_to_cwd() for root in data_roots],
        )

        slog.info("Phase 1: Exploring hiera data with the agent")
        result = self.invoke_react(state, messages, metrics)
        ai_message = self.get_last_ai_message(result)
        findings = ""
        if ai_message:
            findings = str(ai_message.text or ai_message.content or "")
        slog.info("Phase 1 complete, structuring findings")

        slog.info("Phase 2: Producing structured analysis")
        analysis = self._structure_findings(findings, lookup_keys, metrics)
        if not analysis:
            slog.warning("Structured analysis returned None")
            return []

        slog.info(f"Analyzed {len(analysis.files)} relevant hiera files")
        return [self._to_result(f) for f in analysis.files]

    # ------------------------------------------------------------------
    # Lookup key extraction
    # ------------------------------------------------------------------

    def _extract_lookup_keys(
        self,
        manifests: list[ManifestAnalysisResult],
        templates: list[TemplateAnalysisResult],
    ) -> list[str]:
        keys: set[str] = set()

        for manifest in manifests:
            keys.update(self._keys_from_manifest(manifest.analysis))

        for template in templates:
            keys.update(template.analysis.hiera_lookups)

        return sorted(keys)

    def _keys_from_manifest(self, analysis) -> set[str]:
        keys: set[str] = set()

        if analysis.class_name and analysis.class_parameters:
            for param_name, param_default in analysis.class_parameters.items():
                keys.add(f"{analysis.class_name}::{param_name}")
                keys.update(LOOKUP_PATTERN.findall(str(param_default)))

        for item in analysis.execution_order:
            keys.update(self._keys_from_attributes(item))

        return keys

    def _keys_from_attributes(self, item) -> set[str]:
        keys: set[str] = set()

        for attr_value in (item.attributes or {}).values():
            keys.update(LOOKUP_PATTERN.findall(str(attr_value)))

        for nested in getattr(item, "execution_order", []):
            for attr_value in (getattr(nested, "attributes", {}) or {}).values():
                keys.update(LOOKUP_PATTERN.findall(str(attr_value)))

        return keys

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        module_path: str,
        lookup_keys: list[str],
        root_paths: list[str],
    ) -> list[dict[str, str]]:
        system_prompt = get_prompt("puppet_hiera_agent_system").format()
        task_prompt = get_prompt("puppet_hiera_agent_task").format(
            module_path=module_path,
            lookup_keys=lookup_keys,
            root_paths=root_paths,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt},
        ]

    def _structure_findings(
        self,
        findings: str,
        lookup_keys: list[str],
        metrics: AgentMetrics | None,
    ) -> HieraAgentAnalysis | None:
        prompt = get_prompt("puppet_hiera_agent_structuring").format(
            findings=findings,
            lookup_keys=lookup_keys,
        )
        return self.invoke_structured(
            HieraAgentAnalysis,
            [{"role": "user", "content": prompt}],
            metrics,
        )

    # ------------------------------------------------------------------
    # Result conversion
    # ------------------------------------------------------------------

    def _to_result(self, file_analysis) -> HieraDataAnalysisResult:
        raw_content = self._read_file(file_analysis.file_path)
        return HieraDataAnalysisResult(
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

    def _read_file(self, file_path: str) -> str:
        try:
            return Path(file_path).read_text()
        except OSError:
            return ""
