"""Chef infrastructure analyzer.

This module implements the main ChefSubagent that orchestrates all Chef analysis.
It composes BaseAgent subclasses as graph nodes following the pattern from
src/exporters/chef_to_ansible.py.
"""

from pathlib import Path
from typing import Literal

from langgraph.graph import END, StateGraph

from src.inputs.chef.analysis_validation_agent import AnalysisValidationAgent
from src.inputs.chef.cleanup_agent import CleanupAgent
from src.inputs.chef.report_writer_agent import ReportWriterAgent
from src.inputs.chef.state import ChefState
from src.model import get_model, get_runnable_config
from src.types import Telemetry
from src.utils.logging import get_logger

from .dependency_fetcher import ChefDependencyManager
from .execution_tree_builder import ExecutionTreeBuilder
from .models import (
    AttributesAnalysisResult,
    ProviderAnalysisResult,
    RecipeAnalysisResult,
    StructuredAnalysis,
)
from .path_resolver import ChefPathResolver
from .services import (
    AttributeAnalysisService,
    ProviderAnalysisService,
    RecipeAnalysisService,
)

logger = get_logger(__name__)


class ChefSubagent:
    """Main Chef analyzer - implements InfrastructureAnalyzer protocol.

    This class orchestrates all Chef analysis using a LangGraph workflow.
    It composes services and BaseAgent subclasses following DDD patterns.

    Workflow phases:
    1. fetch_dependencies - Fetch cookbook dependencies
    2. analyze_structure - Use analysis services to analyze all files
    3. write_report - Generate migration plan using ReportWriterAgent
    4. validate_with_analysis - Validate plan using AnalysisValidationAgent
    5. cleanup_specification - Clean up using CleanupAgent
    """

    def __init__(self, model=None) -> None:
        self.model = model or get_model()

        # Compose services (Dependency Injection)
        self._path_resolver = ChefPathResolver()
        self._recipe_service = RecipeAnalysisService(self.model)
        self._provider_service = ProviderAnalysisService(self.model)
        self._attribute_service = AttributeAnalysisService(self.model)

        # Compose agents
        self._report_writer = ReportWriterAgent(model=self.model)
        self._analysis_validator = AnalysisValidationAgent(model=self.model)
        self._cleanup = CleanupAgent(model=self.model)

        self._dependency_fetcher: ChefDependencyManager | None = None
        self._workflow = self._create_workflow()

        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_workflow(self):
        """Create LangGraph workflow composing agents as nodes."""
        workflow = StateGraph(ChefState)

        workflow.add_node(
            "fetch_dependencies", lambda state: self._prepare_dependencies(state)
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
            {
                "continue": "validate_with_analysis",
                "failed": END,
            },
        )
        workflow.add_conditional_edges(
            "validate_with_analysis",
            self._check_failure_after_agent,
            {
                "continue": "cleanup_specification",
                "failed": END,
            },
        )
        workflow.add_edge("cleanup_specification", END)

        return workflow.compile()

    def _check_failure_after_agent(
        self, state: ChefState
    ) -> Literal["continue", "failed"]:
        """Conditional edge: check if agent failed, route to END or next phase."""
        if state.failed:
            logger.error(f"Agent failed: {state.failure_reason}")
            return "failed"
        return "continue"

    def _prepare_dependencies(self, state: ChefState) -> ChefState:
        """Fetch external dependencies using appropriate strategy."""
        slog = logger.bind(phase="prepare_dependencies")
        slog.info(f"Checking for external dependencies for {state.path}")

        try:
            self._dependency_fetcher = ChefDependencyManager(state.path)
            slog.info(f"Using {self._dependency_fetcher._strategy.__class__.__name__}")
        except RuntimeError as e:
            slog.error(f"Failed to initialize dependency manager: {e}")
            return state.update(
                dependency_paths=[f"{state.path}/cookbooks"], export_path=None
            )

        has_deps, deps = self._dependency_fetcher.has_dependencies()
        if not has_deps:
            slog.info("No external dependencies found, using local cookbooks only")
            return state.update(
                dependency_paths=[f"{state.path}/cookbooks"], export_path=None
            )

        slog.info(f"Found {len(deps)} external dependencies, fetching...")
        return self._fetch_dependencies(state, deps, slog)

    def _fetch_dependencies(self, state: ChefState, deps: list, slog) -> ChefState:
        """Fetch and resolve dependency paths."""
        assert self._dependency_fetcher is not None

        try:
            self._dependency_fetcher.fetch_dependencies()
            dependency_paths = self._dependency_fetcher.get_dependencies_paths(deps)

            if not dependency_paths:
                slog.warning("No dependency paths returned after fetch")
                return state.update(dependency_paths=[], export_path=None)

            slog.info(f"Successfully fetched {len(dependency_paths)} dependencies")
            return state.update(
                dependency_paths=dependency_paths,
                export_path=str(self._dependency_fetcher.export_path),
            )

        except RuntimeError as e:
            slog.warning(f"Failed to fetch dependencies: {e}")
            return state.update(dependency_paths=[], export_path=None)

    def _analyze_files_by_pattern(
        self,
        paths: list[Path],
        pattern: str,
        file_type: str,
        analysis_service,
        result_class,
        slog,
    ) -> list:
        """Generic method to analyze Chef files matching a pattern."""
        results = []

        for path in paths:
            if not path.exists():
                slog.warning(f"Path does not exist: {path}")
                continue

            for file_path in path.glob(pattern):
                try:
                    slog.debug(f"Analyzing {file_type}: {file_path}")
                    analysis = analysis_service.analyze(file_path)
                    results.append(
                        result_class(file_path=str(file_path), analysis=analysis)
                    )
                except Exception as e:
                    slog.warning(f"Failed to analyze {file_type} {file_path}: {e}")

        return results

    def _build_attribute_collections(
        self, attributes: list[AttributesAnalysisResult], slog
    ) -> dict[str, list[str]]:
        """Build map of collection names to their item keys."""
        attribute_collections: dict[str, list[str]] = {}

        def find_collections(attrs_dict, path=""):
            """Recursively find collection attributes."""
            for key, value in attrs_dict.items():
                current_path = f"{path}.{key}" if path else key

                if not isinstance(value, dict) or len(value) <= 1:
                    continue

                all_dict_values = all(isinstance(v, dict) for v in value.values())
                slog.debug(
                    f"Checking '{current_path}': all_dict_values={all_dict_values}, "
                    f"keys={list(value.keys())[:5]}"
                )

                if not all_dict_values:
                    slog.debug(f"Namespace '{current_path}', recursing")
                    find_collections(value, current_path)
                    continue

                collections_before = len(attribute_collections)
                slog.debug(
                    f"Recursing into '{current_path}' "
                    f"(collections_before={collections_before})"
                )
                find_collections(value, current_path)
                collections_added = len(attribute_collections) - collections_before
                slog.debug(
                    f"After recursing '{current_path}': "
                    f"collections_added={collections_added}"
                )

                if collections_added == 0:
                    attribute_collections[current_path] = list(value.keys())
                    slog.info(
                        f"Found LEAF collection '{current_path}' with "
                        f"{len(value)} items: {list(value.keys())}"
                    )

        for attr_result in attributes:
            try:
                find_collections(attr_result.analysis.attributes)
            except Exception as e:
                slog.warning(
                    f"Failed to build collections from {attr_result.file_path}: {e}"
                )

        return attribute_collections

    def _analyze_structure(self, state: ChefState) -> ChefState:
        """Analyze cookbook structure using analysis services.

        This phase uses analysis services to create structured analysis
        of all Chef files, then precomputes the execution tree summary.
        """
        slog = logger.bind(phase="analyze_structure")
        slog.info("Starting structured analysis of cookbook files")

        # STEP 1: Analyze attributes FIRST to build collection map
        slog.info("Step 1: Analyzing attributes to build iteration map")
        attributes = self._analyze_files_by_pattern(
            paths=state.all_paths,
            pattern="**/attributes/default.rb",
            file_type="attributes",
            analysis_service=self._attribute_service,
            result_class=AttributesAnalysisResult,
            slog=slog,
        )
        attribute_collections = self._build_attribute_collections(attributes, slog)
        slog.info(f"Built iteration map with {len(attribute_collections)} collections")

        # STEP 2: Analyze recipes and providers
        slog.info("Step 2: Analyzing recipes and providers")
        recipes = self._analyze_files_by_pattern(
            paths=state.all_paths,
            pattern="**/recipes/*.rb",
            file_type="recipe",
            analysis_service=self._recipe_service,
            result_class=RecipeAnalysisResult,
            slog=slog,
        )
        providers = self._analyze_files_by_pattern(
            paths=state.all_paths,
            pattern="**/providers/*.rb",
            file_type="provider",
            analysis_service=self._provider_service,
            result_class=ProviderAnalysisResult,
            slog=slog,
        )

        structured_analysis = StructuredAnalysis(
            recipes=recipes,
            providers=providers,
            attributes=attributes,
            attribute_collections=attribute_collections,
        )

        slog.info(
            f"Analyzed {len(recipes)} recipes, {len(providers)} providers, "
            f"{len(attributes)} attributes files with "
            f"{len(attribute_collections)} iterable collections"
        )

        # Precompute execution tree summary for downstream agents
        execution_tree_summary = self._build_execution_tree_summary(
            structured_analysis, state.path, state.dependency_paths
        )

        return state.update(
            structured_analysis=structured_analysis,
            execution_tree_summary=execution_tree_summary,
        )

    def _build_execution_tree_summary(
        self,
        analysis: StructuredAnalysis,
        cookbook_path: str,
        dependency_paths: list[str],
    ) -> str:
        """Build and format the execution tree showing complete recipe flow."""
        lines = [
            "=" * 80,
            "CHEF RECIPE EXECUTION TREE",
            "=" * 80,
            "",
            f"Total files analyzed: {analysis.get_total_files_analyzed()}",
            "",
        ]

        entry_recipe = self._find_entry_recipe(analysis, cookbook_path)

        if entry_recipe:
            tree_builder = ExecutionTreeBuilder(
                structured_analysis=analysis,
                path_resolver=self._path_resolver,
                dependency_paths=dependency_paths,
            )
            tree_root = tree_builder.build_tree(entry_recipe)
            tree_formatted = tree_builder.format_tree(tree_root)

            lines.append("Execution flow starting from entry recipe:")
            lines.append("")
            lines.append(tree_formatted)
        else:
            lines.append("No entry recipe found (expected default.rb)")

        lines.extend(["", "=" * 80, ""])

        if analysis.attribute_collections:
            lines.append("ITERATION COLLECTIONS DETECTED:")
            lines.append("")
            for collection_name, items in analysis.attribute_collections.items():
                lines.append(f"  {collection_name}: {len(items)} items")
                lines.append(f"    → {', '.join(items)}")
            lines.extend(["", "=" * 80, ""])

        return "\n".join(lines)

    def _find_entry_recipe(
        self, analysis: StructuredAnalysis, cookbook_path: str
    ) -> str | None:
        """Find the entry recipe (usually default.rb in the main cookbook)."""
        for recipe_result in analysis.recipes:
            if (
                "default.rb" in recipe_result.file_path
                and cookbook_path in recipe_result.file_path
            ):
                return recipe_result.file_path

        if analysis.recipes:
            return analysis.recipes[0].file_path

        return None

    def invoke(
        self, path: str, user_message: str, telemetry: Telemetry | None = None
    ) -> str:
        """Analyze a Chef cookbook and return migration plan.

        This method satisfies the InfrastructureAnalyzer protocol.

        Args:
            path: Path to Chef cookbook
            user_message: User's migration requirements
            telemetry: Optional telemetry collector for tracking tool calls

        Returns:
            Migration specification as markdown string
        """
        logger.info("Using Chef agent for migration analysis...")

        initial_state = ChefState(
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
                f"Chef analysis failed: {result.get('failure_reason', 'unknown')}"
            )

        return result["specification"]
