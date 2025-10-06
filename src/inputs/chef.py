import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langgraph.prebuilt import create_react_agent

from src.model import get_model, get_last_ai_message
from prompts.get_prompt import get_prompt
from src.inputs.tree_analysis import TreeSitterAnalyzer

logger = logging.getLogger(__name__)


class ChefState(TypedDict):
    path: str
    user_message: str
    specification: str


class ChefSubagent:
    def __init__(self, model=None):
        self.model = model or get_model()
        self.agent = self._create_agent()
        self._workflow = self._create_workflow()
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
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_workflow(self):
        workflow = StateGraph(ChefState)
        workflow.add_node("write_report", self._write_report)
        workflow.add_node("check_files", self._check_files)
        workflow.add_node("cleanup_specification", self._cleanup_specification)

        workflow.set_entry_point("write_report")
        workflow.add_edge("write_report", "check_files")
        workflow.add_edge("check_files", "cleanup_specification")
        workflow.add_edge("cleanup_specification", END)

        return workflow.compile()

    def list_files(self, path: str) -> [str]:
        search_tool = FileSearchTool()
        files = search_tool.run({"dir_path": path, "pattern": "*"}).splitlines()
        return [f"{path}/{x}" for x in files]

    def _check_files(self, state: ChefState) -> ChefState:
        """Validate and improve migration plan by analyzing each file"""
        files = self.list_files(state["path"])
        read_tool = ReadFileTool()

        logger.info(f"Validating migration plan against {len(files)} files")

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
                    current_specification=state["specification"],
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
                    }
                )
                message = get_last_ai_message(result)
                if not message:
                    logger.info("There is no response from AI on file '{fp}'")
                    continue
                validation_response = message.content
                if validation_response.startswith("VALIDATED:"):
                    logger.debug(f"File validated: {fp} - {validation_response}")
                    continue
                if validation_response.startswith("SKIP:"):
                    logger.debug(f"File skipped: {fp} - {validation_response}")
                    continue

                logger.info(f"Updating specification based on file: {fp}")
                state["specification"] = self._merge_specification_update(
                    state["specification"], validation_response
                )
            except Exception as e:
                logger.warning(f"Error processing file {fp}: {e}")
                continue

        logger.info("File validation completed")
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
        logger.info("Cleaning up migration specification")

        # Prepare cleanup prompts
        system_message = get_prompt("chef_analysis_cleanup_system")
        user_prompt = get_prompt("chef_analysis_cleanup_task").format(
            messy_specification=state["specification"]
        )

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
            }
        )

        message = get_last_ai_message(result)
        if not message:
            logger.warning("No valid response from cleanup agent")
            return state

        state["specification"] = message.content

        return state

    def _write_report(self, state: ChefState) -> ChefState:
        search_tool = FileSearchTool()
        all_files = search_tool.run({"dir_path": state["path"], "pattern": "*"})

        # Generate tree-sitter analysis report
        analyzer = TreeSitterAnalyzer()
        try:
            tree_sitter_report = analyzer.report_directory(state["path"])
        except Exception as e:
            logger.warning(f"Failed to generate tree-sitter report: {e}")
            tree_sitter_report = "Tree-sitter analysis not available"

        # Prepare system and user messages for chef agent
        system_message = get_prompt("chef_analysis_system")
        user_prompt = get_prompt("chef_analysis_task").format(
            path=state["path"],
            user_message=state["user_message"],
            directory_listing=all_files,
            tree_sitter_report=tree_sitter_report,
        )

        # Execute chef agent with both system and user messages
        result = self.agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            }
        )
        result_messages_len = len(result.get("messages"))
        if result_messages_len < 2:
            raise Exception("Invalid response from Chef agent")

        state["specification"] = result.get("messages", ["No response"])[-1].content
        return state

    def invoke(self, path: str, user_message: str) -> str:
        """Analyze a Chef cookbook and return migration plan"""
        logger.info("Using Chef agent for migration analysis...")

        initial_state = ChefState(
            path=path,
            user_message=user_message,
            specification="",
        )

        result = self._workflow.invoke(initial_state)
        initial_state["specification"] = result["specification"]
        return initial_state["specification"]


def get_chef_agent():
    """Legacy function for backward compatibility"""
    return ChefSubagent().agent
