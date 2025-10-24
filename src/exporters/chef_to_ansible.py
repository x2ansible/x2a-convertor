from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Optional
import os

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.messages.tool import ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent


from src.model import (
    get_model,
    get_last_ai_message,
    report_tool_calls,
    get_runnable_config,
)
from src.types import (
    SUMMARY_SUCCESS_MESSAGE,
    DocumentFile,
    Checklist,
    ChecklistStatus,
)
from src.exporters.types import MigrationCategory
from prompts.get_prompt import get_prompt
from src.utils.config import get_config_int
from tools.ansible_write import AnsibleWriteTool
from tools.ansible_lint import ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE, AnsibleLintTool
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.diff_file import DiffFileTool
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Constants
ANSIBLE_PATH_TEMPLATE = "./ansible/{module}"
CHECKLIST_FILENAME = ".checklist.json"
PROCESSABLE_STATUSES = {
    ChecklistStatus.PENDING,
    ChecklistStatus.MISSING,
    ChecklistStatus.ERROR,
}

ROLE_VALIDATION_SUCCESS_MESSAGE = "Role Validation Passed"


class MigrationPhase(str, Enum):
    """Phases of the migration workflow"""

    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETE = "complete"


class AgentType(str, Enum):
    """Types of agents used in the migration workflow"""

    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"


@dataclass
class ChefState:
    path: str
    module: str
    user_message: str
    module_migration_plan: DocumentFile
    high_level_migration_plan: DocumentFile
    directory_listing: list[str]
    current_phase: str
    export_attempt_counter: int
    validation_report: str
    last_output: str

    def get_ansible_path(self) -> str:
        """Get the Ansible output path for this module"""
        return ANSIBLE_PATH_TEMPLATE.format(module=self.module)

    def get_checklist_path(self) -> Path:
        """Get the path to the checklist JSON file"""
        return Path(self.get_ansible_path()) / CHECKLIST_FILENAME


class ChefToAnsibleSubagent:
    """Subagent called by the MigrationAgent to do the actual Chef -> Ansible export

    Uses a three-agent workflow:
    1. Planning Agent: Analyzes migration plan and creates detailed checklist
    2. Execution Agent: Processes checklist items and generates Ansible artifacts
    3. Validation Agent: Verifies artifacts and updates checklist status
    """

    # Configuration mapping: agent type -> list of tool factory functions
    # This serves as a single source of truth for agent tool configurations
    AGENT_TOOL_CONFIGS = {
        AgentType.PLANNING: [
            lambda: ListDirectoryTool(),
            lambda: ReadFileTool(),
            lambda: FileSearchTool(),
        ],
        AgentType.EXECUTION: [
            lambda: FileSearchTool(),
            lambda: ListDirectoryTool(),
            lambda: ReadFileTool(),
            lambda: WriteFileTool(),
            lambda: CopyFileWithMkdirTool(),
            lambda: AnsibleWriteTool(),
            lambda: AnsibleLintTool(),
            lambda: AnsibleRoleCheckTool(),
        ],
        AgentType.VALIDATION: [
            lambda: ReadFileTool(),
            lambda: DiffFileTool(),
            lambda: ListDirectoryTool(),
            lambda: FileSearchTool(),
            lambda: WriteFileTool(),
            lambda: AnsibleWriteTool(),
            lambda: CopyFileWithMkdirTool(),
            lambda: AnsibleLintTool(),
        ],
    }

    def __init__(self, model=None, module: Optional[str] = None) -> None:
        self.model = model or get_model()
        if module is None:
            raise ValueError("module parameter is required")
        self.module = module
        self.checklist: Checklist = Checklist(module, MigrationCategory)
        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_agent(self, agent_type: AgentType, pre_model_hook=None):
        """Factory method to create an agent with configured tools

        Args:
            agent_type: Type of agent to create (planning, execution, or validation)
            pre_model_hook: Optional hook to run before model invocation

        Returns:
            Configured react agent with appropriate tools
        """
        logger.info(f"Creating migration {agent_type.value} agent")

        # Get base tools for this agent type
        tool_factories = self.AGENT_TOOL_CONFIGS.get(agent_type, [])
        tools = [factory() for factory in tool_factories]

        # All agents get checklist tools
        tools.extend(self.checklist.get_tools())

        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
            pre_model_hook=pre_model_hook,
        )
        return agent

    def _create_planning_agent(self):
        """Create agent for analyzing migration plan and building checklist"""
        return self._create_agent(AgentType.PLANNING)

    def _create_execution_agent(self):
        """Create agent for executing migrations and generating Ansible files"""
        read_file_name = ReadFileTool().name

        def clean_read_file(state):
            messages = state.get("messages", [])
            read_file_msgs = [
                msg
                for msg in messages
                if isinstance(msg, ToolMessage) and msg.name == read_file_name
            ]

            if len(read_file_msgs) <= 3:
                return {"messages": messages}

            # Collect tool_call_ids of the first 2 read_file messages to remove
            call_ids_to_remove = {msg.tool_call_id for msg in read_file_msgs[:2]}

            # Filter messages
            new_messages = []
            for msg in messages:
                # Skip read_file ToolMessages we want to remove
                if (
                    isinstance(msg, ToolMessage)
                    and msg.tool_call_id in call_ids_to_remove
                ):
                    continue

                # For AIMessages with tool_calls, remove the read_file tool_calls
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    msg.tool_calls = [
                        tc
                        for tc in msg.tool_calls
                        if tc.get("id") not in call_ids_to_remove
                    ]

                new_messages.append(msg)

            logger.info(f"Trimmed {len(call_ids_to_remove)} read_file messages")
            return {"messages": new_messages}

        return self._create_agent(AgentType.EXECUTION, pre_model_hook=clean_read_file)

    def _create_validation_agent(self):
        """Create agent for validating migration completeness and correctness"""
        return self._create_agent(AgentType.VALIDATION)

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

    def _load_checklist(self, state: ChefState):
        checklist_path = state.get_checklist_path()
        if checklist_path.exists():
            logger.info(f"Loaded checklist from previous run: {checklist_path}")
            self.checklist = self.checklist.load(checklist_path, MigrationCategory)
            return

        logger.info(f"Created empty checklist at {checklist_path}")
        checklist_path.parent.mkdir(parents=True, exist_ok=True)
        self.checklist.save(checklist_path)

    def _plan_migration(self, state: ChefState) -> ChefState:
        """Phase 1: Analyze migration plan and create detailed checklist"""
        slog = logger.bind(phase="plan_migration")
        slog.info("Planning migration: analyzing migration plan and creating checklist")
        state.current_phase = MigrationPhase.PLANNING
        self._load_checklist(state)

        # Create planning agent with checklist tools
        planning_agent = self._create_planning_agent()

        system_message = get_prompt("export_ansible_planning_system")

        user_prompt = get_prompt("export_ansible_planning_task").format(
            module=state.module,
            module_migration_plan=state.module_migration_plan.to_document(),
            directory_listing="\n".join(state.directory_listing),
            path=state.path,
            existing_checklist=self.checklist.to_markdown(),
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
        slog.info(f"Planning agent tools: {report_tool_calls(result).to_string()}")
        self.checklist.save(state.get_checklist_path())
        slog.info(f"Checklist after planning:\n{self.checklist.to_markdown()}")

        return state

    def _execute_migration(self, state: ChefState) -> ChefState:
        """Phase 2: Execute migration tasks from checklist"""
        slog = logger.bind(
            phase="execute_migration", attempt=state.export_attempt_counter
        )
        slog.info("Executing migration")
        state.current_phase = MigrationPhase.EXECUTING

        slog.debug(f"Checklist before execution:\n{self.checklist.to_markdown()}")

        checklist_path = state.get_checklist_path()

        self.execution_agent = self._create_execution_agent()

        checklist_md = self.checklist.to_markdown()
        ansible_path = state.get_ansible_path()

        validation_report_formatted = ""
        if state.validation_report:
            validation_report_formatted = f"VALIDATION REPORT FROM A PREVIOUS ATTEMPT:\n{state.validation_report}\n"

        system_message = get_prompt("export_ansible_execution_system")
        user_prompt = get_prompt("export_ansible_execution_task").format(
            module=state.module,
            chef_path=state.path,
            ansible_path=ansible_path,
            migration_plan=state.module_migration_plan.to_document(),
            checklist=checklist_md,
            validation_report=validation_report_formatted,
            fragment_yaml_hints=get_prompt("fragment_yaml_hints"),
        )

        result = self.execution_agent.invoke(
            input={
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            config=get_runnable_config(),
        )
        slog.info(f"Execution agent tools: {report_tool_calls(result).to_string()}")
        self.checklist.save(checklist_path)

        slog.info(f"Checklist after execution:\n{self.checklist.to_markdown()}")
        message = get_last_ai_message(result)
        if message:
            state.last_output = message.content
            slog.info("Execution phase completed")
        else:
            slog.warning("Execution agent did not produce output")

        state.export_attempt_counter += 1
        return state

    def _validate_role_check(self, state: ChefState) -> tuple[bool, str]:
        """Structural validation"""
        slog = logger.bind(phase="validate_migration_role_check")
        ansible_path = state.get_ansible_path()
        role_check_tool = AnsibleRoleCheckTool()
        slog.info(f"Running ansible_role_check on {ansible_path}")

        try:
            role_check_result = role_check_tool.run(ansible_path)
        except Exception as e:
            role_check_result = f"Error: {str(e)}"
        slog.debug(f"Role check result: {role_check_result}")

        if "Validation failed" in role_check_result or "Error:" in role_check_result:
            slog.warning(f"Role validation has issues: {role_check_result}")
            return False, role_check_result

        slog.info("Role validation passed")
        return True, ROLE_VALIDATION_SUCCESS_MESSAGE

    def _validate_file_existence(self, state: ChefState) -> bool:
        """Validate that all files in the checklist exist"""
        slog = logger.bind(phase="validate_migration_file_existence")
        slog.info("Validating file existence")

        success = True
        for item in self.checklist.items:
            if not item.target_exists():
                slog.error(
                    f"Checklist target file {item.target_path} does not exist in Ansible output"
                )
                self.checklist.update_task(
                    item.source_path, item.target_path, ChecklistStatus.MISSING
                )
                success = False

        return success

    def _validate_ansible_lint(self, state: ChefState) -> tuple[bool, str]:
        """Run ansible_lint on every MigrationCategory.RECIPES and MigrationCategory.STRUCTURE"""
        slog = logger.bind(phase="validate_migration_ansible_lint")
        slog.info("Validating ansible_lint")

        ansible_path = state.get_ansible_path()
        ansible_lint_tool = AnsibleLintTool()
        result = ansible_lint_tool.run(ansible_path)

        return result == ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE, result

    def _validate_migration(self, state: ChefState) -> ChefState:
        """Phase 3: Validate migration completeness and correctness"""
        slog = logger.bind(
            phase="validate_migration", export_attempt=state.export_attempt_counter
        )
        slog.info("Validating migration output")
        state.current_phase = MigrationPhase.VALIDATING
        state.validation_report = ""

        # Check completeness of existence of all files in checklist
        if not self._validate_file_existence(state):
            slog.error("File existence validation failed")
            self.checklist.save(state.get_checklist_path())
            return state

        # Run ansible_lint on the folder
        [successAnsibleLint, resultAnsibleLint] = self._validate_ansible_lint(state)
        if not successAnsibleLint:
            slog.error("Ansible lint validation failed")
            state.validation_report = (
                f"ERROR:Ansible lint validation failed:\n```{resultAnsibleLint}```"
            )
            return state

        # Run structural validation
        successRoleCheck, resultRoleCheck = self._validate_role_check(state)
        if not successRoleCheck:
            slog.error("Role validation failed")
            state.validation_report = (
                f"ERROR: Ansible role validation failed:\n```{resultRoleCheck}```"
            )
            return state

        # Agent-based validation for additional checks
        # TODO: Does it still bring a value?
        ansible_path = state.get_ansible_path()
        checklist_md = self.checklist.to_markdown()

        # Create validation agent
        validation_agent = self._create_validation_agent()

        validation_system = get_prompt("export_ansible_validation_system")
        validation_task = get_prompt("export_ansible_validation_task").format(
            module=state.module,
            chef_path=state.path,
            ansible_path=ansible_path,
            migration_plan=state.module_migration_plan.to_document(),
            checklist=checklist_md,
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

        slog.info(f"Validation agent tools: {report_tool_calls(result).to_string()}")
        # Extract validation report
        message = get_last_ai_message(result)
        # TODO: Potential infinite loop if the LLM did not change the checklist statuses
        state.validation_report = message.content if message else "No validation output"

        slog.info("Validation phase completed")
        self.checklist.save(state.get_checklist_path())

        return state

    def _evaluate_validation(
        self, state: ChefState
    ) -> Literal["finalize", "execute_migration"]:
        """Decide whether to finalize or retry execution based on validation"""
        slog = logger.bind(phase="evaluate_validation")
        slog.info("Evaluating validation results")

        stats = self.checklist.get_stats()
        slog.info(f"Checklist stats: {stats}")

        # Check if we're complete or hit max attempts
        if (
            self.checklist.is_complete()
            and SUMMARY_SUCCESS_MESSAGE in state.validation_report
        ):
            slog.info("Migration complete - all items successful")
            return "finalize"

        if state.export_attempt_counter >= get_config_int("MAX_EXPORT_ATTEMPTS"):
            slog.error(
                f"Max attempts ({get_config_int('MAX_EXPORT_ATTEMPTS')}) of top-level export loop reached, finalizing with incomplete items."
            )
            return "finalize"

        incomplete_count = stats["pending"] + stats["missing"] + stats["error"]
        slog.info(
            f"Retrying execution for {incomplete_count} incomplete items and validation report: {state.validation_report}"
        )

        return "execute_migration"

    def _finalize(self, state: ChefState) -> ChefState:
        """Finalize migration and report results"""
        slog = logger.bind(phase="finalize")
        slog.info("Finalizing migration")
        state.current_phase = MigrationPhase.COMPLETE

        stats = self.checklist.get_stats()

        summary_lines = [
            f"Migration Summary for {state.module}:",
            f"  Total items: {stats['total']}",
            f"  Completed: {stats['complete']}",
            f"  Pending: {stats['pending']}",
            f"  Missing: {stats['missing']}",
            f"  Errors: {stats['error']}",
            f"  Attempts: {state.export_attempt_counter}",
            "",
            "Final Validation Report:",
            state.validation_report,
            "",
            "Final check list:",
            self.checklist.to_markdown(),
        ]

        state.last_output = "\n".join(summary_lines)
        slog.info(
            f"Migration finalized: {stats['complete']}/{stats['total']} completed"
        )

        return state

    def invoke(
        self,
        path: str,
        user_message: str,
        module_migration_plan: DocumentFile,
        high_level_migration_plan: DocumentFile,
        directory_listing: list[str],
    ) -> ChefState:
        """Execute the complete Chef to Ansible migration workflow"""
        logger.info(f"Starting Chef to Ansible migration for module: {self.module}")

        initial_state = ChefState(
            path=path,
            module=self.module,
            user_message=user_message,
            module_migration_plan=module_migration_plan,
            high_level_migration_plan=high_level_migration_plan,
            directory_listing=directory_listing,
            current_phase=MigrationPhase.INITIALIZING,
            export_attempt_counter=0,
            validation_report="",
            last_output="",
        )

        result = self._workflow.invoke(
            input=initial_state, config=get_runnable_config()
        )
        return ChefState(**result)
