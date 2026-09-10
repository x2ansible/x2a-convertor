"""Validation agent for Chef to Ansible migration.

Validates and fixes migration output issues using APME's rule catalog.
"""

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Literal

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from prompts.get_prompt import get_prompt
from src.config import get_settings
from src.exporters.agent_state import ValidationAgentState
from src.exporters.export_agent import ExportAgent
from src.exporters.services import CollectionManager, InstallResultSummary
from src.exporters.state import ExportState
from src.exporters.tools.apme import APME, ApmeRuleDoc, CheckReport
from src.model import get_runnable_config
from src.types import SUMMARY_SUCCESS_MESSAGE
from src.types.telemetry import AgentMetrics
from src.utils.config import get_config_int
from src.utils.logging import get_logger
from tools.ansible_lint import AnsibleLintTool
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.ansible_rule_doc import AnsibleRuleDocTool
from tools.ansible_write import AnsibleWriteTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.read_file import ReadFileTool
from tools.validated_write import ValidatedWriteTool

logger = get_logger(__name__)


class ErrorFingerprint:
    """Extracts stable error signatures from APME check reports.

    Fingerprints capture (rule_id, file) pairs without line-number
    information, so cosmetic reformatting doesn't hide a real fix and
    genuinely unchanged violations are detected as a stall.
    """

    @staticmethod
    def extract_from_report(report: CheckReport | None) -> frozenset[tuple[str, str]]:
        """Extract violation fingerprints from an APME check report.

        Args:
            report: CheckReport from APME.check(), or None.

        Returns:
            Frozenset of (rule_id, file) tuples for all reported violations.
        """
        if not report:
            return frozenset()

        return frozenset((v.rule_id, v.file) for v in report.violations)


class ValidationAgent(ExportAgent[ExportState]):
    """Agent responsible for validating and fixing migration output.

    This agent uses an internal StateGraph to manage validation/fix loops:
    - Validates output with APME's rule catalog (ansible_role_check)
    - If errors found, uses react agent to fix them
    - Re-validates after fixes
    - Retries until validation passes OR max attempts reached

    The agent returns only when validation passes or max attempts exhausted.
    """

    _NAME = "Ansible Validator"

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ReadFileTool(),
        lambda: ListDirectoryTool(),
        lambda: FileSearchTool(),
        lambda: ValidatedWriteTool(),  # Auto-routes YAML to ansible_write
        lambda: AnsibleWriteTool(),
        lambda: CopyFileWithMkdirTool(),
        lambda: AnsibleRoleCheckTool(),
        lambda: AnsibleRuleDocTool(),
        lambda: AnsibleLintTool(),
    ]

    USER_PROMPT_NAME = "export_ansible_validation_task"

    def __init__(self, model=None, max_attempts=None):
        super().__init__(model)
        self.max_attempts = max_attempts or get_config_int("MAX_VALIDATION_ATTEMPTS")
        self._apme = APME()
        self._graph = self._build_internal_graph()
        self._current_metrics: AgentMetrics | None = None

    def _build_internal_graph(self):
        """Build the internal StateGraph for validation workflow."""
        workflow = StateGraph(ValidationAgentState)
        workflow.add_node("install_collections", self._install_collections_node)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("fix_errors", self._fix_errors_node)
        workflow.add_node("mark_failed", self._mark_failed_node)

        workflow.add_edge(START, "install_collections")
        workflow.add_edge("install_collections", "validate")
        workflow.add_conditional_edges("validate", self._evaluate_validation_node)
        workflow.add_edge("fix_errors", "validate")  # Loop back to re-validate
        workflow.add_edge("mark_failed", END)

        return workflow.compile()

    # -------------------------------------------------------------------------
    # Collection Installation Node
    # -------------------------------------------------------------------------

    def _install_collections_node(
        self, state: ValidationAgentState
    ) -> ValidationAgentState:
        """Node: Install collections from requirements.yml before validation."""
        slog = logger.bind(phase="install_collections")

        requirements_file = self._find_requirements_file(state.export_state, slog)
        if requirements_file is None:
            slog.info("No requirements.yml found, skipping collection install")
            return state
        slog.info(f"Installing collections from '{requirements_file.resolve()}'")
        results = self._install_requirements(requirements_file)
        self._log_install_results(results, slog)

        return state

    def _find_requirements_file(self, export_state: ExportState, slog) -> Path | None:
        """Find requirements.yml in standard locations."""
        search_paths = self._get_requirements_search_paths(export_state)

        for path in search_paths:
            slog.debug(
                f"Checking for requirements.yml at: {path} (exists: {path.exists()})"
            )
            if path.exists():
                return path

        return None

    def _get_requirements_search_paths(self, export_state: ExportState) -> list[Path]:
        """Get ordered list of paths to search for requirements.yml."""
        ansible_path = Path(export_state.get_ansible_path())
        ansible_root = ansible_path.parent.parent

        return [
            ansible_path / "requirements.yml",
            ansible_root / "requirements.yml",
        ]

    def _install_requirements(self, requirements_file: Path) -> list:
        """Install collections from requirements file."""
        aap_settings = get_settings().aap
        manager = CollectionManager.from_settings(aap_settings)
        return manager.install_from_requirements(requirements_file)

    def _log_install_results(self, results: list, slog) -> None:
        """Log summary of installation results."""
        summary = InstallResultSummary.from_results(results)

        if self._current_metrics:
            self._current_metrics.record_metric(
                "collections_installed", summary.success_count
            )
            self._current_metrics.record_metric(
                "collections_failed", summary.fail_count
            )

        if summary.all_succeeded:
            slog.info(f"All {summary.success_count} collections installed successfully")
            return

        slog.warning(
            f"Collection install: {summary.success_count} succeeded, "
            f"{summary.fail_count} failed"
        )
        for failure in summary.failures:
            slog.warning(f"  Failed: {failure.collection.fqcn} ({failure.source})")

    # -------------------------------------------------------------------------
    # Validation Node
    # -------------------------------------------------------------------------

    def _validate_node(self, state: ValidationAgentState) -> ValidationAgentState:
        """Node: Run APME check on the state.get_ansible_path()."""
        export_state = state.export_state

        slog = logger.bind(phase="validate", attempt=state.attempt)
        slog.info("Running APME check")

        ansible_path = export_state.get_ansible_path()

        report = self._apme.check(ansible_path)

        if self._current_metrics:
            self._current_metrics.record_metric("violations", len(report.violations))
            self._current_metrics.record_metric("errors", report.error_count)
            self._current_metrics.record_metric("warnings", report.warning_count)

        state.previous_validation_report = state.validation_report
        state.validation_report = report

        # Mirrors `apme check` exit-code semantics: any violation is a failure,
        # regardless of severity (0 = no violations, 1 = violations found).
        state.has_errors = report.has_violations

        if state.has_errors:
            slog.warning(f"APME check found violations: {report.summary()}")
            return state

        slog.info("APME check passed")

        success_report = f"{SUMMARY_SUCCESS_MESSAGE}\n\n{report.to_xml_prompt()}"
        export_state = export_state.update(validation_report=success_report)
        state.export_state = export_state
        state.complete = True

        return state

    # -------------------------------------------------------------------------
    # Fix Errors Node
    # -------------------------------------------------------------------------

    def _fix_errors_node(self, state: ValidationAgentState) -> ValidationAgentState:
        """Node: Use react agent to fix validation errors."""
        export_state = state.export_state
        assert export_state.checklist is not None, (
            "Checklist must exist before validation"
        )

        slog = logger.bind(phase="fix_errors", attempt=state.attempt)
        slog.info("Fixing validation errors")

        ansible_path = export_state.get_ansible_path()

        assert state.validation_report is not None, (
            "validation_report must be set before fixing errors"
        )
        validation_task = get_prompt(self.USER_PROMPT_NAME).format(
            module=export_state.module,
            chef_path=export_state.path,
            ansible_path=ansible_path,
            error_report=state.render_errors(),
            rule_docs=ApmeRuleDoc.render_all(state.validation_report.get_errors_doc()),
        )
        result = self.invoke_react(
            export_state,
            [
                {"role": "user", "content": validation_task},
            ],
            self._current_metrics,
        )

        export_state.checklist.save(export_state.get_checklist_path())

        message = self.get_last_ai_message(result)
        if message:
            export_state = export_state.update(validation_report=message.text)

        state.export_state = export_state
        state.attempt += 1

        slog.info("Fix iteration completed")
        return state

    # -------------------------------------------------------------------------
    # Mark Failed Node
    # -------------------------------------------------------------------------

    def _mark_failed_node(self, state: ValidationAgentState) -> ValidationAgentState:
        """Node: Mark the migration as failed due to validation errors."""
        slog = logger.bind(phase="mark_failed", attempt=state.attempt)

        reason = self._get_failure_reason(state)
        slog.error(reason)

        errors = state.render_errors()
        export_state = state.export_state.mark_failed(
            f"{reason}\nErrors remain:\n{errors}"
        )
        export_state = export_state.update(
            validation_report=(
                f"Validation incomplete after {state.attempt} attempts:\n{errors}"
            )
        )
        state.export_state = export_state

        return state

    # -------------------------------------------------------------------------
    # Stall Detection
    # -------------------------------------------------------------------------

    def _errors_are_stale(self, state: ValidationAgentState) -> bool:
        """Return True when the same error types persist from previous attempt.

        Uses error fingerprints instead of raw string comparison to detect
        when the LLM makes cosmetic changes (moves code, reformats) without
        actually fixing validation errors.
        """
        if not state.previous_validation_report:
            return False

        current_fingerprint = ErrorFingerprint.extract_from_report(
            state.validation_report
        )
        previous_fingerprint = ErrorFingerprint.extract_from_report(
            state.previous_validation_report
        )

        return current_fingerprint == previous_fingerprint

    def _get_failure_reason(self, state: ValidationAgentState) -> str:
        """Return a human-readable reason for validation failure."""
        if self._errors_are_stale(state):
            return (
                f"Stall detected after {state.attempt} attempt(s): "
                "errors unchanged between attempts, aborting."
            )
        return (
            f"Max validation attempts ({state.max_attempts}) reached, "
            "marking migration as failed."
        )

    # -------------------------------------------------------------------------
    # Evaluation Edge (Pure Function)
    # -------------------------------------------------------------------------

    def _evaluate_validation_node(
        self, state: ValidationAgentState
    ) -> Literal["fix_errors", "mark_failed", "__end__"]:
        """Conditional edge: Decide whether to fix errors or finish."""
        slog = logger.bind(phase="evaluate_validation", attempt=state.attempt)

        if state.complete:
            slog.info("Validation agent complete - all validations passed")
            return "__end__"

        if not state.has_errors:
            slog.info("No validation errors, finishing")
            return "__end__"

        if state.attempt >= state.max_attempts:
            return "mark_failed"

        if self._errors_are_stale(state):
            slog.warning(
                f"Stall detected: same error types persist after fix attempt\n"
                f"Latest errors:\n{state.render_errors()}"
            )
            return "mark_failed"

        slog.info(
            f"Attempting to fix errors (attempt {state.attempt + 1}/{state.max_attempts})"
        )
        return "fix_errors"

    # -------------------------------------------------------------------------
    # Main Entry Point
    # -------------------------------------------------------------------------

    def execute(self, state: ExportState, metrics: AgentMetrics | None) -> ExportState:
        """Execute validation workflow with internal retry loop."""
        from src.exporters.to_ansible import MigrationPhase

        self._log.info("Starting validation agent workflow")

        state = state.update(current_phase=MigrationPhase.VALIDATING)

        # Store metrics reference for internal nodes to use
        self._current_metrics = metrics

        internal_state = ValidationAgentState(
            export_state=state,
            attempt=0,
            max_attempts=self.max_attempts,
            complete=False,
            has_errors=False,
        )

        final_state_dict = self._graph.invoke(internal_state, get_runnable_config())
        final_state = ValidationAgentState(**final_state_dict)

        if metrics:
            metrics.record_metric("attempts", final_state.attempt)
            metrics.record_metric("complete", final_state.complete)
            metrics.record_metric("has_errors", final_state.has_errors)

        self._current_metrics = None

        export_state = final_state.export_state
        export_state = export_state.update(
            validation_attempt_counter=export_state.validation_attempt_counter
            + final_state.attempt
        )

        self._log.info(
            f"Validation agent finished: complete={final_state.complete}, "
            f"attempts={final_state.attempt}/{self.max_attempts}"
        )

        return export_state
