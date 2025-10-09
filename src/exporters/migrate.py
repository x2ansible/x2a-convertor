import logging
import json
import os

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict
from pathlib import Path

from prompts.get_prompt import get_prompt
from src.const import MIGRATION_PLAN_FILE, MIGRATION_REPORT_FILE
from src.exporters.chef_to_ansible import ChefToAnsibleSubagent
from src.model import get_model
from src.utils.list_files import list_files
from src.utils.technology import Technology


logger = logging.getLogger(__name__)


class MigrationState(TypedDict):
    user_message: str
    path: str
    component: str
    source_technology: Technology
    migration_plan_content: str
    component_migration_plan_content: str
    directory_listing: str


class MigrationAgent:
    def __init__(self, model=None):
        self.model = model or get_model()
        self._graph = self._build_graph()
        logger.debug("Migration workflow: " + self._graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(MigrationState)

        workflow.add_node("read_migration_plan", self._read_migration_plan)
        workflow.add_node(
            "read_component_migration_plan", self._read_component_migration_plan
        )
        workflow.add_node("read_source_metadata", self._read_source_metadata)
        workflow.add_node("choose_subagent", self._choose_subagent)
        workflow.add_node("write_migration_report", self._write_migration_report)

        workflow.set_entry_point("read_migration_plan")
        workflow.add_edge("read_migration_plan", "read_component_migration_plan")
        workflow.add_edge("read_component_migration_plan", "read_source_metadata")
        workflow.add_edge("read_source_metadata", "choose_subagent")
        workflow.add_edge("choose_subagent", "write_migration_report")
        workflow.add_edge("write_migration_report", END)

        return workflow.compile()

    def _read_migration_plan(self, state: MigrationState) -> MigrationState:
        """Read the migration_plan.md file"""
        migration_plan_path = Path(MIGRATION_PLAN_FILE)

        if not migration_plan_path.exists():
            state["migration_plan_content"] = (
                "# Migration Plan\n\nNo existing migration plan found."
            )
            logger.warning("No existing migration plan found, starting fresh.")
            return state

        logger.info(f"Reading migration plan from {migration_plan_path}")
        state["migration_plan_content"] = migration_plan_path.read_text()
        return state

    def _read_component_migration_plan(self, state: MigrationState) -> MigrationState:
        """Read the migration-plan-[COMPONENT].md file"""
        component_migration_plan_path = Path(MIGRATION_PLAN_FILE)
        if not component_migration_plan_path.exists():
            state["component_migration_plan_content"] = (
                "# Migration Plan\n\nNo existing component migration plan found."
            )
            raise ValueError(
                "No existing component migration plan found, run analysis first."
            )

        logger.info(
            f"Reading component migration plan from {component_migration_plan_path}"
        )
        state["component_migration_plan_content"] = (
            component_migration_plan_path.read_text()
        )
        return state

    def _read_source_metadata(self, state: MigrationState) -> MigrationState:
        """Read the source technology from the migration plan"""
        user_message = state.get("user_message")
        component_migration_plan_content = state.get(
            "component_migration_plan_content", ""
        )

        logger.debug(
            f"Component migration plan content: {component_migration_plan_content}"
        )
        prompt = get_prompt("export_source_metadata_system")
        logger.debug(f"Raw prompt: {prompt}")
        system_message = prompt.format(
            component_migration_plan=component_migration_plan_content
        )
        user_prompt = get_prompt("export_source_metadata_task").format(
            user_message=user_message,
        )

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ]

        llm_response = self.model.invoke(messages)
        logger.debug(f"LLM read_source_metadata response: {llm_response.content}")

        try:
            response_data = json.loads(llm_response.content.strip())
        except Exception as e:
            logger.error(
                f"Error during parsing LLM-generated JSON with component metadata: {str(e)}"
            )
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
                f"Unexpected format for LLM response: {response_data}, expected a dictionary with a 'path' key"
            )
        state["path"] = raw_path
        state["source_technology"] = Technology(raw_technology)
        logger.info(
            f"Selected path: '{state['path']}', source technology: '{state['source_technology'].value}'"
        )

        state["directory_listing"] = list_files(path=state["path"])
        return state

    # TODO: once we get source technology and component on the command input, we can remove following
    def _choose_subagent(self, state: MigrationState) -> MigrationState:
        """Choose and execute the appropriate subagent based on technology"""
        technology = state.get("source_technology")

        if technology == Technology.CHEF:
            chef_to_ansible_subagent = ChefToAnsibleSubagent(model=self.model)
            state["migration_report"] = chef_to_ansible_subagent.invoke(
                path=state["path"],
                component=state["component"],
                user_message=state["user_message"],
                component_migration_plan=state["component_migration_plan_content"],
                high_level_migration_plan=state["component_migration_plan_content"],
                directory_listing=state["directory_listing"],
            )
        elif technology == Technology.PUPPET:
            logger.warning("Puppet agent not implemented yet")
            state["component_migration_plan"] = "Export from Puppet not available"
        elif technology == Technology.SALT:
            logger.warning("Salt agent not implemented yet")
            state["component_migration_plan"] = "Export from Salt not available"
        else:
            logger.error("Technology not set correctly")
            state["component_migration_plan"] = (
                "Can not get info about source technology."
            )

        return state

    def _write_migration_report(self, state: MigrationState) -> MigrationState:
        """Write the migration report"""
        logger.info(f"Writing migration report to {MIGRATION_REPORT_FILE}")
        # TODO: implement
        return state

    def invoke(self, initial_state: MigrationState) -> MigrationState:
        """Invoke the migration agent"""
        result = self._graph.invoke(initial_state)
        logger.debug(f"Migration agent result: {result}")
        return result


def migrate_component(user_requirements, component_name, source_dir):
    """Based on the migration plan produced within analysis, this will migrate the project"""
    logger.info(f"Migrating: {source_dir}")
    os.chdir(source_dir)

    workflow = MigrationAgent()
    initial_state = MigrationState(
        user_message=user_requirements,
        path="/",
        source_technology=None,
        component=component_name,
        migration_plan_content="",
        component_migration_plan_content="",
        directory_listing="",
    )

    result = workflow.invoke(initial_state)
    logger.info("Migration completed successfully!")
    return result
