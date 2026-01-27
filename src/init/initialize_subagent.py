"""Initialize subagent for init workflow.

This module contains the ReAct agent that explores the repository
and creates the migration-plan.md file.
"""

from collections.abc import Sequence
from pathlib import Path

from langchain.agents import create_agent
from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from prompts.get_prompt import get_prompt
from src.const import MIGRATION_PLAN_FILE
from src.init.init_state import InitState
from src.model import get_model, get_runnable_config, report_tool_calls
from src.types import telemetry_context
from src.utils.logging import get_logger

logger = get_logger(__name__)


class InitializeSubAgent:
    """ReAct agent that explores repository and creates migration-plan.md."""

    def __init__(self, model=None):
        self.model = model or get_model()

    def __call__(self, state: InitState) -> InitState:
        """Execute planning agent to generate migration plan.

        Args:
            state: Current init state with user requirements and directory listing

        Returns:
            Updated state with migration_plan_content and migration_plan_path set,
            or state marked as failed if plan creation failed
        """
        slog = logger.bind(phase="initialize_planning")
        slog.info("Starting migration planning agent")

        with telemetry_context(state.telemetry, "MigrationPlanningAgent") as metrics:
            agent = self._create_react_agent()

            # Prepare system and user messages
            system_message = get_prompt("init_migration_instructions").format(
                migration_plan_file=MIGRATION_PLAN_FILE
            )
            user_message = get_prompt("init_migration_plan_request").format(
                user_requirements=state.user_message,
                migration_plan_file=MIGRATION_PLAN_FILE,
                files=state.directory_listing,
            )
            slog.debug(f"User prompt for planning agent: {user_message[:200]}...")

            result = agent.invoke(
                {
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_message},
                    ]
                },
                config=get_runnable_config(),
            )

            # Record telemetry
            if metrics:
                tool_calls = report_tool_calls(result)
                metrics.record_tool_calls(tool_calls)
                slog.info(f"Planning agent tools: {tool_calls.to_string()}")

            # Print messages for visibility
            for msg in result["messages"]:
                msg.pretty_print()

            # Check if plan was created
            migration_plan_path = Path(MIGRATION_PLAN_FILE)
            if migration_plan_path.exists():
                migration_plan_content = migration_plan_path.read_text()
                slog.info(f"Migration plan created successfully: {MIGRATION_PLAN_FILE}")
                return state.update(
                    migration_plan_content=migration_plan_content,
                    migration_plan_path=MIGRATION_PLAN_FILE,
                )

            slog.error("Migration plan was not created by agent")
            return state.mark_failed("Migration plan was not created")

    def _create_react_agent(self) -> CompiledStateGraph:
        """Create a LangGraph ReAct agent with file management tools.

        Returns:
            Compiled LangGraph agent ready for invocation
        """
        slog = logger.bind(phase="initialize_planning")
        slog.debug("Creating migration planning ReAct agent")

        # Set up file management tools
        tools: Sequence[BaseTool] = [
            FileSearchTool(),
            ListDirectoryTool(),
            ReadFileTool(),
            WriteFileTool(),
        ]

        # Create agent without prompt (prompt is passed during invocation)
        agent = create_agent(model=self.model, tools=tools)  # pyrefly: ignore
        return agent
