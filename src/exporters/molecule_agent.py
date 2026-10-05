"""Generate and statically validate project-level Molecule scenarios."""

from collections.abc import Callable
from typing import ClassVar

from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.exporters.export_agent import ExportAgent
from src.exporters.services.molecule_project import MoleculeProject
from src.exporters.state import ExportState
from src.exporters.types import MoleculeStatus
from src.types import ChecklistStatus
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger
from tools.write_file import WriteFileTool

logger = get_logger(__name__)


class MoleculeAgent(ExportAgent[ExportState]):
    """Create deterministic Ansible-native scenarios and LLM-based verification."""

    _NAME = "Molecule Test Generator"
    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [lambda: WriteFileTool()]
    SYSTEM_PROMPT_NAME = "export_ansible_molecule_system"
    USER_PROMPT_NAME = "export_ansible_molecule_task"
    MAX_GENERATION_ATTEMPTS = 2

    def execute(self, state: ExportState, metrics: AgentMetrics | None) -> ExportState:
        """Scaffold scenario files, generate verification, and report static status."""
        self._log.info("Generating project-level Molecule scenario")
        state = state.update(current_phase="molecule_testing")
        if state.checklist is None:
            return self._generation_failed(state, "Migration checklist is unavailable")

        project = MoleculeProject(state.layout)
        try:
            project.scaffold()
            errors, attempts = self._generate_and_validate(state, project, metrics)
        except Exception as error:
            self._mark_verification_error(state, [str(error)])
            return self._generation_failed(state, str(error))

        if errors:
            return self._generation_failed(state, "; ".join(errors))

        self._mark_checklist_complete(state)
        state.checklist.save(state.checklist_path)
        if metrics:
            metrics.record_metric("molecule_generation_attempts", attempts)
            metrics.record_metric("molecule_static_validation", True)
        return state.update(
            molecule_status=MoleculeStatus.NOT_EXECUTED,
            molecule_report=(
                "Scenario files passed static validation. Molecule was not run by the converter; "
                "developer/CI execution is required for runtime acceptance."
            ),
        )

    def _generate_and_validate(
        self,
        state: ExportState,
        project: MoleculeProject,
        metrics: AgentMetrics | None,
    ) -> tuple[list[str], int]:
        """Retry verify generation only while static validation reports errors."""
        errors = project.validate_scaffold()
        if errors:
            return errors, 0
        errors = project.validate()
        if not errors:
            return [], 0
        for attempt in range(1, self.MAX_GENERATION_ATTEMPTS + 1):
            self._write_verification(state, errors, metrics)
            errors = project.validate()
            if not errors:
                return [], attempt
        self._mark_verification_error(state, errors)
        return errors, self.MAX_GENERATION_ATTEMPTS

    def _write_verification(
        self,
        state: ExportState,
        errors: list[str],
        metrics: AgentMetrics | None,
    ) -> None:
        """Invoke the LLM only for source-grounded verify.yml generation."""
        verify_path = state.molecule_verify_path
        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        task_message = get_prompt(self.USER_PROMPT_NAME).format(
            module=state.module,
            scenario_name=str(state.module),
            verify_path=verify_path,
            migration_plan=state.module_migration_plan.to_document(),
            validation_errors="\n".join(errors),
        )
        self.invoke_react(
            state,
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": str(task_message)},
            ],
            metrics,
        )

    def _mark_checklist_complete(self, state: ExportState) -> None:
        """Mark generated artifacts complete after the entire scenario validates."""
        assert state.checklist is not None
        for target_path in state.molecule_checklist_targets():
            if not state.checklist.update_task(
                source_path="N/A",
                target_path=target_path,
                status=ChecklistStatus.COMPLETE,
                notes="Generated and statically validated; runtime execution is pending.",
            ):
                logger.warning(
                    "Molecule checklist target not found", target=target_path
                )

    def _mark_verification_error(self, state: ExportState, errors: list[str]) -> None:
        """Persist static validation failure against the verify checklist item."""
        assert state.checklist is not None
        verify_path = str(state.molecule_verify_path)
        state.checklist.update_task(
            source_path="N/A",
            target_path=verify_path,
            status=ChecklistStatus.ERROR,
            notes="; ".join(errors),
        )
        state.checklist.save(state.checklist_path)

    def _generation_failed(self, state: ExportState, reason: str) -> ExportState:
        """Keep migration nonfatal but make unverified tests visible to users."""
        self._log.warning("Molecule generation is unverified", reason=reason)
        return state.update(
            molecule_status=MoleculeStatus.GENERATION_FAILED,
            molecule_report=f"Static generation/validation failed: {reason}",
        )
