"""Planning agent for Chef to Ansible migration.

Analyzes migration plans and creates detailed checklists.
"""

from collections.abc import Callable
from typing import ClassVar

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.exporters.state import ChefState
from src.types.telemetry import AgentMetrics


class PlanningAgent(BaseAgent[ChefState]):
    """Agent responsible for analyzing migration plans and building checklists.

    This agent:
    - Reads the high-level and module-specific migration plans
    - Analyzes the source Chef repository structure
    - Creates a detailed checklist of files to migrate
    - Categorizes items (templates, recipes, attributes, files, structure)
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: FileSearchTool(),
    ]

    SYSTEM_PROMPT_NAME = "export_ansible_planning_system"
    USER_PROMPT_NAME = "export_ansible_planning_task"

    def extra_tools_from_state(self, state: ChefState) -> list[BaseTool]:
        if state.checklist is None:
            return []
        return state.checklist.get_tools()

    def execute(self, state: ChefState, metrics: AgentMetrics | None) -> ChefState:
        """Execute planning phase."""
        self._log.info(
            "Planning migration: analyzing migration plan and creating checklist"
        )

        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            module=state.module,
            high_level_migration_plan=state.high_level_migration_plan,
            module_migration_plan=state.module_migration_plan.to_document(),
            path=state.path,
            existing_checklist=state.checklist.to_markdown() if state.checklist else "",
        )

        self.invoke_react(
            state,
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            metrics,
        )

        assert state.checklist is not None, (
            "Checklist must be created by planning agent"
        )
        state.checklist.save(state.get_checklist_path())
        self._log.info(f"Checklist after planning:\n{state.checklist.to_markdown()}")

        return state
