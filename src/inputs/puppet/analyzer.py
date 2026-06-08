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
from src.types.file_analysis_state import FileAnalysisState
from src.types.telemetry import telemetry_context
from src.utils.logging import get_logger

from .dependency_fetcher import PuppetDependencyAgent, resolve_puppet_module_root
from .execution_tree_builder import PuppetExecutionTreeBuilder
from .models import (
    CredentialAnalysisResult,
    CustomTypeAnalysisResult,
    HieraDataAnalysisResult,
    ManifestAnalysisResult,
    PuppetStructuredAnalysis,
    TemplateAnalysisResult,
)
from .path_resolver import PuppetPathResolver
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

        # Services (Dependency Injection)
        self._manifest_service = ManifestAnalysisService(self.model)
        self._hiera_service = HieraDataAnalysisService(self.model)
        self._template_service = TemplateAnalysisService(self.model)
        self._custom_type_service = CustomTypeAnalysisService(self.model)
        self._credential_service = CredentialDetectionService(self.model)

        # Agents
        self._dependency_agent = PuppetDependencyAgent(model=self.model)
        self._report_writer = ReportWriterAgent(model=self.model)
        self._analysis_validator = AnalysisValidationAgent(model=self.model)
        self._cleanup = CleanupAgent(model=self.model)

        self._path_resolver: PuppetPathResolver | None = None

        # Cache: absolute path -> ManifestAnalysisResult
        self._manifest_cache: dict[str, ManifestAnalysisResult] = {}

        self._workflow = self._create_workflow()

        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_workflow(self):
        workflow = StateGraph(PuppetState)

        workflow.add_node(
            "fetch_dependencies", lambda state: self._fetch_dependencies(state)
        )
        workflow.add_node(
            "discover_context",
            lambda state: self._discover_control_repo_context(state),
        )
        workflow.add_node(
            "analyze_structure", lambda state: self._analyze_structure(state)
        )
        workflow.add_node("write_report", self._report_writer)
        workflow.add_node("validate_with_analysis", self._analysis_validator)
        workflow.add_node("cleanup_specification", self._cleanup)

        workflow.set_entry_point("fetch_dependencies")
        workflow.add_edge("fetch_dependencies", "discover_context")
        workflow.add_edge("discover_context", "analyze_structure")
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
        logger.info(f"Checking for external dependencies for {state.path}")
        result = self._dependency_agent(state)
        return result

    def _discover_control_repo_context(self, state: PuppetState) -> PuppetState:
        """Discover control repo structure and find role/profile chain."""
        slog = logger.bind(phase="discover_context")
        module_path = resolve_puppet_module_root(state.path)

        repo_root = PuppetPathResolver.find_control_repo_root(module_path)
        if repo_root is None:
            slog.info("No environment.conf found — standalone module")
            if state.dependencies_dir:
                deps_path = Path(state.dependencies_dir)
                if deps_path.is_dir():
                    self._path_resolver = PuppetPathResolver(
                        module_path, [module_path.parent, deps_path]
                    )
                    slog.info(f"Created path resolver with dependencies: {deps_path}")
            return state

        slog.info(f"Found control repo root: {repo_root}")
        env_conf = repo_root / "environment.conf"
        modulepath = PuppetPathResolver.parse_modulepath(env_conf)
        if not modulepath:
            slog.warning("Could not parse modulepath from environment.conf")
            return state

        if state.dependencies_dir:
            deps_path = Path(state.dependencies_dir)
            if deps_path.is_dir():
                modulepath.append(deps_path)

        slog.info(f"Modulepath entries: {[str(p) for p in modulepath]}")
        self._path_resolver = PuppetPathResolver(repo_root, modulepath)

        module_name = module_path.name
        slog.info(f"Discovering references to module '{module_name}'")
        context_manifests = self._path_resolver.find_referencing_manifests(module_name)

        context_paths = [str(p) for p in context_manifests]
        slog.info(f"Found {len(context_paths)} context manifests (roles/profiles)")
        for cp in context_paths:
            slog.info(f"  {cp}")

        role_class = None
        profile_classes: list[str] = []
        for manifest_path in context_manifests:
            inferred = self._path_resolver._infer_class_name(manifest_path)
            if inferred and inferred.startswith("role::"):
                role_class = inferred
            elif inferred:
                profile_classes.append(inferred)

        if role_class:
            slog.info(f"Role entry point: {role_class}")
        if profile_classes:
            slog.info(f"Profile chain: {profile_classes}")

        return state.update(
            control_repo_root=str(repo_root),
            context_manifest_paths=context_paths,
            role_class=role_class,
            profile_classes=profile_classes,
        )

    def _analyze_structure(self, state: PuppetState) -> PuppetState:
        slog = logger.bind(phase="analyze_structure")
        slog.info("Starting structured analysis of Puppet module files")

        with telemetry_context(state.telemetry, "analyze_structure") as metrics:
            module_path = resolve_puppet_module_root(state.path)
            if module_path != Path(state.path):
                slog.info(f"Resolved module root: {state.path} -> {module_path}")

            slog.info("Step 1: Analyzing manifests")
            manifests = self._analyze_manifests(module_path, slog)

            if state.context_manifest_paths:
                slog.info(
                    f"Step 1b: Analyzing {len(state.context_manifest_paths)} "
                    "context manifests (roles/profiles)"
                )
                context_manifests = self._analyze_manifest_files(
                    [Path(p) for p in state.context_manifest_paths], slog
                )
                manifests.extend(context_manifests)

            if state.dependencies_dir:
                deps_path = Path(state.dependencies_dir)
                if deps_path.is_dir():
                    dep_modules = [
                        d
                        for d in sorted(deps_path.iterdir())
                        if d.is_dir() and (d / "manifests").is_dir()
                    ]
                    if dep_modules:
                        slog.info(
                            f"Step 1c: Analyzing {len(dep_modules)} dependency modules"
                        )
                        for dep_module in dep_modules:
                            dep_manifests = self._analyze_manifests(dep_module, slog)
                            manifests.extend(dep_manifests)

            slog.info("Step 2: Analyzing Hiera data files")
            hiera_data = self._analyze_hiera_data(module_path, slog)

            if state.control_repo_root:
                repo_root = Path(state.control_repo_root)
                slog.info("Step 2b: Analyzing environment-level Hiera data")
                env_hiera = self._analyze_hiera_data(repo_root, slog)
                hiera_data.extend(env_hiera)

            slog.info("Step 3: Analyzing templates")
            templates = self._analyze_templates(module_path, slog)

            if state.dependencies_dir:
                deps_path = Path(state.dependencies_dir)
                if deps_path.is_dir():
                    for dep_module in sorted(deps_path.iterdir()):
                        if dep_module.is_dir() and (dep_module / "templates").is_dir():
                            dep_templates = self._analyze_templates(dep_module, slog)
                            templates.extend(dep_templates)

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
            tree_builder = PuppetExecutionTreeBuilder(
                structured_analysis, path_resolver=self._path_resolver
            )
            entry_class = state.role_class if state.role_class else None
            tree_root = tree_builder.build_tree(entry_class=entry_class)

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

    def _analyze_manifest_file(
        self, pp_file: Path, slog
    ) -> ManifestAnalysisResult | None:
        """Analyze a single manifest file with caching."""
        file_path_str = str(pp_file.resolve())

        cached_manifest = self._manifest_cache.get(file_path_str)
        if cached_manifest:
            slog.debug(f"Using cached analysis for: {pp_file}")
            return self._manifest_cache[file_path_str]

        try:
            slog.debug(f"Analyzing manifest: {pp_file}")
            file_state = FileAnalysisState(user_message="", path=file_path_str)
            result_state = self._manifest_service(file_state)
            result = ManifestAnalysisResult(
                file_path=file_path_str, analysis=result_state.result
            )
            self._manifest_cache[file_path_str] = result
            return result
        except Exception as e:
            slog.warning(f"Failed to analyze manifest {pp_file}: {e}")
            return None

    def _analyze_manifests(
        self, module_path: Path, slog
    ) -> list[ManifestAnalysisResult]:
        results: list[ManifestAnalysisResult] = []
        for pp_file in sorted(module_path.glob("**/manifests/**/*.pp")):
            if "spec/" in str(pp_file) or "test/" in str(pp_file):
                continue
            result = self._analyze_manifest_file(pp_file, slog)
            if result:
                results.append(result)
        return results

    def _analyze_manifest_files(
        self, files: list[Path], slog
    ) -> list[ManifestAnalysisResult]:
        """Analyze specific manifest files (used for context manifests)."""
        results: list[ManifestAnalysisResult] = []
        for pp_file in sorted(files):
            if not pp_file.is_file():
                continue
            result = self._analyze_manifest_file(pp_file, slog)
            if result:
                results.append(result)
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
                file_state = FileAnalysisState(
                    user_message="",
                    path=str(yaml_file),
                    metadata={"hierarchy_level": level_name, "full_hierarchy": ""},
                )
                result_state = self._hiera_service(file_state)
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
                        analysis=result_state.result,
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
                    file_state = FileAnalysisState(user_message="", path=str(tpl_file))
                    result_state = self._template_service(file_state)
                    results.append(
                        TemplateAnalysisResult(
                            file_path=str(tpl_file), analysis=result_state.result
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
            "functions/*.pp": "puppet_function",
            "types/*.pp": "type_alias",
            "plans/*.pp": "bolt_plan",
        }

        for pattern, component_type in patterns.items():
            for rb_file in sorted(module_path.glob(pattern)):
                try:
                    slog.debug(f"Analyzing {component_type}: {rb_file}")
                    file_state = FileAnalysisState(user_message="", path=str(rb_file))
                    result_state = self._custom_type_service(file_state)
                    results.append(
                        CustomTypeAnalysisResult(
                            file_path=str(rb_file),
                            component_type=component_type,
                            analysis=result_state.result,
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
            file_state = FileAnalysisState(
                user_message="",
                path="",
                metadata={
                    "hiera_variables": hiera_variables,
                    "manifest_params": manifest_params,
                },
            )
            result_state = self._credential_service(file_state)
            return [CredentialAnalysisResult(analysis=result_state.result)]
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
            export_path=None,
            telemetry=telemetry,
        )

        result = self._workflow.invoke(initial_state, config=get_runnable_config())

        if result.get("failed"):
            logger.error(
                f"Puppet analysis failed: {result.get('failure_reason', 'unknown')}"
            )

        return result["specification"]
