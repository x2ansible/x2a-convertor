import logging
import json
import os
import re

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict
from pathlib import Path

from prompts.get_prompt import get_prompt
from src.const import EXPORT_OUTPUT_FILENAME_TEMPLATE
from src.exporters.chef_to_ansible import ChefToAnsibleSubagent
from src.types import DocumentFile
from src.model import get_model
from src.utils.list_files import list_files
from src.utils.technology import Technology


logger = logging.getLogger(__name__)


class MigrationState(TypedDict):
    user_message: str
    path: str
    module: str
    source_technology: Technology
    high_level_migration_plan: DocumentFile
    module_migration_plan: DocumentFile
    directory_listing: str
    migration_output: str


class MigrationAgent:
    def __init__(self, model=None):
        self.model = model or get_model()
        self._graph = self._build_graph()
        logger.debug("Migration workflow: " + self._graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(MigrationState)

        workflow.add_node("read_source_metadata", self._read_source_metadata)
        workflow.add_node("choose_subagent", self._choose_subagent)
        workflow.add_node("write_migration_output", self._write_migration_output)

        workflow.set_entry_point("read_source_metadata")
        workflow.add_edge("read_source_metadata", "choose_subagent")
        workflow.add_edge("choose_subagent", "write_migration_output")
        workflow.add_edge("write_migration_output", END)

        return workflow.compile()

    def _read_source_metadata(self, state: MigrationState) -> MigrationState:
        """Read the source technology from the migration plan"""
        logger.info("MigrationAgent is reading source metadata")
        prompt = get_prompt("export_source_metadata_system")
        system_message = prompt.format(
            module_migration_plan=state["module_migration_plan"].content,
        )
        user_prompt = get_prompt("export_source_metadata_task").format(
            user_message=state["user_message"],
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
                f"Error during parsing LLM-generated JSON with module metadata: {str(e)}"
            )
            raise

        if isinstance(response_data, dict) and "path" in response_data:
            raw_path = response_data["path"]
        elif (
            isinstance(response_data, list)
            and len(response_data) == 1
            and "path" in response_data[0]
        ):
            raw_path = response_data[0]["path"]
        else:
            raise ValueError(
                f"Unexpected format for LLM response: {response_data}, expected a dictionary with a 'path' key"
            )
        state["path"] = raw_path

        if not state["path"] or not Path(state["path"]).exists():
            raise ValueError(
                f"Module path from the module migration plan not found: {raw_path}"
            )

        # Get the directory listing
        state["directory_listing"] = list_files(path=state["path"])

        logger.info(
            f"Gathered metadata:\n- module path: {state['path']}\n- directory listing: {state['directory_listing']}"
        )

        return state

    def _choose_subagent(self, state: MigrationState) -> MigrationState:
        """Choose and execute the appropriate subagent based on technology"""
        technology = state.get("source_technology")
        logger.info(f"Choosing subagent based on technology: '{technology}'")

        if technology == Technology.CHEF:
            chef_to_ansible_subagent = ChefToAnsibleSubagent(model=self.model)
            result = chef_to_ansible_subagent.invoke(
                path=state["path"],
                module=state["module"],
                user_message=state["user_message"],
                module_migration_plan=state["module_migration_plan"],
                high_level_migration_plan=state["high_level_migration_plan"],
                directory_listing=state["directory_listing"],
            )
            state["migration_output"] = result["last_output"]
        elif technology == Technology.PUPPET:
            logger.warning("Puppet agent not implemented yet")
            state["module_migration_plan"] = "Export from Puppet not available"
        elif technology == Technology.SALT:
            logger.warning("Salt agent not implemented yet")
            state["module_migration_plan"] = "Export from Salt not available"
        else:
            logger.error(f"Unknown source technology: {technology}")
            raise ValueError(f"Unknown source technology: {technology}")

        return state

    def _write_migration_output(self, state: MigrationState) -> MigrationState:
        """Write the migration last message(s) to the output file"""
        filename = EXPORT_OUTPUT_FILENAME_TEMPLATE.format(module=state["module"])
        logger.info(f"Writing migration output to {filename}")

        file = Path(filename)
        # should not be needed but sometimes an unexpected flow occurs
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_text(state["migration_output"])

        return state

    def invoke(self, initial_state: MigrationState) -> MigrationState:
        """Invoke the migration agent"""
        result = self._graph.invoke(initial_state)
        logger.debug(f"Migration agent result: {result}")
        return result


def migrate_module(
    user_requirements,
    source_technology,
    module_migration_plan,
    high_level_migration_plan,
    source_dir,
):
    """Based on the migration plan produced within analysis, this will migrate the project"""
    logger.info(f"Migrating: {source_dir}")
    os.chdir(source_dir)

    # Extract module_name from module_migration_plan, which is in the form "migration-plan-{module_name}.md"
    match = re.match(r".*migration-plan-(.+)\.md", module_migration_plan)
    module_name = match.group(1) if match else None

    if not module_name:
        raise ValueError("module name not found in module_migration_plan filename")

    if not high_level_migration_plan:
        raise ValueError("High level migration plan not found")

    # Load migration plan documents
    high_level_migration_plan_doc = DocumentFile.from_path(high_level_migration_plan)
    module_migration_plan_doc = DocumentFile.from_path(module_migration_plan)

    logger.info(
        f"Module name: {module_name}. Both the high-level and module migration plans have been read."
    )

    technology = Technology(source_technology)
    logger.info(f"Source technology: {technology.value}")

    # Run the migration agent
    workflow = MigrationAgent()
    initial_state = MigrationState(
        user_message=user_requirements,
        path="/",
        source_technology=technology,
        module=module_name,
        high_level_migration_plan=high_level_migration_plan_doc,
        module_migration_plan=module_migration_plan_doc,
        directory_listing="",
    )

    result = workflow.invoke(initial_state)
    logger.info("Migration completed successfully!")
    return result
