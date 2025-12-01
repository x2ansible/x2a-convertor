"""Chef infrastructure analyzer.

This module implements the main ChefSubagent that orchestrates all Chef analysis.
It maintains backward compatibility with the original implementation while using
clean SOLID/DDD architecture internally.
"""

from dataclasses import dataclass
from pathlib import Path

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from prompts.get_prompt import get_prompt
from src.inputs.tree_analysis import TreeSitterAnalyzer
from src.model import get_last_ai_message, get_model, get_runnable_config
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


class ChefAgentError(Exception):
    """Raised when Chef agent returns invalid response."""


@dataclass
class ChefState:
    """State object for Chef analysis workflow."""

    path: str
    user_message: str
    specification: str
    dependency_paths: list[str]
    export_path: str | None
    structured_analysis: StructuredAnalysis | None = None

    @property
    def all_paths(self) -> list[Path]:
        """Get all paths (main path + dependencies) as Path objects."""
        return [Path(x) for x in [self.path, *self.dependency_paths]]


class ChefSubagent:
    """Main Chef analyzer - implements InfrastructureAnalyzer protocol.

    This class orchestrates all Chef analysis using a LangGraph workflow.
    It composes services following Dependency Injection pattern.

    Workflow phases:
    1. fetch_dependencies - Fetch cookbook dependencies
    2. analyze_structure - Use analysis services to analyze all files
    3. write_report - Generate migration plan using structured analysis
    4. validate_with_analysis - Validate plan against analysis
    5. cleanup_specification - Clean up the specification
    6. cleanup_temp_files - Cleanup temporary files
    """

    def __init__(self, model=None) -> None:
        self.model = model or get_model()

        # Compose services (Dependency Injection)
        self._path_resolver = ChefPathResolver()
        self._recipe_service = RecipeAnalysisService(self.model)
        self._provider_service = ProviderAnalysisService(self.model)
        self._attribute_service = AttributeAnalysisService(self.model)

        # Existing LangGraph components
        self.agent = self._create_agent()
        self._workflow = self._create_workflow()
        self._dependency_fetcher: ChefDependencyManager | None = None

        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_agent(self):
        """Create a LangGraph agent with file management tools."""
        logger.info("Creating chef agent")

        tools = [
            FileSearchTool(),
            ListDirectoryTool(),
            ReadFileTool(),
        ]

        agent = create_react_agent(  # type: ignore[deprecated]
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_workflow(self):
        """Create LangGraph workflow.

        Workflow phases:
        1. fetch_dependencies - Fetch cookbook dependencies
        2. analyze_structure - Use analysis services to analyze all files
        3. write_report - Generate migration plan using structured analysis
        4. validate_with_analysis - Validate plan against analysis
        5. cleanup_specification - Clean up the specification
        6. cleanup_temp_files - Cleanup temporary files
        """
        workflow = StateGraph(ChefState)

        workflow.add_node(
            "fetch_dependencies", lambda state: self._prepare_dependencies(state)
        )
        workflow.add_node(
            "analyze_structure", lambda state: self._analyze_structure(state)
        )
        workflow.add_node("write_report", lambda state: self._write_report(state))
        workflow.add_node(
            "validate_with_analysis", lambda state: self._validate_with_analysis(state)
        )
        workflow.add_node(
            "cleanup_specification", lambda state: self._cleanup_specification(state)
        )

        workflow.set_entry_point("fetch_dependencies")
        workflow.add_edge("fetch_dependencies", "analyze_structure")
        workflow.add_edge("analyze_structure", "write_report")
        workflow.add_edge("write_report", "validate_with_analysis")
        workflow.add_edge("validate_with_analysis", "cleanup_specification")
        workflow.add_edge("cleanup_specification", END)

        return workflow.compile()

    def _prepare_dependencies(self, state: ChefState) -> ChefState:
        """Fetch external dependencies using appropriate strategy."""
        slog = logger.bind(phase="prepare_dependencies")
        slog.info(f"Checking for external dependencies for {state.path}")

        # Initialize dependency manager
        try:
            self._dependency_fetcher = ChefDependencyManager(state.path)
            slog.info(f"Using {self._dependency_fetcher._strategy.__class__.__name__}")
        except RuntimeError as e:
            slog.error(f"Failed to initialize dependency manager: {e}")
            state.dependency_paths = [f"{state.path}/cookbooks"]
            state.export_path = None
            return state

        # Check for dependencies
        has_deps, deps = self._dependency_fetcher.has_dependencies()
        if not has_deps:
            slog.info("No external dependencies found, using local cookbooks only")
            state.dependency_paths = [f"{state.path}/cookbooks"]
            state.export_path = None
            return state

        # Fetch dependencies
        slog.info(f"Found {len(deps)} external dependencies, fetching...")
        try:
            self._dependency_fetcher.fetch_dependencies()
            dependency_paths = self._dependency_fetcher.get_dependencies_paths(deps)

            if dependency_paths:
                state.dependency_paths = dependency_paths
                state.export_path = str(self._dependency_fetcher.export_path)
                slog.info(f"Successfully fetched {len(dependency_paths)} dependencies")
            else:
                slog.warning("No dependency paths returned after fetch")
                state.dependency_paths = []
                state.export_path = None

        except RuntimeError as e:
            slog.warning(f"Failed to fetch dependencies: {e}")
            state.dependency_paths = []
            state.export_path = None

        return state

    def _analyze_files_by_pattern(
        self,
        paths: list[Path],
        pattern: str,
        file_type: str,
        analysis_service,
        result_class,
        slog,
    ) -> list:
        """Generic method to analyze Chef files matching a pattern.

        Args:
            paths: List of paths to search
            pattern: Glob pattern (e.g., "**/recipes/*.rb")
            file_type: Human-readable type for logging (e.g., "recipe")
            analysis_service: Service with analyze() method
            result_class: Result class to instantiate (e.g., RecipeAnalysisResult)
            slog: Structured logger

        Returns:
            List of analysis results
        """
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
        """Build map of collection names to their item keys.

        Args:
            attributes: List of analyzed attribute files
            slog: Structured logger

        Returns:
            Dictionary mapping collection paths to item lists
            Example: {"nginx.sites": ["test.cluster.local", "ci.cluster.local"]}
        """
        attribute_collections = {}

        def find_collections(attrs_dict, path=""):
            """Recursively find collection attributes."""
            for key, value in attrs_dict.items():
                current_path = f"{path}.{key}" if path else key

                if isinstance(value, dict) and len(value) > 1:
                    # Check if all values are dicts (collection pattern)
                    # e.g., sites: {site1: {...}, site2: {...}}
                    all_dict_values = all(isinstance(v, dict) for v in value.values())
                    slog.debug(
                        f"Checking '{current_path}': all_dict_values={all_dict_values}, "
                        f"keys={list(value.keys())[:5]}"
                    )

                    if all_dict_values:
                        # Check if this is a deep collection by recursing first
                        # This ensures we find nginx.sites instead of nginx
                        collections_before = len(attribute_collections)
                        slog.debug(
                            f"Recursing into '{current_path}' "
                            f"(collections_before={collections_before})"
                        )
                        find_collections(value, current_path)
                        collections_added = (
                            len(attribute_collections) - collections_before
                        )
                        slog.debug(
                            f"After recursing '{current_path}': "
                            f"collections_added={collections_added}"
                        )

                        # Only mark as collection if no deeper collections were found
                        if collections_added == 0:
                            # This is a leaf collection
                            attribute_collections[current_path] = list(value.keys())
                            slog.info(
                                f"Found LEAF collection '{current_path}' with "
                                f"{len(value)} items: {list(value.keys())}"
                            )
                    else:
                        # This is just a namespace, recurse deeper
                        slog.debug(f"Namespace '{current_path}', recursing")
                        find_collections(value, current_path)

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

        This phase uses RecipeAnalysisService, ProviderAnalysisService, and
        AttributeAnalysisService to create structured analysis of all Chef files.
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

        # Build collection map for iteration expansion
        attribute_collections = self._build_attribute_collections(attributes, slog)
        slog.info(f"Built iteration map with {len(attribute_collections)} collections")

        # STEP 2: Analyze recipes and providers with iteration context
        slog.info("Step 2: Analyzing recipes and providers")

        # Analyze all recipe files
        recipes = self._analyze_files_by_pattern(
            paths=state.all_paths,
            pattern="**/recipes/*.rb",
            file_type="recipe",
            analysis_service=self._recipe_service,
            result_class=RecipeAnalysisResult,
            slog=slog,
        )

        # Analyze all provider files
        providers = self._analyze_files_by_pattern(
            paths=state.all_paths,
            pattern="**/providers/*.rb",
            file_type="provider",
            analysis_service=self._provider_service,
            result_class=ProviderAnalysisResult,
            slog=slog,
        )

        # Create structured analysis aggregate
        state.structured_analysis = StructuredAnalysis(
            recipes=recipes,
            providers=providers,
            attributes=attributes,
            attribute_collections=attribute_collections,
        )

        slog.info(
            f"Analyzed {len(recipes)} recipes, {len(providers)} providers, "
            f"{len(attributes)} attributes files with {len(attribute_collections)} iterable collections"
        )

        return state

    def _validate_with_analysis(self, state: ChefState) -> ChefState:
        """Validate migration plan against structured analysis.

        This phase ensures the migration plan is consistent with the
        structured analysis from recipes, providers, and attributes.
        """
        slog = logger.bind(phase="validate_with_analysis")
        slog.info("Validating migration plan against structured analysis")

        if not state.structured_analysis:
            slog.warning("No structured analysis available, skipping validation")
            return state

        # Prepare execution tree summary for validation
        analysis_summary = self._build_execution_tree_summary(
            state.structured_analysis, state.path, state.dependency_paths
        )

        # Create validation prompt
        system_message = get_prompt("chef_analysis_validation_system")
        user_prompt = get_prompt("chef_analysis_validation_task").format(
            specification=state.specification,
            analysis_summary=analysis_summary,
        )

        # Execute validation agent
        agent = create_react_agent(model=self.model, tools=[])  # type: ignore[deprecated]
        result = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            config=get_runnable_config(),
        )

        message = get_last_ai_message(result)
        if not message:
            slog.warning("No response from validation agent")
            return state

        validation_response = message.content

        # If validation found issues, append them to specification
        if not validation_response.startswith("VALIDATED:"):
            slog.info("Validation found issues, updating specification")
            state.specification = f"{state.specification}\n\n## VALIDATION NOTES ##\n{validation_response}"
        else:
            slog.info("✓ Specification validated successfully")

        return state

    def _build_execution_tree_summary(
        self,
        analysis: StructuredAnalysis,
        cookbook_path: str,
        dependency_paths: list[str],
    ) -> str:
        """Build and format the execution tree showing complete recipe flow."""
        lines = []

        lines.append("=" * 80)
        lines.append("CHEF RECIPE EXECUTION TREE")
        lines.append("=" * 80)
        lines.append("")
        lines.append(f"Total files analyzed: {analysis.get_total_files_analyzed()}")
        lines.append("")

        # Find the entry recipe (usually default.rb in the main cookbook)
        entry_recipe = None
        for recipe_result in analysis.recipes:
            if (
                "default.rb" in recipe_result.file_path
                and cookbook_path in recipe_result.file_path
            ):
                entry_recipe = recipe_result.file_path
                break

        if not entry_recipe and analysis.recipes:
            # Fallback to first recipe if no default.rb found
            entry_recipe = analysis.recipes[0].file_path

        if entry_recipe:
            # Build execution tree
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

        lines.append("")
        lines.append("=" * 80)
        lines.append("")

        # Still show iteration collections summary at the bottom
        if analysis.attribute_collections:
            lines.append("ITERATION COLLECTIONS DETECTED:")
            lines.append("")
            for collection_name, items in analysis.attribute_collections.items():
                lines.append(f"  {collection_name}: {len(items)} items")
                lines.append(f"    → {', '.join(items)}")
            lines.append("")
            lines.append("=" * 80)
            lines.append("")

        return "\n".join(lines)

    def _cleanup_specification(self, state: ChefState) -> ChefState:
        """Clean up the messy specification with validation updates."""
        slog = logger.bind(phase="cleanup_specification")
        slog.info("Cleaning up migration specification")

        # Prepare cleanup prompts
        system_message = get_prompt("chef_analysis_cleanup_system")
        user_prompt = get_prompt("chef_analysis_cleanup_task").format(
            messy_specification=state.specification
        )

        agent = create_react_agent(  # type: ignore[deprecated]
            model=self.model,
            tools=[],
        )
        # Execute cleanup agent
        result = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            config=get_runnable_config(),
        )

        message = get_last_ai_message(result)
        if not message:
            slog.warning("No valid response from cleanup agent")
            return state

        state.specification = message.content

        return state

    def _write_report(self, state: ChefState) -> ChefState:
        """Generate migration specification using structured analysis."""
        slog = logger.bind(phase="write_report")
        slog.info("Generating migration specification")
        data_list = (
            "\n".join(state.structured_analysis.analyzed_file_paths)
            if state.structured_analysis
            else ""
        )

        # Generate tree-sitter analysis report
        analyzer = TreeSitterAnalyzer()
        try:
            tree_sitter_report = analyzer.report_directory(state.path)
        except Exception as e:
            slog.warning(f"Failed to generate tree-sitter report: {e}")
            tree_sitter_report = "Tree-sitter analysis not available"

        # Build execution tree if available
        execution_tree_summary = ""
        if state.structured_analysis:
            execution_tree_summary = self._build_execution_tree_summary(
                state.structured_analysis, state.path, state.dependency_paths
            )
            slog.info(
                f"Built execution tree from {state.structured_analysis.get_total_files_analyzed()} analyzed files"
            )
        else:
            slog.warning("No structured analysis available")

        # Prepare system and user messages for chef agent
        system_message = get_prompt("chef_analysis_system")
        user_prompt = get_prompt("chef_analysis_task").format(
            path=state.path,
            user_message=state.user_message,
            directory_listing=data_list,
            tree_sitter_report=tree_sitter_report,
            execution_tree=execution_tree_summary,
        )
        # Execute chef agent with both system and user messages
        result = self.agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            config=get_runnable_config(),
        )
        messages = result.get("messages", [])
        if len(messages) < 2:
            raise ChefAgentError("Invalid response from Chef agent")

        state.specification = messages[-1].content
        slog.info("✓ Migration specification generated")
        return state

    def invoke(self, path: str, user_message: str) -> str:
        """Analyze a Chef cookbook and return migration plan.

        This method satisfies the InfrastructureAnalyzer protocol.

        Args:
            path: Path to Chef cookbook
            user_message: User's migration requirements

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
        )

        result = self._workflow.invoke(initial_state, config=get_runnable_config())
        return result["specification"]
