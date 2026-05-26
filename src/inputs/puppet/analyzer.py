"""Puppet infrastructure analyzer.

This module implements the main PuppetSubagent that orchestrates all Puppet analysis.
It composes InputAgent subclasses as graph nodes following the pattern from
src/inputs/chef/analyzer.py.
"""

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
    2. analyze_structure - Run all services across all files
    3. write_report - Generate migration plan using ReportWriterAgent (has hiera parser tool)
    4. validate_with_analysis - Validate plan using AnalysisValidationAgent
    5. cleanup_specification - Clean up using CleanupAgent
    """

    def __init__(self, model=None) -> None:
        self.model = model or get_model()

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
            "analyze_structure", lambda state: self._analyze_structure(state)
        )
        workflow.add_node("write_report", self._report_writer)
        workflow.add_node("validate_with_analysis", self._analysis_validator)
        workflow.add_node("cleanup_specification", self._cleanup)

        workflow.set_entry_point("fetch_dependencies")
        workflow.add_edge("fetch_dependencies", "analyze_structure")
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
        workflow.add_edge("cleanup_specification", END)

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
            module_root = str(self._resolve_module_root(state.path))
            self._dependency_fetcher = PuppetDependencyFetcher(module_root)
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

            deps_path = self._dependency_fetcher.download_dependencies()
            if deps_path:
                slog.info(f"Dependencies downloaded to {deps_path}")
            else:
                slog.warning("Could not download dependencies (r10k not available or failed)")

            if metrics:
                metrics.record_metric("dependencies_found", len(dep_info))

        return state.update(
            dependency_paths=[d["name"] for d in dep_info],
            dependency_info=dep_info,
            dependencies_dir=str(deps_path) if deps_path else None,
        )

    @staticmethod
    def _resolve_module_root(path: str) -> Path:
        """Resolve path to Puppet module root directory.

        The module selector may return 'manifests/init.pp' or 'manifests'
        instead of the module root. Walk up to find the directory containing manifests/.
        """
        p = Path(path)
        if p.is_file():
            p = p.parent
        for candidate in [p] + list(p.parents):
            if (candidate / "manifests").is_dir():
                return candidate
            if candidate == Path("."):
                break
        return Path(path)

    def _analyze_structure(self, state: PuppetState) -> PuppetState:
        slog = logger.bind(phase="analyze_structure")
        slog.info("Starting structured analysis of Puppet module files")

        with telemetry_context(state.telemetry, "analyze_structure") as metrics:
            module_path = self._resolve_module_root(state.path)
            if module_path != Path(state.path):
                slog.info(f"Resolved module root: {state.path} -> {module_path}")

            slog.info("Step 1: Analyzing manifests")
            manifests = self._analyze_manifests(module_path, slog)

            slog.info("Step 2: Analyzing Hiera data files")
            hiera_data = self._analyze_hiera_data(module_path, slog)

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
        )

    def _analyze_manifests(
        self, module_path: Path, slog
    ) -> list[ManifestAnalysisResult]:
        results: list[ManifestAnalysisResult] = []
        for pp_file in sorted(module_path.glob("**/manifests/**/*.pp")):
            if "spec/" in str(pp_file) or "test/" in str(pp_file):
                continue
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
        self, module_path: Path, slog
    ) -> list[HieraDataAnalysisResult]:
        """Analyze all YAML files under the data/ directory."""
        results: list[HieraDataAnalysisResult] = []
        data_dir = module_path / "data"
        if not data_dir.exists():
            slog.info("No data/ directory found")
            return results

        for yaml_file in sorted(data_dir.glob("**/*.yaml")):
            try:
                level_name = yaml_file.relative_to(data_dir).as_posix()
                slog.debug(f"Analyzing Hiera data: {yaml_file}")
                analysis = self._hiera_service.analyze(
                    file_path=yaml_file,
                    hierarchy_level=level_name,
                )
                raw_content = ""
                try:
                    raw_content = yaml_file.read_text()
                except OSError as e:
                    slog.warning(f"Could not read Hiera file {yaml_file}: {e}")
                results.append(
                    HieraDataAnalysisResult(
                        file_path=str(yaml_file),
                        hierarchy_level=level_name,
                        raw_content=raw_content,
                        analysis=analysis,
                    )
                )
            except Exception as e:
                slog.warning(f"Failed to analyze Hiera data {yaml_file}: {e}")

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
