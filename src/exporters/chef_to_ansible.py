import logging

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_community.tools.file_management.write import WriteFileTool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import create_react_agent
from typing import Literal, TypedDict

from src.model import (
    get_model,
    get_last_ai_message,
    report_tool_calls,
    get_runnable_config,
)
from src.types import DocumentFile
from prompts.get_prompt import get_prompt
from src.utils.config import MAX_EXPORT_ATTEMPTS
from tools.ansible import AnsibleWriteTool
from tools.ansible_lint import AnsibleLintTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.diff_file import DiffFileTool

logger = logging.getLogger(__name__)


class ChefState(TypedDict):
    path: str
    module: str
    user_message: str
    module_migration_plan: DocumentFile
    high_level_migration_plan: DocumentFile
    directory_listing: list[str]
    validation_status: bool
    export_attempt_counter: int
    last_validation_result: str
    last_output: str


class ChefToAnsibleSubagent:
    """Subagent called by the MigrationAgent to do the actual Chef -> Ansible export"""

    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self.agent = self._create_agent()
        self.validation_agent = self._create_validation_agent()
        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_agent(self):
        """Create an agent with file management tools for migration"""
        logger.info("Creating chef to ansible export agent")

        tools = [
            FileSearchTool(),
            ListDirectoryTool(),
            ReadFileTool(),
            WriteFileTool(),
            CopyFileWithMkdirTool(),
            AnsibleWriteTool(),
            AnsibleLintTool(),
        ]

        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_validation_agent(self):
        """Create an agent with file tools for validation"""
        logger.info("Creating chef to ansible validation agent")

        tools = [
            ReadFileTool(),
            DiffFileTool(),
            ListDirectoryTool(),
            FileSearchTool(),
            WriteFileTool(),
            AnsibleWriteTool(),
            CopyFileWithMkdirTool(),
            AnsibleLintTool(),
        ]

        # pyrefly: ignore
        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_workflow(self):
        workflow = StateGraph(ChefState)
        # pyrefly: ignore
        workflow.add_node("export", self._export)
        # pyrefly: ignore
        workflow.add_node("validate", self._validate)
        # pyrefly: ignore
        workflow.add_node("finalize", self._finalize)

        workflow.add_edge(START, "export")
        workflow.add_edge("export", "validate")
        workflow.add_conditional_edges("validate", self._evaluate_validation)
        workflow.add_edge("finalize", END)

        return workflow.compile()

    # pyrefly: ignore
    def _export(self, state: ChefState) -> TypedDict[ChefState]:
        logger.info(
            f"ChefToAnsibleSubagent is cooking Ansible, attempt {state['export_attempt_counter']}"
        )

        # This is a naive loop of several attempts
        # TODO: we will experiment wether this re-export from scratch or rather fix-existing approach works better
        # So far we rebuild the context by passing the validation errors in a hope that the next run will do it better.
        # We should evaluate whether better chaining of attempts with explanation of issues to the LLM works better.

        # Another viable approach is in wrapping the linter as a tool and let the LLM drive he process

        export_ansible_previous_attempts_partial = ""
        # TODO: if we will implement fix-existing approach, we will retrigger the export (validation/linter not yet implemented)
        if state["export_attempt_counter"] > 1:
            export_ansible_previous_attempts_partial = get_prompt(
                "export_ansible_previous_attempts_partial"
            ).format(
                export_attempt_counter=state["export_attempt_counter"],
                previous_issues=state["last_validation_result"],
            )

        system_message = get_prompt("export_ansible_system").format(
            module=state["module"],
        )
        user_prompt = get_prompt("export_ansible_task").format(
            user_message=state["user_message"],
            directory_listing="\n".join(state["directory_listing"]),
            path=state["path"],
            module_migration_plan=state["module_migration_plan"].to_document(),
            high_level_migration_plan=state["high_level_migration_plan"].to_document(),
            previous_attempts=export_ansible_previous_attempts_partial,
        )

        # Execute validation agent
        result = self.agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_prompt},
                ]
            },
            get_runnable_config(),
        )
        logger.info(
            f"Export got this tools calls: {report_tool_calls(result).to_string()}"
        )
        message = get_last_ai_message(result)
        if not message:
            logger.info(
                f"LLM call to export Ansible did not produce any output, attempt {state['export_attempt_counter']}"
            )
        else:
            state["last_output"] = message.content

        state["export_attempt_counter"] += 1
        return state

    def _list_all_files(self, directory: str) -> list:
        """List all files recursively in a directory"""
        from pathlib import Path

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

    # pyrefly: ignore
    def _validate(self, state: ChefState) -> TypedDict[ChefState]:
        """Validation using react-agent to compare Chef vs Ansible"""
        logger.info("ChefToAnsibleSubagent is validating the exported Ansible")

        # Pre-list ALL Chef source files
        chef_path = state["path"]
        chef_files = self._list_all_files(chef_path)

        # Pre-list ALL Ansible output files
        ansible_path = f"./ansible/{state['module']}"
        ansible_files = self._list_all_files(ansible_path)

        # Format listings for prompt
        chef_files_str = "\n".join(chef_files) if chef_files else "(none)"
        ansible_files_str = "\n".join(ansible_files) if ansible_files else "(none)"

        validation_system = get_prompt("export_ansible_validate_system")
        validation_task = get_prompt("export_ansible_validate_task").format(
            module=state["module"],
            chef_path=state["path"],
            ansible_path=ansible_path,
            migration_plan_content=state["module_migration_plan"].to_document(),
            chef_files=chef_files_str,
            ansible_files=ansible_files_str,
        )

        # Give validation agent more iterations since it needs to check many files
        result = self.validation_agent.invoke(
            {
                "messages": [
                    {"role": "system", "content": validation_system},
                    {"role": "user", "content": validation_task},
                ]
            },
            get_runnable_config(),
        )

        logger.info(
            f"Validation agent completed: {report_tool_calls(result).to_string()}"
        )

        # Extract validation report
        message = get_last_ai_message(result)
        validation_report = message.content if message else "No validation output"
        logger.info(validation_report)
        # Parse report for COMPLETE/INCOMPLETE status
        if "STATUS: INCOMPLETE" in validation_report or "MISSING:" in validation_report:
            state["validation_status"] = False
            state["last_validation_result"] = validation_report
        else:
            state["validation_status"] = True
            state["last_validation_result"] = validation_report

        return state

    def _evaluate_validation(self, state: ChefState) -> Literal["finalize", "export"]:
        logger.info("ChefToAnsibleSubagent is evaluating the validation")
        if (
            state["validation_status"]
            or state["export_attempt_counter"] >= MAX_EXPORT_ATTEMPTS
        ):
            return "finalize"

        return "export"

    # pyrefly: ignore
    def _finalize(self, state: ChefState) -> TypedDict[ChefState]:
        # do clean-up, if needed
        logger.info("ChefToAnsibleSubagent final state")
        print(f"{state['last_validation_result']}")
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
        """Export Ansible playbook based on the module migration plan and Chef sources"""
        logger.info("Using ChefToAnsible agent for migration")

        initial_state = ChefState(
            path=path,
            module=module,
            user_message=user_message,
            module_migration_plan=module_migration_plan,
            high_level_migration_plan=high_level_migration_plan,
            directory_listing=directory_listing,
            export_attempt_counter=1,
            validation_status=False,
            last_validation_result="",
            last_output="",
        )

        result = self._workflow.invoke(initial_state, get_runnable_config())
        # pyrefly: ignore
        return result


# Notes to try
# - Either
#   - call the linter tool to validate the syntax. If not valid, fix the generated playbook and try again.
#   - or use linter as a tool
# - tune the validate-export loop to fix the issues found in the generated playbook
#
