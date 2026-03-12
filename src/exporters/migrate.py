import json
import re
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from prompts.get_prompt import get_prompt
from src.const import EXPORT_OUTPUT_FILENAME_TEMPLATE, METADATA_FILENAME
from src.model import get_model, get_runnable_config
from src.types import AnsibleModule, DocumentFile
from src.types.technology import Technology
from src.utils.list_files import list_files
from src.utils.logging import get_logger
from src.utils.technology_registry import TechnologyRegistry

logger = get_logger(__name__)


class SourceMetadata(BaseModel):
    """Structured output for source metadata"""

    path: str


class MigrationState(TypedDict):
    user_message: str
    path: str
    module: AnsibleModule
    source_technology: Technology
    high_level_migration_plan: DocumentFile
    module_migration_plan: DocumentFile
    directory_listing: list[str]
    migration_output: str
    failed: bool
    failure_reason: str


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

        # Try reading path from generated-project-metadata.json first
        raw_path = self._read_path_from_metadata(state["module"])

        # Fall back to LLM extraction if metadata file doesn't have the path
        if not raw_path:
            raw_path = self._extract_path_via_llm(state)

        if not raw_path or not Path(raw_path).exists():
            raise ValueError(
                f"Module path from the module migration plan not found: {raw_path}"
            )

        state["path"] = raw_path
        state["directory_listing"] = list_files(path=state["path"])

        logger.info(
            f"Gathered metadata:\n- module path: {state['path']}\n- directory listing: {state['directory_listing']}"
        )

        return state

    def _read_path_from_metadata(self, module: AnsibleModule) -> str | None:
        """Try to read module path from generated-project-metadata.json."""
        metadata_path = Path(METADATA_FILENAME)
        if not metadata_path.exists():
            return None
        try:
            metadata_list = json.loads(metadata_path.read_text())
            for entry in metadata_list:
                if entry.get("name") == str(module):
                    path = entry.get("path", "")
                    if not path:
                        continue
                    # Normalize LLM-generated root directory descriptions to "."
                    if not Path(path).exists() and "root" in path.lower():
                        path = "."
                    if Path(path).exists():
                        logger.info(f"Read module path '{path}' from {METADATA_FILENAME}")
                        return path
        except Exception as e:
            logger.warning(f"Failed to read {METADATA_FILENAME}: {e}")
        return None

    def _extract_path_via_llm(self, state: MigrationState) -> str | None:
        """Fall back to LLM extraction of path from migration plan."""
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
        return response.path

    def _choose_subagent(self, state: MigrationState) -> MigrationState:
        """Choose and execute the appropriate subagent based on technology."""
        technology = state.get("source_technology")
        logger.info(f"Choosing subagent based on technology: '{technology}'")

        try:
            exporter = TechnologyRegistry.get_exporter(
                technology, model=self.model, module=state["module"]
            )
        except ValueError:
            logger.error(f"No exporter registered for technology: {technology}")
            state["failed"] = True
            state["failure_reason"] = (
                f"{technology.value} migration not implemented yet"
            )
            return state

        result = exporter.invoke(
            path=state["path"],
            user_message=state["user_message"],
            module_migration_plan=state["module_migration_plan"],
            high_level_migration_plan=state["high_level_migration_plan"],
            directory_listing=state["directory_listing"],
        )
        state["migration_output"] = result.get_output()
        state["failed"] = result.did_fail()
        state["failure_reason"] = result.get_failure_reason()

        return state

    def _write_migration_output(self, state: MigrationState) -> MigrationState:
        """Write the migration last message(s) to the output file"""
        filename = EXPORT_OUTPUT_FILENAME_TEMPLATE.format(module=str(state["module"]))
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
    raw_module_name = match.group(1) if match else None

    if not raw_module_name:
        raise ValueError("module name not found in module_migration_plan filename")

    # Create AnsibleModule value object (automatically sanitizes)
    module_name = AnsibleModule(raw_module_name)

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
        failed=False,
        failure_reason="",
    )

    result = workflow.invoke(initial_state)

    if result["failed"]:
        logger.error(
            f"Migration failed for module {module_name}: {result['failure_reason']}"
        )
    else:
        logger.info(f"Migration completed successfully for module {module_name}!")

    return MigrationState(**result)
