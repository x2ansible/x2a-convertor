"""Puppet infrastructure analyzer.

This module implements the main PuppetSubagent that orchestrates all Puppet analysis.
It composes BaseAgent subclasses as graph nodes following the pattern from
src/inputs/chef/analyzer.py.
"""

import json
from pathlib import Path
from typing import Literal

from langgraph.graph import END, StateGraph

from src.inputs.puppet.analysis_validation_agent import AnalysisValidationAgent
from src.inputs.puppet.cleanup_agent import CleanupAgent
from src.inputs.puppet.report_writer_agent import ReportWriterAgent
from src.inputs.puppet.state import PuppetState
from src.model import get_model, get_runnable_config
from src.types import Telemetry
from src.types.telemetry import telemetry_context
from src.utils.logging import get_logger

from .dependency_fetcher import PuppetDependencyFetcher
from .execution_tree_builder import PuppetExecutionTreeBuilder
from .hiera_parser import HieraConfigParser
from .models import (
    CredentialAnalysisResult,
    CustomTypeAnalysisResult,
    HieraDataAnalysisResult,
    ManifestAnalysisResult,
    PuppetStructuredAnalysis,
    TemplateAnalysisResult,
)
from .services import (
    CredentialDetectionService,
    CustomTypeAnalysisService,
    HieraDataAnalysisService,
    ManifestAnalysisService,
    TemplateAnalysisService,
)

logger = get_logger(__name__)


class PuppetSubagent:
    """Main Puppet analyzer - implements InfrastructureAnalyzer protocol.

    Workflow phases:
    1. fetch_dependencies - Parse Puppetfile, catalog external modules
    2. scan_hiera_config - Parse hiera.yaml, resolve data files on disk
    3. analyze_structure - Run all services across all files
    4. write_report - Generate migration plan using ReportWriterAgent
    5. validate_with_analysis - Validate plan using AnalysisValidationAgent
    6. cleanup_specification - Clean up using CleanupAgent
    """

    def __init__(self, model=None) -> None:
        self.model = model or get_model()

        # Non-LLM components
        self._hiera_parser: HieraConfigParser | None = None
        self._dependency_fetcher: PuppetDependencyFetcher | None = None

        # Services (Dependency Injection)
        self._manifest_service = ManifestAnalysisService(self.model)
        self._hiera_service = HieraDataAnalysisService(self.model)
        self._template_service = TemplateAnalysisService(self.model)
        self._custom_type_service = CustomTypeAnalysisService(self.model)
        self._credential_service = CredentialDetectionService(self.model)

        # Agents
        self._report_writer = ReportWriterAgent(model=self.model)
        self._analysis_validator = AnalysisValidationAgent(model=self.model)
        self._cleanup = CleanupAgent(model=self.model)

        self._workflow = self._create_workflow()

        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_workflow(self):
        workflow = StateGraph(PuppetState)

        workflow.add_node(
            "fetch_dependencies", lambda state: self._fetch_dependencies(state)
        )
        workflow.add_node(
            "scan_hiera_config", lambda state: self._scan_hiera_config(state)
        )
        workflow.add_node(
            "analyze_structure", lambda state: self._analyze_structure(state)
        )
        workflow.add_node("write_report", self._report_writer)
        workflow.add_node("validate_with_analysis", self._analysis_validator)
        workflow.add_node("cleanup_specification", self._cleanup)
        workflow.add_node("save_hiera_data", lambda state: self._save_hiera_data(state))

        workflow.set_entry_point("fetch_dependencies")
        workflow.add_edge("fetch_dependencies", "scan_hiera_config")
        workflow.add_edge("scan_hiera_config", "analyze_structure")
        workflow.add_edge("analyze_structure", "write_report")
        workflow.add_conditional_edges(
            "write_report",
            self._check_failure_after_agent,
            {"continue": "validate_with_analysis", "failed": END},
        )
        workflow.add_conditional_edges(
            "validate_with_analysis",
            self._check_failure_after_agent,
            {"continue": "cleanup_specification", "failed": END},
        )
        workflow.add_edge("cleanup_specification", "save_hiera_data")
        workflow.add_edge("save_hiera_data", END)

        return workflow.compile()

    def _check_failure_after_agent(
        self, state: PuppetState
    ) -> Literal["continue", "failed"]:
        if state.failed:
            logger.error(f"Agent failed: {state.failure_reason}")
            return "failed"
        return "continue"

    def _fetch_dependencies(self, state: PuppetState) -> PuppetState:
        slog = logger.bind(phase="fetch_dependencies")
        slog.info(f"Checking for external dependencies for {state.path}")

        with telemetry_context(state.telemetry, "fetch_dependencies") as metrics:
            self._dependency_fetcher = PuppetDependencyFetcher(state.path)
            has_deps, _deps = self._dependency_fetcher.has_dependencies()

            if not has_deps:
                slog.info("No Puppetfile found or no dependencies")
                if metrics:
                    metrics.record_metric("dependencies_found", 0)
                return state.update(dependency_paths=[], dependency_info=[])

            dep_info = self._dependency_fetcher.get_dependency_info()
            slog.info(f"Found {len(dep_info)} dependencies in Puppetfile")
            for dep in dep_info:
                slog.info(f"  {dep['name']} ({dep['source']}: {dep['version']})")

            if metrics:
                metrics.record_metric("dependencies_found", len(dep_info))

        return state.update(
            dependency_paths=[d["name"] for d in dep_info],
            dependency_info=dep_info,
        )

    def _scan_hiera_config(self, state: PuppetState) -> PuppetState:
        slog = logger.bind(phase="scan_hiera_config")
        slog.info(f"Scanning Hiera configuration for {state.path}")

        with telemetry_context(state.telemetry, "scan_hiera_config") as metrics:
            self._hiera_parser = HieraConfigParser(state.path)
            hierarchy = self._hiera_parser.parse()

            slog.info(
                f"Found {len(hierarchy.levels)} hierarchy levels, "
                f"{hierarchy.total_data_files} data files"
            )

            if metrics:
                metrics.record_metric("hiera_levels", len(hierarchy.levels))
                metrics.record_metric("hiera_data_files", hierarchy.total_data_files)

        return state.update(hiera_hierarchy=hierarchy)

    def _analyze_structure(self, state: PuppetState) -> PuppetState:
        slog = logger.bind(phase="analyze_structure")
        slog.info("Starting structured analysis of Puppet module files")

        with telemetry_context(state.telemetry, "analyze_structure") as metrics:
            module_path = Path(state.path)

            slog.info("Step 1: Analyzing manifests")
            manifests = self._analyze_manifests(module_path, slog)

            slog.info("Step 2: Analyzing Hiera data files")
            hiera_data = self._analyze_hiera_data(state, slog)

            slog.info("Step 3: Analyzing templates")
            templates = self._analyze_templates(module_path, slog)

            slog.info("Step 4: Analyzing custom types and components")
            custom_types = self._analyze_custom_types(module_path, slog)

            structured_analysis = PuppetStructuredAnalysis(
                manifests=manifests,
                hiera_data=hiera_data,
                templates=templates,
                custom_types=custom_types,
            )

            slog.info(
                f"Analyzed {len(manifests)} manifests, {len(hiera_data)} Hiera files, "
                f"{len(templates)} templates, {len(custom_types)} custom components"
            )

            slog.info("Step 5: Detecting credentials")
            credentials_analysis = self._detect_credentials(hiera_data, manifests, slog)

            slog.info("Step 6: Building execution tree")
            tree_builder = PuppetExecutionTreeBuilder(structured_analysis)
            tree_root = tree_builder.build_tree()
            execution_tree_summary = self._format_execution_tree(
                tree_builder, tree_root, structured_analysis
            )

            variables_summary = self._build_variables_summary(hiera_data)

            if metrics:
                metrics.record_metric("manifests_analyzed", len(manifests))
                metrics.record_metric("hiera_files_analyzed", len(hiera_data))
                metrics.record_metric("templates_analyzed", len(templates))
                metrics.record_metric("custom_types_analyzed", len(custom_types))
                metrics.record_metric(
                    "total_files", structured_analysis.get_total_files_analyzed()
                )

        return state.update(
            structured_analysis=structured_analysis,
            execution_tree_summary=execution_tree_summary,
            credentials_analysis=credentials_analysis,
            variables_summary=variables_summary,
        )

    def _analyze_manifests(
        self, module_path: Path, slog
    ) -> list[ManifestAnalysisResult]:
        results: list[ManifestAnalysisResult] = []
        for pp_file in sorted(module_path.glob("**/manifests/**/*.pp")):
            try:
                slog.debug(f"Analyzing manifest: {pp_file}")
                analysis = self._manifest_service.analyze(pp_file)
                results.append(
                    ManifestAnalysisResult(file_path=str(pp_file), analysis=analysis)
                )
            except Exception as e:
                slog.warning(f"Failed to analyze manifest {pp_file}: {e}")
        return results

    def _analyze_hiera_data(
        self, state: PuppetState, slog
    ) -> list[HieraDataAnalysisResult]:
        results: list[HieraDataAnalysisResult] = []

        if not state.hiera_hierarchy or not state.hiera_hierarchy.levels:
            slog.info("No Hiera hierarchy to analyze")
            return results

        full_hierarchy = "\n".join(
            f"  {level.name}: {level.path_pattern}"
            for level in state.hiera_hierarchy.levels
        )

        for level in state.hiera_hierarchy.levels:
            for file_path in level.resolved_files:
                try:
                    slog.debug(
                        f"Analyzing Hiera data: {file_path} (level: {level.name})"
                    )
                    analysis = self._hiera_service.analyze(
                        file_path=Path(file_path),
                        hierarchy_level=level.name,
                        full_hierarchy=full_hierarchy,
                    )
                    raw_content = ""
                    try:
                        raw_content = Path(file_path).read_text()
                    except OSError as e:
                        slog.warning(
                            f"Could not read resolved Hiera file {file_path}: {e}"
                        )
                    results.append(
                        HieraDataAnalysisResult(
                            file_path=file_path,
                            hierarchy_level=level.name,
                            raw_content=raw_content,
                            analysis=analysis,
                        )
                    )
                except Exception as e:
                    slog.warning(f"Failed to analyze Hiera data {file_path}: {e}")

        return results

    def _analyze_templates(
        self, module_path: Path, slog
    ) -> list[TemplateAnalysisResult]:
        results: list[TemplateAnalysisResult] = []
        patterns = ["**/templates/**/*.erb", "**/templates/**/*.epp"]

        for pattern in patterns:
            for tpl_file in sorted(module_path.glob(pattern)):
                try:
                    slog.debug(f"Analyzing template: {tpl_file}")
                    analysis = self._template_service.analyze(tpl_file)
                    results.append(
                        TemplateAnalysisResult(
                            file_path=str(tpl_file), analysis=analysis
                        )
                    )
                except Exception as e:
                    slog.warning(f"Failed to analyze template {tpl_file}: {e}")

        return results

    def _analyze_custom_types(
        self, module_path: Path, slog
    ) -> list[CustomTypeAnalysisResult]:
        results: list[CustomTypeAnalysisResult] = []
        patterns = {
            "lib/puppet/type/*.rb": "type",
            "lib/puppet/provider/**/*.rb": "provider",
            "lib/facter/*.rb": "fact",
            "lib/puppet/functions/*.rb": "function",
        }

        for pattern, component_type in patterns.items():
            for rb_file in sorted(module_path.glob(pattern)):
                try:
                    slog.debug(f"Analyzing {component_type}: {rb_file}")
                    analysis = self._custom_type_service.analyze(rb_file)
                    results.append(
                        CustomTypeAnalysisResult(
                            file_path=str(rb_file),
                            component_type=component_type,
                            analysis=analysis,
                        )
                    )
                except Exception as e:
                    slog.warning(f"Failed to analyze {component_type} {rb_file}: {e}")

        return results

    def _detect_credentials(
        self,
        hiera_data: list[HieraDataAnalysisResult],
        manifests: list[ManifestAnalysisResult],
        slog,
    ) -> list[CredentialAnalysisResult]:
        hiera_vars_lines: list[str] = []
        for h in hiera_data:
            hiera_vars_lines.append(f"File: {h.file_path} (level: {h.hierarchy_level})")
            for var in h.analysis.variables:
                encrypted_marker = " [ENCRYPTED]" if var.is_encrypted else ""
                hiera_vars_lines.append(
                    f"  {var.puppet_key} ({var.value_type}){encrypted_marker}"
                )

        manifest_params_lines: list[str] = []
        for m in manifests:
            if m.analysis.class_name and m.analysis.class_parameters:
                manifest_params_lines.append(f"Class: {m.analysis.class_name}")
                for param_name, param_info in m.analysis.class_parameters.items():
                    manifest_params_lines.append(f"  {param_name}: {param_info}")

        hiera_variables = "\n".join(hiera_vars_lines) if hiera_vars_lines else "None"
        manifest_params = (
            "\n".join(manifest_params_lines) if manifest_params_lines else "None"
        )

        try:
            analysis = self._credential_service.analyze(
                hiera_variables=hiera_variables,
                manifest_params=manifest_params,
            )
            return [CredentialAnalysisResult(analysis=analysis)]
        except Exception as e:
            slog.warning(f"Failed to detect credentials: {e}")
            return []

    def _format_execution_tree(
        self,
        tree_builder: PuppetExecutionTreeBuilder,
        tree_root,
        analysis: PuppetStructuredAnalysis,
    ) -> str:
        lines = [
            "=" * 80,
            "PUPPET CLASS EXECUTION TREE",
            "=" * 80,
            "",
            f"Total files analyzed: {analysis.get_total_files_analyzed()}",
            "",
            "Execution flow starting from entry class:",
            "",
            tree_builder.format_tree(tree_root),
            "",
            "=" * 80,
            "",
        ]
        return "\n".join(lines)

    def _build_variables_summary(
        self, hiera_data: list[HieraDataAnalysisResult]
    ) -> str:
        if not hiera_data:
            return "No Hiera variables detected."

        lines: list[str] = []
        lines.append("HIERA VARIABLE MAPPING SUMMARY")
        lines.append("=" * 60)

        total_vars = sum(len(h.analysis.variables) for h in hiera_data)
        levels_with_data = {h.hierarchy_level for h in hiera_data}
        lines.append(
            f"Total: {total_vars} variables across {len(levels_with_data)} Hiera levels"
        )
        lines.append("")

        lines.append(
            f"{'Puppet Variable':<45} {'Hiera Level':<25} {'Ansible Target':<30} {'Ansible Name'}"
        )
        lines.append("-" * 140)

        for h in hiera_data:
            for var in h.analysis.variables:
                lines.append(
                    f"{var.puppet_key:<45} {h.hierarchy_level:<25} "
                    f"{var.ansible_target:<30} {var.ansible_variable_name}"
                )

        cross_overrides: set[str] = set()
        for h in hiera_data:
            for key in h.analysis.cross_level_overrides:
                cross_overrides.add(key)

        if cross_overrides:
            lines.append("")
            lines.append("CROSS-LEVEL OVERRIDES (same key at multiple levels):")
            for key in sorted(cross_overrides):
                levels = [
                    h.hierarchy_level
                    for h in hiera_data
                    if key in h.analysis.cross_level_overrides
                ]
                lines.append(f"  {key}: overridden at {', '.join(levels)}")

        lines.append("")
        lines.append("RAW HIERA DATA FILES (use these EXACT values)")
        lines.append("=" * 60)
        for h in hiera_data:
            if h.raw_content.strip():
                lines.append(f"\n--- {h.file_path} (level: {h.hierarchy_level}) ---")
                lines.append(h.raw_content)

        return "\n".join(lines)

    def _save_hiera_data(self, state: PuppetState) -> PuppetState:
        """Save Hiera analysis data as JSON for deterministic vars generation."""
        if not state.structured_analysis or not state.structured_analysis.hiera_data:
            logger.info("No Hiera data to save")
            return state

        data = []
        for h in state.structured_analysis.hiera_data:
            mappings = [
                {
                    "puppet_key": v.puppet_key,
                    "ansible_variable_name": v.ansible_variable_name,
                    "ansible_target": v.ansible_target,
                    "value_type": v.value_type,
                    "is_encrypted": v.is_encrypted,
                }
                for v in h.analysis.variables
            ]
            data.append(
                {
                    "file_path": h.file_path,
                    "hierarchy_level": h.hierarchy_level,
                    "raw_content": h.raw_content,
                    "mappings": mappings,
                    "merge_behavior": h.analysis.merge_behavior,
                }
            )

        module_name = Path(state.path).resolve().name
        json_path = Path(state.path).parent / f"hiera-data-{module_name}.json"
        json_path.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved Hiera data ({len(data)} files) to {json_path}")
        return state

    def invoke(
        self, path: str, user_message: str, telemetry: Telemetry | None = None
    ) -> str:
        logger.info("Using Puppet agent for migration analysis...")

        initial_state = PuppetState(
            path=path,
            user_message=user_message,
            specification="",
            dependency_paths=[],
            export_path=None,
            telemetry=telemetry,
        )

        result = self._workflow.invoke(initial_state, config=get_runnable_config())

        if result.get("failed"):
            logger.error(
                f"Puppet analysis failed: {result.get('failure_reason', 'unknown')}"
            )

        return result["specification"]
