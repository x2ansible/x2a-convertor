import logging
import re

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from typing import TypedDict
from pathlib import Path
from pydantic import BaseModel

from prompts.get_prompt import get_prompt
from src.const import EXPORT_OUTPUT_FILENAME_TEMPLATE
from src.exporters.chef_to_ansible import ChefToAnsibleSubagent
from src.types import DocumentFile
from src.model import get_model, get_runnable_config
from src.utils.list_files import list_files
from src.utils.technology import Technology


logger = logging.getLogger(__name__)


class SourceMetadata(BaseModel):
    """Structured output for source metadata"""

    path: str


class MigrationState(TypedDict):
    user_message: str
    path: str
    module: str
    source_technology: Technology
    high_level_migration_plan: DocumentFile
    module_migration_plan: DocumentFile
    directory_listing: list[str]
    migration_output: str


class MigrationAgent:
    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self._graph = self._build_graph()
        logger.debug("Migration workflow: " + self._graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(MigrationState)

        workflow.add_node(
            "read_source_metadata", lambda state: self._read_source_metadata(state)
        )
        workflow.add_node("choose_subagent", lambda state: self._choose_subagent(state))
        workflow.add_node(
            "write_migration_output", lambda state: self._write_migration_output(state)
        )

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

        structured_llm = self.model.with_structured_output(SourceMetadata)
        response = structured_llm.invoke(messages, config=get_runnable_config())
        logger.debug(f"LLM read_source_metadata response: {response}")

        assert isinstance(response, SourceMetadata)
        raw_path = response.path

        if not raw_path or not Path(raw_path).exists():
            raise ValueError(
                f"Module path from the module migration plan not found: {raw_path}"
            )

        state["path"] = raw_path

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
            chef_to_ansible_subagent = ChefToAnsibleSubagent(
                model=self.model, module=state["module"]
            )
            result = chef_to_ansible_subagent.invoke(
                path=state["path"],
                user_message=state["user_message"],
                module_migration_plan=state["module_migration_plan"],
                high_level_migration_plan=state["high_level_migration_plan"],
                directory_listing=state["directory_listing"],
            )
            state["migration_output"] = result.last_output
        elif technology == Technology.PUPPET:
            logger.warning("Puppet agent not implemented yet")
            state["module_migration_plan"] = DocumentFile(
                path=Path("not_available.txt"),
                content="Export from Puppet not available",
            )
        elif technology == Technology.SALT:
            logger.warning("Salt agent not implemented yet")
            state["module_migration_plan"] = DocumentFile(
                path=Path("not_available.txt"), content="Export from Salt not available"
            )
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
        result = self._graph.invoke(input=initial_state, config=get_runnable_config())
        logger.debug(f"Migration agent result: {result}")
        return MigrationState(**result)


def migrate_module(
    user_requirements,
    source_technology,
    module_migration_plan,
    high_level_migration_plan,
    source_dir,
    # pyrefly: ignore
) -> MigrationState:
    """Based on the migration plan produced within analysis, this will migrate the project"""
    logger.info(f"Migrating: {source_dir}")

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
        directory_listing=[],
        migration_output="",
    )

    result = workflow.invoke(initial_state)
    logger.info("Migration completed successfully!")
    return MigrationState(**result)
