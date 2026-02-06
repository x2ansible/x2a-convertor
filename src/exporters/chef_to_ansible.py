from enum import Enum
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.exporters.aap_discovery_agent import AAPDiscoveryAgent
from src.exporters.planning_agent import PlanningAgent
from src.exporters.state import ChefState
from src.exporters.types import MigrationCategory
from src.exporters.validation_agent import ValidationAgent
from src.exporters.write_agent import WriteAgent
from src.model import get_model, get_runnable_config
from src.types import (
    AnsibleModule,
    Checklist,
    DocumentFile,
    Telemetry,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class MigrationPhase(str, Enum):
    """Phases of the migration workflow"""

    INITIALIZING = "initializing"
    PLANNING = "planning"
    WRITING = "writing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"


class ChefToAnsibleSubagent:
    """Subagent called by the MigrationAgent to do the actual Chef -> Ansible export.

    This class orchestrates a three-agent workflow following DDD principles:
    1. Planning Agent: Analyzes migration plan and creates detailed checklist
    2. Write Agent: Creates all files from checklist (loops until all files exist)
    3. Validation Agent: Runs lint/role-check and fixes issues in batch mode

    The checklist is part of the domain state (ChefState) rather than instance state,
    ensuring agents remain stateless and derive their tools from the state object.
    """

    def __init__(self, model=None, module: AnsibleModule | None = None) -> None:
        self.model = model or get_model()
        if module is None:
            raise ValueError("module parameter is required")
        self.module = module

        # Initialize agent instances
        self.discovery_agent = AAPDiscoveryAgent(model=self.model)
        self.planning_agent = PlanningAgent(model=self.model)
        self.write_agent = WriteAgent(model=self.model)
        self.validation_agent = ValidationAgent(model=self.model)

        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _load_or_create_checklist(self, state: ChefState) -> Checklist:
        """Load existing checklist or create a new one.

        Args:
            state: Current migration state

        Returns:
            Loaded or newly created Checklist instance
        """
        checklist_path = state.get_checklist_path()
        if checklist_path.exists():
            logger.info(f"Loaded checklist from previous run: {checklist_path}")
            return Checklist.load(checklist_path, MigrationCategory)

        logger.info(f"Creating new checklist at {checklist_path}")
        checklist_path.parent.mkdir(parents=True, exist_ok=True)
        checklist = Checklist(str(self.module), MigrationCategory)
        checklist.save(checklist_path)
        return checklist

    def _create_workflow(self):
        """Create the main migration workflow.

        Agents handle their own retry/validation logic internally.
        If any agent fails (exhausts max attempts), it marks state.failed=True
        and the workflow skips directly to finalize.
        """
        workflow = StateGraph(ChefState)
        workflow.add_node("initialize", self._initialize)
        workflow.add_node("discover_collections", self.discovery_agent)
        workflow.add_node("plan_migration", self.planning_agent)
        workflow.add_node("write_migration", self.write_agent)
        workflow.add_node("validate_migration", self.validation_agent)
        workflow.add_node("finalize", self._finalize)

        # Check for failure after each agent
        workflow.add_edge(START, "initialize")
        workflow.add_edge("initialize", "discover_collections")
        workflow.add_edge("discover_collections", "plan_migration")

        # After planning: skip to finalize if failed
        workflow.add_conditional_edges(
            "plan_migration", self._check_failure_after_agent
        )

        # After write: skip to finalize if failed
        workflow.add_conditional_edges(
            "write_migration", self._check_failure_after_agent
        )

        # After validation: skip to finalize if failed
        workflow.add_conditional_edges(
            "validate_migration", self._check_failure_after_agent
        )

        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _initialize(self, state: ChefState) -> ChefState:
        """Initialize workflow by loading or creating checklist.

        Args:
            state: Current migration state

        Returns:
            Updated ChefState with checklist loaded
        """
        slog = logger.bind(phase="initialize")
        slog.info("Initializing migration workflow")

        # Ensure checklist is loaded or created
        if state.checklist is None:
            checklist = self._load_or_create_checklist(state)
            state = state.update(checklist=checklist)

        state = state.update(current_phase=MigrationPhase.PLANNING)
        return state

    def _check_failure_after_agent(
        self, state: ChefState
    ) -> Literal["write_migration", "validate_migration", "finalize"]:
        """Check if current agent failed, route to next phase or finalize.

        This is called after each agent (planning, write, validation) to check
        if the agent marked the migration as failed. If so, skip to finalize.

        Args:
            state: Current migration state

        Returns:
            Next node based on current phase and failure status
        """
        if state.failed:
            logger.error(
                f"Agent failed in phase {state.current_phase}, skipping to finalize: {state.failure_reason}"
            )
            return "finalize"

        # Route to next phase based on current phase
        if state.current_phase == MigrationPhase.PLANNING:
            return "write_migration"
        elif state.current_phase in (MigrationPhase.WRITING, "writing"):
            return "validate_migration"
        else:  # VALIDATING or any other phase
            return "finalize"

    def _finalize(self, state: ChefState) -> ChefState:
        """Finalize migration and report results.

        Handles both successful and failed migrations.
        """
        slog = logger.bind(phase="finalize")

        assert state.checklist is not None, (
            "Checklist must be initialized before finalize"
        )
        checklist = state.checklist  # Store for type narrowing
        stats = checklist.get_stats()

        if state.failed:
            # Failed migration path
            slog.error(f"Migration failed: {state.failure_reason}")
            state = state.update(current_phase=MigrationPhase.FAILED)

            summary_lines = [
                f"❌ MIGRATION FAILED for {state.module}",
                "",
                "Failure Reason:",
                f"  {state.failure_reason}",
                "",
                "Migration Summary:",
                f"  Total items: {stats['total']}",
                f"  Completed: {stats['complete']}",
                f"  Pending: {stats['pending']}",
                f"  Missing: {stats['missing']}",
                f"  Errors: {stats['error']}",
                f"  Write attempts: {state.write_attempt_counter}",
                f"  Validation attempts: {state.validation_attempt_counter}",
                "",
                "Partial Validation Report:",
                state.validation_report or "Not run",
                "",
                "Partial Checklist:",
                checklist.to_markdown(),
            ]

            # Add telemetry summary
            if state.telemetry:
                summary_lines.append("")
                summary_lines.append("Telemetry:")
                summary_lines.append(state.telemetry.to_summary())

            slog.error(
                f"Migration failed: {stats['complete']}/{stats['total']} completed"
            )
        else:
            # Successful migration path
            slog.info("Finalizing successful migration")
            state = state.update(current_phase=MigrationPhase.COMPLETE)

            summary_lines = [
                f"✅ Migration Summary for {state.module}:",
                f"  Total items: {stats['total']}",
                f"  Completed: {stats['complete']}",
                f"  Pending: {stats['pending']}",
                f"  Missing: {stats['missing']}",
                f"  Errors: {stats['error']}",
                f"  Write attempts: {state.write_attempt_counter}",
                f"  Validation attempts: {state.validation_attempt_counter}",
                "",
                "Final Validation Report:",
                state.validation_report,
                "",
                "Final checklist:",
                checklist.to_markdown(),
            ]

            # Add telemetry summary
            if state.telemetry:
                summary_lines.append("")
                summary_lines.append("Telemetry:")
                summary_lines.append(state.telemetry.to_summary())

            slog.info(
                f"Migration finalized: {stats['complete']}/{stats['total']} completed"
            )

        summary_text = "\n".join(summary_lines)

        # Stop telemetry and save with summary
        if state.telemetry:
            state.telemetry.stop().with_summary(summary_text).save()

        state = state.update(last_output=summary_text)
        return state

    def invoke(
        self,
        path: str,
        user_message: str,
        module_migration_plan: DocumentFile,
        high_level_migration_plan: DocumentFile,
        directory_listing: list[str],
    ) -> ChefState:
        """Execute the complete Chef to Ansible migration workflow.

        The workflow will discover collections on AAP and from there load or create the checklist during the planning phase.

        Args:
            path: Path to the Chef cookbook
            user_message: User requirements
            module_migration_plan: Detailed migration plan document
            high_level_migration_plan: High-level strategy document
            directory_listing: Files in source directory
        """
        logger.info(f"Starting Chef to Ansible migration for module: {self.module}")

        initial_state = ChefState(
            path=path,
            module=self.module,
            user_message=user_message,
            module_migration_plan=module_migration_plan,
            high_level_migration_plan=high_level_migration_plan,
            directory_listing=directory_listing,
            current_phase=MigrationPhase.INITIALIZING,
            write_attempt_counter=0,
            validation_attempt_counter=0,
            validation_report="",
            last_output="",
            checklist=None,  # Will be loaded/created during planning phase
            aap_discovery=None,  # Will be populated by discovery agent
            failed=False,
            failure_reason="",
            telemetry=Telemetry(phase="migrate"),
        )

        result = self._workflow.invoke(
            input=initial_state, config=get_runnable_config()
        )
        return ChefState(**result)
