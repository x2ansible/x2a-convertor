import logging
from enum import Enum
from pathlib import Path
from typing import Literal, TypedDict

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent


from src.model import (
    get_model,
    get_last_ai_message,
    report_tool_calls,
    get_runnable_config,
)
from src.types import (
    DocumentFile,
    Checklist,
    MigrationCategory,
    ChecklistStatus,
)
from prompts.get_prompt import get_prompt
from src.utils.config import MAX_EXPORT_ATTEMPTS
from tools.ansible import AnsibleWriteTool
from tools.ansible_lint import AnsibleLintTool
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.diff_file import DiffFileTool
from tools.checklist import create_checklist_tools

logger = logging.getLogger(__name__)

# Constants
ANSIBLE_PATH_TEMPLATE = "./ansible/{module}"
CHECKLIST_FILENAME = ".checklist.json"
PROCESSABLE_STATUSES = {
    ChecklistStatus.PENDING,
    ChecklistStatus.MISSING,
    ChecklistStatus.ERROR,
}


class MigrationPhase(str, Enum):
    """Phases of the migration workflow"""

    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETE = "complete"


class ChefState(TypedDict):
    path: str
    module: str
    user_message: str
    module_migration_plan: DocumentFile
    high_level_migration_plan: DocumentFile
    directory_listing: list[str]
    checklist: Checklist
    current_phase: str
    export_attempt_counter: int
    validation_report: str
    last_output: str


class ChefToAnsibleSubagent:
    """Subagent called by the MigrationAgent to do the actual Chef -> Ansible export

    Uses a three-agent workflow:
    1. Planning Agent: Analyzes migration plan and creates detailed checklist
    2. Execution Agent: Processes checklist items and generates Ansible artifacts
    3. Validation Agent: Verifies artifacts and updates checklist status
    """

    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self.execution_agent = self._create_execution_agent()
        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _get_ansible_path(self, module: str) -> str:
        """Get the Ansible output path for a module"""
        return ANSIBLE_PATH_TEMPLATE.format(module=module)

    def _get_checklist_path(self, module: str) -> Path:
        """Get the path to the checklist JSON file"""
        return Path(self._get_ansible_path(module)) / CHECKLIST_FILENAME

    def _create_planning_agent(self, checklist: Checklist, checklist_path: Path):
        """Create agent for analyzing migration plan and building checklist

        Args:
            checklist: Checklist instance to inject into tools
            checklist_path: Path to checklist JSON file
        """
        logger.info("Creating migration planning agent")

        tools = [
            ListDirectoryTool(),
            ReadFileTool(),
            FileSearchTool(),
            # Add checklist tools for LLM to populate checklist
            *create_checklist_tools(checklist, checklist_path, include_add=True),
        ]

        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_execution_agent(self):
        """Create agent for executing migrations and generating Ansible files"""
        logger.info("Creating migration execution agent")

        tools = [
            FileSearchTool(),
            ListDirectoryTool(),
            ReadFileTool(),
            WriteFileTool(),
            CopyFileWithMkdirTool(),
            AnsibleWriteTool(),
            AnsibleLintTool(),
            AnsibleRoleCheckTool(),
        ]

        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_validation_agent(self, checklist: Checklist, checklist_path: Path):
        """Create agent for validating migration completeness and correctness

        Args:
            checklist: Checklist instance to inject into tools
            checklist_path: Path to checklist JSON file
        """
        logger.info("Creating migration validation agent")

        tools = [
            ReadFileTool(),
            DiffFileTool(),
            ListDirectoryTool(),
            FileSearchTool(),
            WriteFileTool(),
            AnsibleWriteTool(),
            CopyFileWithMkdirTool(),
            AnsibleLintTool(),
            # Add checklist tools for LLM to update tasks
            *create_checklist_tools(checklist, checklist_path),
        ]

        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_workflow(self):
        workflow = StateGraph(ChefState)
        workflow.add_node("plan_migration", lambda state: self._plan_migration(state))
        workflow.add_node(
            "execute_migration", lambda state: self._execute_migration(state)
        )
        workflow.add_node(
            "validate_migration", lambda state: self._validate_migration(state)
        )
        workflow.add_node("finalize", lambda state: self._finalize(state))

        workflow.add_edge(START, "plan_migration")
        workflow.add_edge("plan_migration", "execute_migration")
        workflow.add_edge("execute_migration", "validate_migration")
        workflow.add_conditional_edges("validate_migration", self._evaluate_validation)
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _list_all_files(self, directory: str) -> list[str]:
        """List all files recursively in a directory"""
        try:
            path = Path(directory)
            if not path.exists():
                return []

            files = [f for f in path.rglob("*") if f.is_file()]

            # Return relative paths as strings
            return [str(f.relative_to(path)) for f in sorted(files)]
        except Exception as e:
            logger.warning(f"Error listing files in {directory}: {e}")
            return []

    def _plan_migration(self, state: ChefState) -> ChefState:
        """Phase 1: Analyze migration plan and create detailed checklist"""
        logger.info(
            "Planning migration: analyzing migration plan and creating checklist"
        )
        state["current_phase"] = MigrationPhase.PLANNING

        checklist_path = self._get_checklist_path(state["module"])
        checklist_path.parent.mkdir(parents=True, exist_ok=True)

        state["checklist"] = Checklist(state["module"], MigrationCategory)
        state["checklist"].save(checklist_path)
        logger.info(f"Created empty checklist at {checklist_path}")

        # Create planning agent with checklist tools
        planning_agent = self._create_planning_agent(state["checklist"], checklist_path)

        system_message = get_prompt("export_ansible_planning_system")
        user_prompt = get_prompt("export_ansible_planning_task").format(
            module=state["module"],
            module_migration_plan=state["module_migration_plan"].to_document(),
            directory_listing="\n".join(state["directory_listing"]),
            path=state["path"],
        )

        result = planning_agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            get_runnable_config(),
        )

        logger.info(f"Planning agent tools: {report_tool_calls(result).to_string()}")

        # Reload checklist from JSON (LLM populated it via tools)
        if checklist_path.exists():
            state["checklist"] = Checklist.load(checklist_path, MigrationCategory)
            logger.info(f"Loaded checklist with {len(state['checklist'])} items")
        else:
            logger.warning(
                f"Checklist file not found after planning at {checklist_path}"
            )

        return state

    def _execute_migration(self, state: ChefState) -> ChefState:
        """Phase 2: Execute migration tasks from checklist"""
        logger.info(f"Executing migration, attempt {state['export_attempt_counter']}")
        state["current_phase"] = MigrationPhase.EXECUTING

        # Get items that need processing
        items_to_process = [
            item
            for item in state["checklist"].items
            if item.status in PROCESSABLE_STATUSES
        ]

        if not items_to_process:
            logger.info("No items to process in execution phase")
            return state

        checklist_md = state["checklist"].to_markdown()
        ansible_path = self._get_ansible_path(state["module"])

        system_message = get_prompt("export_ansible_execution_system")
        user_prompt = get_prompt("export_ansible_execution_task").format(
            module=state["module"],
            chef_path=state["path"],
            ansible_path=ansible_path,
            migration_plan=state["module_migration_plan"].to_document(),
            checklist=checklist_md,
        )

        result = self.execution_agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            get_runnable_config(),
        )

        logger.info(f"Execution agent tools: {report_tool_calls(result).to_string()}")

        message = get_last_ai_message(result)
        if message:
            state["last_output"] = message.content
            logger.info("Execution phase completed")
        else:
            logger.warning("Execution agent did not produce output")

        state["export_attempt_counter"] += 1
        return state

    def _validate_migration(self, state: ChefState) -> ChefState:
        """Phase 3: Validate migration completeness and correctness"""
        logger.info("Validating migration output")
        state["current_phase"] = MigrationPhase.VALIDATING

        ansible_path = self._get_ansible_path(state["module"])
        checklist_path = self._get_checklist_path(state["module"])

        # Reload checklist from JSON
        if checklist_path.exists():
            logger.info(f"Reloading checklist from {checklist_path}")
            state["checklist"] = Checklist.load(checklist_path, MigrationCategory)
        else:
            logger.warning(f"Checklist file not found at {checklist_path}")

        # Run structural validation
        role_check_tool = AnsibleRoleCheckTool()
        logger.info(f"Running ansible_role_check on {ansible_path}")
        role_check_result = role_check_tool.run(ansible_path)

        # Check for validation failure
        if "Validation failed" in role_check_result or "Error:" in role_check_result:
            logger.error("Role validation failed")
            state["validation_report"] = f"## Validation Failed\n\n{role_check_result}"
            for item in state["checklist"].items:
                if item.status in {ChecklistStatus.PENDING, ChecklistStatus.MISSING}:
                    state["checklist"].update_task(
                        item.source_path,
                        item.target_path,
                        ChecklistStatus.ERROR,
                        "Role validation failed",
                    )
            return state

        logger.info("Role validation passed")

        # Agent-based validation for file existence and content
        chef_files = self._list_all_files(state["path"])
        ansible_files = self._list_all_files(ansible_path)

        chef_files_str = "\n".join(chef_files) if chef_files else "(none)"
        ansible_files_str = "\n".join(ansible_files) if ansible_files else "(none)"
        checklist_md = state["checklist"].to_markdown()

        # Create validation agent
        validation_agent = self._create_validation_agent(
            state["checklist"], checklist_path
        )

        validation_system = get_prompt("export_ansible_validation_system")
        validation_task = get_prompt("export_ansible_validation_task").format(
            module=state["module"],
            chef_path=state["path"],
            ansible_path=ansible_path,
            migration_plan=state["module_migration_plan"].to_document(),
            checklist=checklist_md,
            chef_files=chef_files_str,
            ansible_files=ansible_files_str,
        )

        result = validation_agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": validation_system},
                    {"role": "user", "content": validation_task},
                ]
            },
            get_runnable_config(),
        )

        logger.info(f"Validation agent tools: {report_tool_calls(result).to_string()}")

        # Extract validation report
        message = get_last_ai_message(result)
        state["validation_report"] = (
            message.content if message else "No validation output"
        )
        logger.info("Validation phase completed")

        if checklist_path.exists():
            state["checklist"] = Checklist.load(checklist_path, MigrationCategory)
            logger.info(f"Reloaded checklist: {len(state['checklist'])} items")
        else:
            logger.warning(f"Checklist file not found at {checklist_path}")

        return state

    def _evaluate_validation(
        self, state: ChefState
    ) -> Literal["finalize", "execute_migration"]:
        """Decide whether to finalize or retry execution based on validation"""
        logger.info("Evaluating validation results")

        stats = state["checklist"].get_stats()
        logger.info(f"Checklist stats: {stats}")

        # Check if we're complete or hit max attempts
        if state["checklist"].is_complete():
            logger.info("Migration complete - all items successful")
            return "finalize"

        if state["export_attempt_counter"] >= MAX_EXPORT_ATTEMPTS:
            logger.warning(
                f"Max attempts ({MAX_EXPORT_ATTEMPTS}) reached, finalizing with incomplete items"
            )
            return "finalize"

        incomplete_count = stats["pending"] + stats["missing"] + stats["error"]
        logger.info(f"Retrying execution for {incomplete_count} incomplete items")
        return "execute_migration"

    def _finalize(self, state: ChefState) -> ChefState:
        """Finalize migration and report results"""
        logger.info("Finalizing migration")
        state["current_phase"] = MigrationPhase.COMPLETE

        stats = state["checklist"].get_stats()

        summary_lines = [
            f"Migration Summary for {state['module']}:",
            f"  Total items: {stats['total']}",
            f"  Completed: {stats['complete']}",
            f"  Pending: {stats['pending']}",
            f"  Missing: {stats['missing']}",
            f"  Errors: {stats['error']}",
            f"  Attempts: {state['export_attempt_counter']}",
            "",
            "Final Validation Report:",
            state["validation_report"],
        ]

        state["last_output"] = "\n".join(summary_lines)
        logger.info(
            f"Migration finalized: {stats['complete']}/{stats['total']} completed"
        )

        return state

    def invoke(
        self,
        path: str,
        module: str,
        user_message: str,
        module_migration_plan: DocumentFile,
        high_level_migration_plan: DocumentFile,
        directory_listing: list[str],
    ) -> ChefState:
        """Execute the complete Chef to Ansible migration workflow"""
        logger.info(f"Starting Chef to Ansible migration for module: {module}")

        initial_state = ChefState(
            path=path,
            module=module,
            user_message=user_message,
            module_migration_plan=module_migration_plan,
            high_level_migration_plan=high_level_migration_plan,
            directory_listing=directory_listing,
            checklist=Checklist(module, MigrationCategory),
            current_phase=MigrationPhase.INITIALIZING,
            export_attempt_counter=0,
            validation_report="",
            last_output="",
        )

        result = self._workflow.invoke(
            input=initial_state, config=get_runnable_config()
        )
        return ChefState(**result)
