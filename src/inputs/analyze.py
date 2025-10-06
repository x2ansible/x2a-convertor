import logging
import json
import os

from enum import Enum
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from pathlib import Path
from typing import TypedDict

from prompts.get_prompt import get_prompt
from src.const import MIGRATION_PLAN_FILE, COMPONENT_MIGRATION_PLAN_TEMPLATE
from src.inputs.chef import ChefSubagent
from src.model import get_model

logger = logging.getLogger(__name__)


class Technology(Enum):
    CHEF = "Chef"
    PUPPET = "Puppet"
    SALT = "Salt"


class MigrationState(TypedDict):
    user_message: str
    path: str
    technology: Technology
    migration_plan_content: str
    component_migration_plan: str
    component_plan_path: str


class MigrationAnalysisWorkflow:
    def __init__(self, model=None):
        self.model = model or get_model()
        self.chef_subagent = ChefSubagent(model=self.model)
        self.graph = self._build_graph()
        logger.debug(self.graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(MigrationState)

        workflow.add_node("read_migration_plan", self.read_migration_plan)
        workflow.add_node("select_component", self.select_component)
        workflow.add_node("choose_subagent", self.choose_subagent)
        workflow.add_node("write_migration_file", self.write_migration_file)

        workflow.set_entry_point("read_migration_plan")
        workflow.add_edge("read_migration_plan", "select_component")
        workflow.add_edge("select_component", "choose_subagent")
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

    def select_component(self, state: MigrationState) -> MigrationState:
        """Select component to migrate based on user input and LLM analysis"""

        # Get user requirements and migration plan content
        user_message = state.get("user_message")
        migration_plan_content = state.get("migration_plan_content", "")

        # Prepare system message with migration plan context
        system_message = get_prompt("analyze_select_component_system").format(
            migration_plan_content=migration_plan_content
        )

        user_prompt = get_prompt("analyze_select_component_task").format(
            user_message=user_message
        )

        # Call LLM to get suggestions
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

        llm_response = self.model.invoke(messages)
        logger.debug(f"LLM Response: {llm_response.content}")

        response_data = json.loads(llm_response.content.strip())
        raw_path = response_data.get("path", "")

        # Convert absolute paths to relative
        if raw_path.startswith("/"):
            raw_path = f".{raw_path}"

        state["path"] = raw_path
        state["technology"] = Technology(response_data.get("technology", "Chef"))
        logger.info(
            f"Selected path: '{state['path']}' technology: '{state['technology'].value}'"
        )

        return state

    def choose_subagent(self, state: MigrationState) -> MigrationState:
        """Choose and execute the appropriate subagent based on technology"""
        technology = state.get("technology")

        if technology == Technology.CHEF:
            state["component_migration_plan"] = self.chef_subagent.invoke(
                state["path"], state["user_message"]
            )
        elif technology == Technology.PUPPET:
            logger.warning("Puppet agent not implemented yet")
            state["component_migration_plan"] = "Puppet analysis not available"
        elif technology == Technology.SALT:
            logger.warning("Salt agent not implemented yet")
            state["component_migration_plan"] = "Salt analysis not available"
        else:
            logger.error("Technology not set correctly")
            state["component_migration_plan"] = "Technology analysis failed"

        return state

    def write_migration_file(self, state: MigrationState) -> MigrationState:
        """Write the migration plan to a file"""
        migration_content = state.get("component_migration_plan")
        if not migration_content:
            logger.error("Migration failed, no plan")
            return state

        path = state.get("path", "")
        component = path.split("/")[-1] if path else "unknown"
        filename = COMPONENT_MIGRATION_PLAN_TEMPLATE.format(component=component)

        Path(filename).write_text(migration_content)
        logger.info(f"Migration plan written to {filename}")
        state["component_plan_path"] = filename

        return state


def analyze_project(user_requirements: str, source_dir: str = "."):
    """Create dependency graph and granular migration tasks"""
    logger.info("Starting migration analysis workflow...")
    os.chdir(source_dir)

    workflow = MigrationAnalysisWorkflow()
    initial_state = MigrationState(
        user_message=user_requirements,
        path="/",
        technology=None,
        migration_plan_content="",
        component_migration_plan="",
        component_plan_path="",
    )

    result = workflow.graph.invoke(initial_state)
    logger.info("Migration analysis completed successfully!")
    return result
