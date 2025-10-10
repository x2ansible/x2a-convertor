import logging
from typing import Literal, TypedDict

from langchain_community.tools.file_management.write import WriteFileTool
from langgraph.graph import StateGraph, START, END
from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langgraph.prebuilt import create_react_agent

from src.model import get_model, get_last_ai_message
from prompts.get_prompt import get_prompt
from src.utils.config import ANALYZE_RECURSION_LIMIT, MAX_EXPORT_ATTEMPTS

logger = logging.getLogger(__name__)


class ChefState(TypedDict):
    path: str
    module: str
    user_message: str
    module_migration_plan: str
    high_level_migration_plan: str
    directory_listing: str
    validation_status: bool
    export_attempt_counter: int
    last_validation_result: str
    last_output: str


class ChefToAnsibleSubagent:
    """Subagent called by the MigrationAgent to do the actual Chef -> Ansible export"""

    def __init__(self, model=None):
        self.model = model or get_model()
        self.agent = self._create_agent()
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
        ]

        agent = create_react_agent(
            model=self.model,
            tools=tools,
        )
        return agent

    def _create_workflow(self):
        workflow = StateGraph(ChefState)
        workflow.add_node("export", self._export)
        workflow.add_node("validate", self._validate)
        workflow.add_node("finalize", self._finalize)

        workflow.add_edge(START, "export")
        workflow.add_edge("export", "validate")
        workflow.add_conditional_edges("validate", self._evaluate_validation)
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _export(self, state: ChefState):
        logger.info(
            f"ChefToAnsibleSubagent is cooking Ansible, attempt {state['export_attempt_counter']}"
        )

        # This is a naive loop of several attempts
        # TODO: we will experiment wether this re-export from scratch or rather fix-existing approach works better
        # So far we rebuild the context by passing the validation errors in a hope that the next run will do it better.
        # We should evaluate whether better chaining of attempts with explanation of issues to the LLM works better.

        # Another viable approach is in wrapping the linter as a tool and let the LLM drive he process

        export_ansible_previous_attempts_partial = ""
        if state["export_attempt_counter"] > 1:
            export_ansible_previous_attempts_partial = get_prompt(
                "export_ansible_previous_attempts_partial"
            ).format(
                export_attempt_counter=state["export_attempt_counter"],
                previous_issues=state["last_validation_result"],
            )

        system_message = get_prompt("export_ansible_system")
        user_prompt = get_prompt("export_ansible_task").format(
            user_message=state["user_message"],
            path=state["path"],
            module_migration_plan=state["module_migration_plan"],
            high_level_migration_plan=state["high_level_migration_plan"],
            directory_listing=state["directory_listing"],
            previous_attempts=export_ansible_previous_attempts_partial,
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
            logger.info(
                f"LLM call to export Ansible did not produce any output, attempt {state['export_attempt_counter']}"
            )
        else:
            state["last_output"] = message.content

        state["export_attempt_counter"] += 1
        return state

    def _validate(self, state: ChefState):
        logger.info("ChefToAnsibleSubagent is validating the exported Ansible")
        # TODO: call Ansible linter or similar check
        # If failing, store findings in state["last_validation_result"]

        state["last_validation_result"] = ""
        state["validation_status"] = True

        return state

    def _evaluate_validation(self, state: ChefState) -> Literal["finalize", "export"]:
        logger.info("ChefToAnsibleSubagent is evaluating the validation")
        if (
            state["validation_status"]
            or state["export_attempt_counter"] >= MAX_EXPORT_ATTEMPTS
        ):
            return "finalize"

        return "export"

    def _finalize(self, state: ChefState):
        # do clean-up, if needed
        logger.info("ChefToAnsibleSubagent final state")
        return state

    def invoke(
        self,
        path: str,
        module: str,
        user_message: str,
        module_migration_plan: str,
        high_level_migration_plan: str,
        directory_listing: str,
    ) -> str:
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
        )

        result = self._workflow.invoke(
            initial_state, {"recursion_limit": ANALYZE_RECURSION_LIMIT}
        )
        return result


# Notes to try
# - Either
#   - call the linter tool to validate the syntax. If not valid, fix the generated playbook and try again.
#   - or use linter as a tool
# - tune the validate-export loop to fix the issues found in the generated playbook
#
