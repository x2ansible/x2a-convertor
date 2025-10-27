"""Planning agent for Chef to Ansible migration.

Analyzes migration plans and creates detailed checklists.
"""

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool

from src.exporters.base_agent import BaseAgent
from src.exporters.state import ChefState
from src.model import get_runnable_config, report_tool_calls
from src.utils.logging import get_logger
from prompts.get_prompt import get_prompt

logger = get_logger(__name__)


class PlanningAgent(BaseAgent):
    """Agent responsible for analyzing migration plans and building checklists.

    This agent:
    - Reads the high-level and module-specific migration plans
    - Analyzes the source Chef repository structure
    - Creates a detailed checklist of files to migrate
    - Categorizes items (templates, recipes, attributes, files, structure)
    """

    # Base tools that this agent always has access to
    BASE_TOOLS = [
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: FileSearchTool(),
    ]

    SYSTEM_PROMPT_NAME = "export_ansible_planning_system"
    USER_PROMPT_NAME = "export_ansible_planning_task"

    def __call__(self, state: ChefState) -> ChefState:
        """Execute planning phase.

        Args:
            state: Current migration state

        Returns:
            Updated ChefState
        """
        slog = logger.bind(phase="plan_migration")
        slog.info("Planning migration: analyzing migration plan and creating checklist")

        agent = self._create_react_agent(state)

        system_message = get_prompt(self.SYSTEM_PROMPT_NAME)
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            module=state.module,
            high_level_migration_plan=state.high_level_migration_plan.to_document(),
            module_migration_plan=state.module_migration_plan.to_document(),
            directory_listing="\n".join(state.directory_listing),
            path=state.path,
            existing_checklist=state.checklist.to_markdown() if state.checklist else "",
        )

        result = agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            get_runnable_config(),
        )

        slog.info(f"Planning agent tools: {report_tool_calls(result).to_string()}")

        assert state.checklist is not None, (
            "Checklist must be created by planning agent"
        )
        state.checklist.save(state.get_checklist_path())
        slog.info(f"Checklist after planning:\n{state.checklist.to_markdown()}")

        return state
