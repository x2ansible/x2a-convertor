import re
from pathlib import Path
from typing import Literal

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.const import EXPORT_OUTPUT_FILENAME_TEMPLATE
from src.exporters.module_selection_agent import ModuleSelectionAgent
from src.exporters.state import ExportState
from src.model import get_model, get_runnable_config
from src.types import AnsibleModule, DocumentFile
from src.types.technology import Technology
from src.utils.logging import get_logger
from src.utils.technology_registry import TechnologyRegistry

logger = get_logger(__name__)


class MigrationAgent:
    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self.module_selection_agent = ModuleSelectionAgent(model=self.model)
        self._graph = self._build_graph()
        logger.debug("Migration workflow: " + self._graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(ExportState)

        workflow.add_node("select_module", self.module_selection_agent)
        workflow.add_node("choose_subagent", lambda state: self._choose_subagent(state))
        workflow.add_node(
            "write_migration_output", lambda state: self._write_migration_output(state)
        )

        workflow.set_entry_point("select_module")
        workflow.add_conditional_edges(
            "select_module",
            self._check_failure,
            {"continue": "choose_subagent", "failed": "write_migration_output"},
        )
        workflow.add_conditional_edges(
            "choose_subagent",
            self._check_failure,
            {"continue": "write_migration_output", "failed": "write_migration_output"},
        )
        workflow.add_edge("write_migration_output", END)

        return workflow.compile()

    def _check_failure(self, state: ExportState) -> Literal["continue", "failed"]:
        """Check if the state is marked as failed.

        Args:
            state: Current export state

        Returns:
            "failed" if state is marked as failed, "continue" otherwise
        """
        if state.failed:
            logger.error(f"Migration failed: {state.failure_reason}")
            return "failed"
        return "continue"

    def _choose_subagent(self, state: ExportState) -> ExportState:
        """Choose and execute the appropriate subagent based on technology."""
        technology = state.source_technology
        logger.info(f"Choosing subagent based on technology: '{technology}'")

        try:
            exporter = TechnologyRegistry.get_exporter(
                technology, model=self.model, module=state.module
            )
        except ValueError:
            error_msg = f"{technology.value} migration not implemented yet"
            logger.error(f"No exporter registered for technology: {technology}")
            return state.mark_failed(error_msg).update(last_output=error_msg)

        result = exporter.invoke(
            path=state.path,
            user_message=state.user_message,
            module_migration_plan=state.module_migration_plan,
            high_level_migration_plan=state.high_level_migration_plan,
            directory_listing=state.directory_listing,
            source_technology=technology,
        )

        return state.update(
            last_output=result.get_output(),
            failed=result.did_fail(),
            failure_reason=result.get_failure_reason(),
        )

    def _write_migration_output(self, state: ExportState) -> ExportState:
        """Write the migration last message(s) to the output file"""
        filename = EXPORT_OUTPUT_FILENAME_TEMPLATE.format(module=str(state.module))
        logger.info(f"Writing migration output to {filename}")

        file = Path(filename)
        file.parent.mkdir(exist_ok=True, parents=True)
        file.write_text(state.last_output)

        return state

    def invoke(self, initial_state: ExportState) -> ExportState:
        """Invoke the migration agent"""
        result = self._graph.invoke(input=initial_state, config=get_runnable_config())
        logger.debug(f"Migration agent result: {result}")
        return ExportState(**result)


def migrate_module(
    user_requirements,
    source_technology,
    module_migration_plan,
    high_level_migration_plan,
    source_dir,
) -> ExportState:
    """Based on the migration plan produced within analysis, this will migrate the project"""
    logger.info(f"Migrating: {source_dir}")

    # Extract module_name from module_migration_plan
    match = re.match(r".*migration-plan-(.+)\.md", module_migration_plan)
    raw_module_name = match.group(1) if match else None

    if not raw_module_name:
        raise ValueError("module name not found in module_migration_plan filename")

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
    initial_state = ExportState(
        user_message=user_requirements,
        path="/",
        module=module_name,
        module_migration_plan=module_migration_plan_doc,
        high_level_migration_plan=high_level_migration_plan_doc,
        directory_listing=[],
        current_phase="module_selection",
        write_attempt_counter=0,
        validation_attempt_counter=0,
        validation_report="",
        last_output="",
        source_technology=technology,
    )

    result = workflow.invoke(initial_state)

    if result.failed:
        logger.error(
            f"Migration failed for module {module_name}: {result.failure_reason}"
        )
    else:
        logger.info(f"Migration completed successfully for module {module_name}!")

    return result
