"""Initialize subagent for init workflow.

This module contains the ReAct agent that explores the repository
and creates the migration-plan.md file.
"""

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.const import MIGRATION_PLAN_FILE
from src.init.init_state import InitState
from src.types.telemetry import AgentMetrics


class InitializeSubAgent(BaseAgent[InitState]):
    """ReAct agent that explores repository and creates migration-plan.md.

    Uses file management tools to explore the source directory structure
    and generate a high-level migration plan document.
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: WriteFileTool(),
    ]

    SYSTEM_PROMPT_NAME = "init_migration_instructions"
    USER_PROMPT_NAME = "init_migration_plan_request"

    def execute(self, state: InitState, metrics: AgentMetrics | None) -> InitState:
        """Execute planning agent to generate migration plan.

        Args:
            state: Current init state with user requirements and directory listing
            metrics: Telemetry metrics collector

        Returns:
            Updated state with migration_plan_content and migration_plan_path set,
            or state marked as failed if plan creation failed
        """
        self._log.info("Starting migration planning agent")

        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format(
            migration_plan_file=MIGRATION_PLAN_FILE
        )
        user_message = get_prompt(self.USER_PROMPT_NAME).format(
            user_requirements=state.user_message,
            migration_plan_file=MIGRATION_PLAN_FILE,
            files=state.directory_listing,
        )
        self._log.debug(f"User prompt for planning agent: {user_message[:200]}...")

        result = self.invoke_react(
            state,
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            metrics,
        )

        # Print messages for visibility
        for msg in result["messages"]:
            msg.pretty_print()

        # Check if plan was created
        migration_plan_path = Path(MIGRATION_PLAN_FILE)
        if migration_plan_path.exists():
            migration_plan_content = migration_plan_path.read_text()
            self._log.info(
                f"Migration plan created successfully: {MIGRATION_PLAN_FILE}"
            )
            return state.update(
                migration_plan_content=migration_plan_content,
                migration_plan_path=MIGRATION_PLAN_FILE,
            )

        self._log.error("Migration plan was not created by agent")
        return state.mark_failed("Migration plan was not created")
