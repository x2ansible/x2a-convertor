"""Technology-agnostic infrastructure-to-Ansible migration subagent.

This module implements the ToAnsibleSubagent that orchestrates the export
pipeline. The export agents (Planning, Write, Validation) work from migration
plans and checklists - they are not technology-specific.
"""

from enum import Enum
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.exporters.aap_discovery_agent import AAPDiscoveryAgent
from src.exporters.molecule_agent import MoleculeAgent
from src.exporters.planning_agent import PlanningAgent
from src.exporters.state import ExportState
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
from src.types.technology import Technology
from src.utils.logging import get_logger

logger = get_logger(__name__)


class MigrationPhase(str, Enum):
    """Phases of the migration workflow"""

    INITIALIZING = "initializing"
    PLANNING = "planning"
    WRITING = "writing"
    MOLECULE_TESTING = "molecule_testing"
    VALIDATING = "validating"
    COMPLETE = "complete"
    FAILED = "failed"


class ToAnsibleSubagent:
    """Subagent that exports infrastructure code to Ansible roles.

    This class orchestrates a multi-agent workflow following DDD principles:
    1. Planning Agent: Analyzes migration plan and creates detailed checklist
    2. Write Agent: Creates all files from checklist (loops until all files exist)
    3. Validation Agent: Runs lint/role-check and fixes issues in batch mode

    The checklist is part of the domain state (ExportState) rather than instance
    state, ensuring agents remain stateless and derive their tools from the
    state object.
    """

    def __init__(self, model=None, module: AnsibleModule | None = None) -> None:
        self.model = model or get_model()
        if module is None:
            raise ValueError("module parameter is required")
        self.module = module

        self.discovery_agent = AAPDiscoveryAgent(model=self.model)
        self.planning_agent = PlanningAgent(model=self.model)
        self.write_agent = WriteAgent(model=self.model)
        self.molecule_agent = MoleculeAgent(model=self.model)
        self.validation_agent = ValidationAgent(model=self.model)

        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _load_or_create_checklist(self, state: ExportState) -> Checklist:
        """Load existing checklist or create a new one."""
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
        """Create the main migration workflow."""
        workflow = StateGraph(ExportState)
        workflow.add_node("initialize", self._initialize)
        workflow.add_node("discover_collections", self.discovery_agent)
        workflow.add_node("plan_migration", self.planning_agent)
        workflow.add_node("write_migration", self.write_agent)
        workflow.add_node("molecule_testing", self.molecule_agent)
        workflow.add_node("validate_migration", self.validation_agent)
        workflow.add_node("finalize", self._finalize)

        workflow.add_edge(START, "initialize")
        workflow.add_edge("initialize", "discover_collections")
        workflow.add_edge("discover_collections", "plan_migration")

        workflow.add_conditional_edges(
            "plan_migration", self._check_failure_after_agent
        )
        workflow.add_conditional_edges(
            "write_migration", self._check_failure_after_agent
        )
        workflow.add_conditional_edges(
            "molecule_testing", self._check_failure_after_agent
        )
        workflow.add_conditional_edges(
            "validate_migration", self._check_failure_after_agent
        )

        workflow.add_edge("finalize", END)

        return workflow.compile()

    def _initialize(self, state: ExportState) -> ExportState:
        """Initialize workflow by loading or creating checklist."""
        slog = logger.bind(phase="initialize")
        slog.info("Initializing migration workflow")

        if state.checklist is None:
            checklist = self._load_or_create_checklist(state)
            state = state.update(checklist=checklist)

        return state.update(current_phase=MigrationPhase.PLANNING)

    def _check_failure_after_agent(
        self, state: ExportState
    ) -> Literal[
        "write_migration", "molecule_testing", "validate_migration", "finalize"
    ]:
        """Check if current agent failed, route to next phase or finalize."""
        if state.failed:
            logger.error(
                f"Agent failed in phase {state.current_phase}, "
                f"skipping to finalize: {state.failure_reason}"
            )
            return "finalize"

        if state.current_phase == MigrationPhase.PLANNING:
            return "write_migration"
        if state.current_phase in (MigrationPhase.WRITING, "writing"):
            return "molecule_testing"
        if state.current_phase in (
            MigrationPhase.MOLECULE_TESTING,
            "molecule_testing",
        ):
            return "validate_migration"
        return "finalize"

    def _finalize(self, state: ExportState) -> ExportState:
        """Finalize migration and report results."""
        slog = logger.bind(phase="finalize")

        assert state.checklist is not None, (
            "Checklist must be initialized before finalize"
        )
        checklist = state.checklist
        stats = checklist.get_stats()

        summary_lines = (
            self._build_failure_summary(state, stats, checklist)
            if state.failed
            else self._build_success_summary(state, stats, checklist)
        )

        if state.failed:
            slog.error(f"Migration failed: {state.failure_reason}")
            state = state.update(current_phase=MigrationPhase.FAILED)
            slog.error(
                f"Migration failed: {stats['complete']}/{stats['total']} completed"
            )
        else:
            slog.info("Finalizing successful migration")
            state = state.update(current_phase=MigrationPhase.COMPLETE)
            slog.info(
                f"Migration finalized: {stats['complete']}/{stats['total']} completed"
            )

        if state.telemetry:
            summary_lines.extend(["", "Telemetry:", state.telemetry.to_summary()])

        summary_text = "\n".join(summary_lines)

        if state.telemetry:
            state.telemetry.stop().with_summary(summary_text).save()

        return state.update(last_output=summary_text)

    def _build_failure_summary(
        self, state: ExportState, stats: dict, checklist: Checklist
    ) -> list[str]:
        """Build summary lines for a failed migration."""
        return [
            f"MIGRATION FAILED for {state.module}",
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

    def _build_success_summary(
        self, state: ExportState, stats: dict, checklist: Checklist
    ) -> list[str]:
        """Build summary lines for a successful migration."""
        return [
            f"Migration Summary for {state.module}:",
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

    def invoke(
        self,
        path: str,
        user_message: str,
        module_migration_plan: DocumentFile,
        high_level_migration_plan: DocumentFile,
        directory_listing: list[str],
        source_technology=None,
    ) -> ExportState:
        """Execute the complete migration workflow.

        Args:
            path: Path to source infrastructure code
            user_message: User requirements
            module_migration_plan: Detailed migration plan document
            high_level_migration_plan: High-level strategy document
            directory_listing: Files in source directory
        """
        logger.info(f"Starting migration to Ansible for module: {self.module}")

        initial_state = ExportState(
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
            checklist=None,
            aap_discovery=None,
            source_technology=source_technology or Technology.CHEF,
            failed=False,
            failure_reason="",
            telemetry=Telemetry(phase="migrate"),
        )

        result = self._workflow.invoke(
            input=initial_state, config=get_runnable_config()
        )
        return ExportState(**result)
