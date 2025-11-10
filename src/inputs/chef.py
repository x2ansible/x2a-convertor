from dataclasses import dataclass

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent

from prompts.get_prompt import get_prompt
from src.inputs.chef_dependency_fetcher import ChefDependencyManager
from src.inputs.tree_analysis import TreeSitterAnalyzer
from src.model import get_last_ai_message, get_model, get_runnable_config
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ChefAgentError(Exception):
    """Raised when Chef agent returns invalid response."""


@dataclass
class ChefState:
    path: str
    user_message: str
    specification: str
    dependency_paths: list[str]
    export_path: str | None


class ChefSubagent:
    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self.agent = self._create_agent()
        self._workflow = self._create_workflow()
        self._dependency_fetcher: ChefDependencyManager | None = None
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_agent(self):
        """Create a LangGraph agent with file management tools for migration planning"""
        logger.info("Creating chef agent")

        # Set up file management tools
        tools = [
            FileSearchTool(),
            ListDirectoryTool(),
            ReadFileTool(),
        ]

        # Create the agent with higher recursion limit
        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_workflow(self):
        workflow = StateGraph(ChefState)
        workflow.add_node(
            "fetch_dependencies", lambda state: self._prepare_dependencies(state)
        )
        workflow.add_node("write_report", lambda state: self._write_report(state))
        workflow.add_node("check_files", lambda state: self._check_files(state))
        workflow.add_node(
            "cleanup_specification", lambda state: self._cleanup_specification(state)
        )
        workflow.add_node(
            "cleanup_temp_files", lambda state: self._cleanup_temp_files(state)
        )

        workflow.set_entry_point("fetch_dependencies")
        workflow.add_edge("fetch_dependencies", "write_report")
        workflow.add_edge("write_report", "check_files")
        workflow.add_edge("check_files", "cleanup_specification")
        workflow.add_edge("cleanup_specification", "cleanup_temp_files")
        workflow.add_edge("cleanup_temp_files", END)

        return workflow.compile()

    def list_files(self, paths: list[str]) -> list[str]:
        """Search multiple paths for cookbook files"""
        search_tool = FileSearchTool()
        all_files = []

        for path in paths:
            try:
                files = search_tool.run({"dir_path": path, "pattern": "*"}).splitlines()
                all_files.extend([f"{path}/{x}" for x in files])
            except Exception as e:
                logger.warning(f"Error listing files in {path}: {e}")
                continue

        return all_files

    def _prepare_dependencies(self, state: ChefState) -> ChefState:
        """Fetch external dependencies using chef-cli"""
        slog = logger.bind(phase="prepare_dependencies")
        slog.info(f"Checking for external dependencies for {state.path}")
        self._dependency_fetcher = ChefDependencyManager(state.path)

        has_deps, deps = self._dependency_fetcher.has_dependencies()
        if not has_deps:
            slog.info("No external dependencies found, using local cookbooks only")
            state.dependency_paths = [f"{state.path}/cookbooks"]
            state.export_path = None
            return state

        slog.info("Found external dependencies, fetching with chef-cli...")
        self._dependency_fetcher.fetch_dependencies()
        try:
            dependency_paths = self._dependency_fetcher.get_dependencies_paths(deps)
            if dependency_paths:
                state.dependency_paths = dependency_paths
                state.export_path = str(self._dependency_fetcher.export_path)
        except RuntimeError:
            slog.warning(
                "PolicyLock has not been found, so there is no dependency path"
            )
            state.dependency_paths = []
            state.export_path = None

        return state

    def _cleanup_temp_files(self, state: ChefState) -> ChefState:
        """Cleanup temporary dependency files"""
        if self._dependency_fetcher:
            self._dependency_fetcher.cleanup()

        return state

    def _check_files(self, state: ChefState) -> ChefState:
        """Validate and improve migration plan by analyzing each file"""
        files = self.list_files([state.path, *state.dependency_paths])
        read_tool = ReadFileTool()
        slog = logger.bind(phase="check_files")
        slog.info(f"Validating migration plan against {len(files)} files")

        # TODO: Rethink following.
        # Maybe run this in parallel, there can be many files and it takes forever to finish on a more complex example
        for i, fp in enumerate(files):
            try:
                # Read the file content
                file_content = read_tool.run({"file_path": fp})

                # Skip empty files or binary files
                if not file_content or not isinstance(file_content, str):
                    continue

                # Prepare validation prompts
                system_message = get_prompt("chef_analysis_file_validation_system")
                user_prompt = get_prompt("chef_analysis_file_validation_task").format(
                    current_specification=state.specification,
                    file_path=fp,
                    file_content=file_content,
                )

                # Execute validation agent
                result = self.agent.invoke(
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
                    slog.info("There is no response from AI on file '{fp}'")
                    continue
                validation_response = message.content
                if validation_response.startswith("VALIDATED:"):
                    slog.debug(f"File validated: {fp} - {validation_response}")
                    continue
                if validation_response.startswith("SKIP:"):
                    slog.debug(f"File skipped: {fp} - {validation_response}")
                    continue

                slog.info(f"Updating specification based on file: {fp}")
                state.specification = self._merge_specification_update(
                    state.specification, validation_response
                )
            except Exception as e:
                slog.warning(f"Error processing file {fp}: {e}")
                continue

        slog.info("File validation completed")
        return state

    def _merge_specification_update(self, current_spec: str, update: str) -> str:
        """Merge updated section into the current specification"""
        # Simple merge strategy - append the update for now
        # In a more sophisticated implementation, you could parse sections
        # and replace specific parts of the specification
        if not current_spec:
            return update

        return f"{current_spec}\n\n## VALIDATION UPDATE ##\n{update}"

    def _cleanup_specification(self, state: ChefState) -> ChefState:
        """Clean up the messy specification with validation updates"""

        slog = logger.bind(phase="cleanup_specification")
        slog.info("Cleaning up migration specification")

        # Prepare cleanup prompts
        system_message = get_prompt("chef_analysis_cleanup_system")
        user_prompt = get_prompt("chef_analysis_cleanup_task").format(
            messy_specification=state.specification
        )

        # pyrefly: ignore
        agent = create_react_agent(
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
        logger.info(f"Writing Chef report for {state!s}")
        data_list = "\n".join(self.list_files([state.path, *state.dependency_paths]))
        # Generate tree-sitter analysis report
        analyzer = TreeSitterAnalyzer()
        try:
            tree_sitter_report = analyzer.report_directory(state.path)
        except Exception as e:
            logger.warning(f"Failed to generate tree-sitter report: {e}")
            tree_sitter_report = "Tree-sitter analysis not available"

        # Prepare system and user messages for chef agent
        system_message = get_prompt("chef_analysis_system")
        user_prompt = get_prompt("chef_analysis_task").format(
            path=state.path,
            user_message=state.user_message,
            directory_listing=data_list,
            tree_sitter_report=tree_sitter_report,
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
        return state

    def invoke(self, path: str, user_message: str) -> str:
        """Analyze a Chef cookbook and return migration plan"""
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


def get_chef_agent():
    """Legacy function for backward compatibility"""
    return ChefSubagent().agent
