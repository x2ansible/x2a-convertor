"""Migration analysis workflow.

This module implements the MigrationAnalysisWorkflow that orchestrates
module selection, technology-specific analysis, and plan generation.
"""

from pathlib import Path

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.const import MIGRATION_PLAN_FILE
from src.inputs.analyze_state import MigrationState
from src.inputs.chef import ChefSubagent
from src.inputs.module_selection_agent import ModuleSelectionAgent
from src.model import get_model, get_runnable_config
from src.types import Telemetry, telemetry_context
from src.utils.logging import get_logger
from src.utils.technology import Technology

logger = get_logger(__name__)


class MigrationAnalysisWorkflow:
    def __init__(self, model=None) -> None:
        self.model = model or get_model()
        self.chef_subagent = ChefSubagent(model=self.model)
        self.module_selection_agent = ModuleSelectionAgent(model=self.model)
        self.graph = self._build_graph()
        logger.debug(self.graph.get_graph().draw_mermaid())

    def _build_graph(self) -> CompiledStateGraph:
        workflow = StateGraph(MigrationState)

        workflow.add_node(
            "read_migration_plan", lambda state: self.read_migration_plan(state)
        )
        workflow.add_node("select_module", self.module_selection_agent)
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
        """Read the migration_plan.md file."""
        migration_plan_path = Path(MIGRATION_PLAN_FILE)

        if not migration_plan_path.exists():
            logger.warning("No existing migration plan found, starting fresh")
            return state.update(
                migration_plan_content=(
                    "# Migration Plan\n\nNo existing migration plan found."
                )
            )

        logger.info(f"Read migration plan from {migration_plan_path}")
        return state.update(migration_plan_content=migration_plan_path.read_text())

    def choose_subagent(self, state: MigrationState) -> MigrationState:
        """Choose and execute the appropriate subagent based on technology."""
        technology = state.technology

        with telemetry_context(state.telemetry, "choose_subagent") as metrics:
            if technology == Technology.CHEF:
                module_plan = self.chef_subagent.invoke(
                    state.path, state.user_message, telemetry=state.telemetry
                )
                if metrics:
                    metrics.record_metric("subagent", "ChefSubagent")
                return state.update(module_migration_plan=module_plan)

            if technology == Technology.PUPPET:
                logger.warning("Puppet agent not implemented yet")
                if metrics:
                    metrics.record_metric(
                        "subagent", "PuppetSubagent (not implemented)"
                    )
                return state.update(
                    module_migration_plan="Puppet analysis not available"
                )

            if technology == Technology.SALT:
                logger.warning("Salt agent not implemented yet")
                if metrics:
                    metrics.record_metric("subagent", "SaltSubagent (not implemented)")
                return state.update(module_migration_plan="Salt analysis not available")

            logger.error("Technology not set correctly")
            if metrics:
                metrics.record_metric("subagent", "unknown")
            return state.update(module_migration_plan="Technology analysis failed")

    def write_migration_file(self, state: MigrationState) -> MigrationState:
        """Write the migration plan to a file."""
        migration_content = state.module_migration_plan
        if not migration_content:
            logger.error("Migration failed, no plan generated")
            return state

        filename = state.get_migration_plan_path()
        Path(filename).write_text(migration_content)
        logger.info(f"Migration plan written to {filename}")

        if state.telemetry:
            state.telemetry.with_summary(f"Migration plan written to {filename}")

        return state.update(module_plan_path=filename)


def analyze_project(user_requirements: str, source_dir: str = "."):
    """Create dependency graph and granular migration tasks."""
    logger.info("Starting migration analysis workflow...")

    workflow = MigrationAnalysisWorkflow()
    telemetry = Telemetry(phase="analyze")
    initial_state = MigrationState(
        user_message=user_requirements,
        path="/",
        name="",
        technology=None,
        migration_plan_content="",
        module_migration_plan="",
        module_plan_path="",
        telemetry=telemetry,
    )

    result = workflow.graph.invoke(initial_state, config=get_runnable_config())

    # Stop telemetry and save
    telemetry.stop().save()
    logger.info(f"Telemetry summary:\n{telemetry.to_summary()}")

    logger.info("Chef to Ansible migration analysis completed successfully!")
    return result
