import structlog
import json

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from pathlib import Path
from typing import TypedDict

from prompts.get_prompt import get_prompt
from src.const import MIGRATION_PLAN_FILE, MODULE_MIGRATION_PLAN_TEMPLATE
from src.inputs.chef import ChefSubagent
from src.model import get_model, get_runnable_config
from src.utils.technology import Technology

logger = structlog.get_logger(__name__)


class MigrationState(TypedDict):
    user_message: str
    path: str
    technology: Technology | None
    migration_plan_content: str
    module_migration_plan: str
    module_plan_path: str


class MigrationAnalysisWorkflow:
    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self.chef_subagent = ChefSubagent(model=self.model)
        self.graph = self._build_graph()
        logger.debug(self.graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(MigrationState)

        workflow.add_node(
            "read_migration_plan", lambda state: self.read_migration_plan(state)
        )
        workflow.add_node("select_module", lambda state: self.select_module(state))
        workflow.add_node("choose_subagent", lambda state: self.choose_subagent(state))
        workflow.add_node(
            "write_migration_file", lambda state: self.write_migration_file(state)
        )

        workflow.set_entry_point("read_migration_plan")
        workflow.add_edge("read_migration_plan", "select_module")
        workflow.add_edge("select_module", "choose_subagent")
        workflow.add_edge("choose_subagent", "write_migration_file")
        workflow.add_edge("write_migration_file", END)

        return workflow.compile()

    def read_migration_plan(self, state: MigrationState) -> MigrationState:
        """Read the migration_plan.md file"""
        migration_plan_path = Path(MIGRATION_PLAN_FILE)

        if not migration_plan_path.exists():
            state["migration_plan_content"] = (
                "# Migration Plan\n\nNo existing migration plan found."
            )
            logger.warning("No existing migration plan found, starting fresh")
            return state

        state["migration_plan_content"] = migration_plan_path.read_text()
        logger.info(f"Read migration plan from {migration_plan_path}")
        return state

    def select_module(self, state: MigrationState) -> MigrationState:
        """Select module to migrate based on user input and LLM analysis"""

        # Get user requirements and migration plan content
        user_message = state.get("user_message")
        migration_plan_content = state.get("migration_plan_content", "")

        # Prepare system message with migration plan context
        system_message = get_prompt("analyze_select_module_system").format(
            migration_plan_content=migration_plan_content
        )

        user_prompt = get_prompt("analyze_select_module_task").format(
            user_message=user_message
        )

        # Call LLM to get suggestions
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

        llm_response = self.model.invoke(messages, config=get_runnable_config())
        logger.debug(f"LLM select_module response: {llm_response.content}")

        try:
            content = llm_response.content
            if isinstance(content, list) and content:
                first_item = content[0]
                content = (
                    first_item.get("text", "")
                    if isinstance(first_item, dict)
                    else str(first_item)
                )
            response_data = json.loads(str(content).strip())
        except Exception as e:
            logger.error(
                f"Error during parsing LLM-generated JSON with list of modules: {str(e)}"
            )
            # TODO: if this is an issue among several attempts, we should retry the LLM call
            raise

        if isinstance(response_data, dict) and "path" in response_data:
            raw_path = response_data["path"]
            raw_technology = response_data.get("technology", "Chef")
        elif (
            isinstance(response_data, list)
            and len(response_data) == 1
            and "path" in response_data[0]
        ):
            raw_path = response_data[0]["path"]
            raw_technology = response_data[0].get("technology", "Chef")
        else:
            raise ValueError(
                f"Unexpected format for LLM response, expected a dictionary with a 'path' key but got: {response_data}"
            )

        # Convert absolute paths to relative
        if raw_path.startswith("/"):
            raw_path = f".{raw_path}"

        # remove trailing slash if present
        if raw_path.endswith("/") and len(raw_path) > 1:
            raw_path = raw_path.rstrip("/")

        state["path"] = raw_path
        state["technology"] = Technology(raw_technology)
        logger.info(
            f"Selected path: '{state['path']}' technology: '{state['technology'].value}'"
        )

        return state

    def choose_subagent(self, state: MigrationState) -> MigrationState:
        """Choose and execute the appropriate subagent based on technology"""
        technology = state.get("technology")

        if technology == Technology.CHEF:
            state["module_migration_plan"] = self.chef_subagent.invoke(
                state["path"], state["user_message"]
            )
        elif technology == Technology.PUPPET:
            logger.warning("Puppet agent not implemented yet")
            state["module_migration_plan"] = "Puppet analysis not available"
        elif technology == Technology.SALT:
            logger.warning("Salt agent not implemented yet")
            state["module_migration_plan"] = "Salt analysis not available"
        else:
            logger.error("Technology not set correctly")
            state["module_migration_plan"] = "Technology analysis failed"

        return state

    def write_migration_file(self, state: MigrationState) -> MigrationState:
        """Write the migration plan to a file"""
        migration_content = state.get("module_migration_plan")
        if not migration_content:
            logger.error("Migration failed, no plan generated")
            return state

        path = state.get("path", "")
        module = path.split("/")[-1] if path else "unknown"

        filename = MODULE_MIGRATION_PLAN_TEMPLATE.format(module=module)

        Path(filename).write_text(migration_content)
        logger.info(f"Migration plan written to {filename}")
        state["module_plan_path"] = filename

        return state


def analyze_project(user_requirements: str, source_dir: str = "."):
    """Create dependency graph and granular migration tasks"""
    logger.info("Starting migration analysis workflow...")

    workflow = MigrationAnalysisWorkflow()
    initial_state = MigrationState(
        user_message=user_requirements,
        path="/",
        technology=None,
        migration_plan_content="",
        module_migration_plan="",
        module_plan_path="",
    )

    result = workflow.graph.invoke(initial_state, config=get_runnable_config())
    logger.info("Chef to Ansible migration analysis completed successfully!")
    return result
