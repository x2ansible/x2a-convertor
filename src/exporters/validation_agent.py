"""Validation agent for Chef to Ansible migration.

Validates and fixes migration output issues.
"""

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Literal

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph

from prompts.get_prompt import get_prompt
from src.config import get_settings
from src.exporters.agent_state import ValidationAgentState
from src.exporters.base_agent import BaseAgent
from src.exporters.services import CollectionManager, InstallResultSummary
from src.exporters.state import ChefState
from src.model import (
    get_last_ai_message,
    get_runnable_config,
    report_tool_calls,
)
from src.types import SUMMARY_SUCCESS_MESSAGE
from src.types.telemetry import AgentMetrics
from src.utils.config import get_config_int
from src.utils.logging import get_logger
from src.validation.service import ValidationService
from src.validation.validators import AnsibleLintValidator, RoleStructureValidator
from tools.ansible_lint import AnsibleLintTool
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.ansible_write import AnsibleWriteTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.diff_file import DiffFileTool
from tools.validated_write import ValidatedWriteTool

logger = get_logger(__name__)


class ValidationAgent(BaseAgent):
    """Agent responsible for validating and fixing migration output.

    This agent uses an internal StateGraph to manage validation/fix loops:
    - Validates output with ansible-lint and ansible-role-check
    - If errors found, uses react agent to fix them
    - Re-validates after fixes
    - Retries until validation passes OR max attempts reached

    The agent returns only when validation passes or max attempts exhausted.
    """

    # Base tools that this agent always has access to
    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ReadFileTool(),
        lambda: DiffFileTool(),
        lambda: ListDirectoryTool(),
        lambda: FileSearchTool(),
        lambda: ValidatedWriteTool(),  # Auto-routes YAML to ansible_write
        lambda: AnsibleWriteTool(),
        lambda: CopyFileWithMkdirTool(),
        lambda: AnsibleLintTool(),
        lambda: AnsibleRoleCheckTool(),
    ]

    USER_PROMPT_NAME = "export_ansible_validation_task"

    def __init__(self, model=None, max_attempts=None):
        """Initialize validation agent with validators, model, and max attempts.

        Args:
            model: LLM model to use (defaults to get_model())
            max_attempts: Maximum validation attempts (defaults to MAX_VALIDATION_ATTEMPTS config)
        """
        super().__init__(model)
        self.max_attempts = max_attempts or get_config_int("MAX_VALIDATION_ATTEMPTS")
        self.validators = [
            AnsibleLintValidator(),
            RoleStructureValidator(),
        ]
        self.validation_service = ValidationService(self.validators)
        self._graph = self._build_internal_graph()
        # Telemetry metrics reference (set during __call__)
        self._current_metrics: AgentMetrics | None = None

    def _build_internal_graph(self):
        """Build the internal StateGraph for validation workflow.

        Graph structure:
        START -> install_collections -> validate -> evaluate -> END / fix_errors / mark_failed
                                          ^                    |
                                          +--- fix_errors -----+
        """
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
        """Node: Install collections from requirements.yml before validation.

        This ensures that collection roles referenced via include_role are available
        for validation. Uses CollectionManager service which handles AAP Private Hub
        with Bearer token auth and falls back to public Galaxy.

        Args:
            state: Internal agent state

        Returns:
            Updated agent state (unchanged, this is a side-effect node)
        """
        slog = logger.bind(phase="install_collections")

        requirements_file = self._find_requirements_file(state.chef_state, slog)
        if requirements_file is None:
            slog.info("No requirements.yml found, skipping collection install")
            return state
        slog.info(f"Installing collections from '{requirements_file.resolve()}'")
        results = self._install_requirements(requirements_file)
        self._log_install_results(results, slog)

        return state

    def _find_requirements_file(self, chef_state: ChefState, slog) -> Path | None:
        """Find requirements.yml in standard locations."""
        search_paths = self._get_requirements_search_paths(chef_state)

        for path in search_paths:
            slog.debug(
                f"Checking for requirements.yml at: {path} (exists: {path.exists()})"
            )
            if path.exists():
                return path

        return None

    def _get_requirements_search_paths(self, chef_state: ChefState) -> list[Path]:
        """Get ordered list of paths to search for requirements.yml."""
        ansible_path = Path(chef_state.get_ansible_path())  # e.g., ansible/roles/cache
        ansible_root = ansible_path.parent.parent  # ansible/

        return [
            # Role-level (preferred)
            ansible_path / "requirements.yml",
            # Project-level
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

        # Record collection install metrics in telemetry
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
        """Node: Run validation service on the state.get_ansible_path().

        Args:
            state: Internal agent state

        Returns:
            Updated agent state with validation_results and has_errors
        """
        chef_state = state.chef_state

        slog = logger.bind(phase="validate", attempt=state.attempt)
        slog.info("Running validation")

        ansible_path = chef_state.get_ansible_path()

        # Run validation using service
        results = self.validation_service.validate_all(ansible_path)

        # Record per-validator results in telemetry
        if self._current_metrics:
            validators_passed = []
            validators_failed = []
            for name, result in results.items():
                if result.success:
                    validators_passed.append(name)
                else:
                    validators_failed.append(name)
            self._current_metrics.record_metric("validators_passed", validators_passed)
            self._current_metrics.record_metric("validators_failed", validators_failed)

        # Update internal state
        state.validation_results = results
        state.has_errors = self.validation_service.has_errors(results)

        if state.has_errors:
            error_report = self.validation_service.format_error_report(results)
            state.error_report = error_report
            slog.warning(f"Validation errors found:\n{error_report}")
            return state

        # No errors - mark complete
        slog.info("All validations passed")
        validation_report = (
            f"{SUMMARY_SUCCESS_MESSAGE}\n\n"
            + self.validation_service.get_success_message(results)
        )
        chef_state = chef_state.update(validation_report=validation_report)
        state.chef_state = chef_state
        state.complete = True

        return state

    # -------------------------------------------------------------------------
    # Fix Errors Node
    # -------------------------------------------------------------------------

    def _fix_errors_node(self, state: ValidationAgentState) -> ValidationAgentState:
        """Node: Use react agent to fix validation errors.

        Args:
            state: Internal agent state

        Returns:
            Updated agent state
        """
        chef_state = state.chef_state
        assert chef_state.checklist is not None, (
            "Checklist must exist before validation"
        )

        slog = logger.bind(phase="fix_errors", attempt=state.attempt)
        slog.info("Fixing validation errors")

        ansible_path = chef_state.get_ansible_path()

        # Create react agent to fix errors
        agent = self._create_react_agent(chef_state)

        # Use v2 validation prompt with few-shot examples
        validation_task = get_prompt(self.USER_PROMPT_NAME).format(
            module=chef_state.module,
            chef_path=chef_state.path,
            ansible_path=ansible_path,
            error_report=state.error_report,
        )

        result = agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": validation_task},
                ]
            },
            get_runnable_config(),
        )

        tool_calls = report_tool_calls(result)
        slog.info(f"Validation agent tools: {tool_calls.to_string()}")

        # Record tool calls in telemetry
        if self._current_metrics:
            self._current_metrics.record_tool_calls(tool_calls)

        chef_state.checklist.save(chef_state.get_checklist_path())

        # Extract validation report
        message = get_last_ai_message(result)
        if message:
            chef_state = chef_state.update(validation_report=message.content)

        # Update internal state
        state.chef_state = chef_state
        state.last_result = result
        state.attempt += 1

        slog.info("Fix iteration completed")
        return state

    # -------------------------------------------------------------------------
    # Mark Failed Node
    # -------------------------------------------------------------------------

    def _mark_failed_node(self, state: ValidationAgentState) -> ValidationAgentState:
        """Node: Mark the migration as failed due to validation errors.

        This node is reached when max validation attempts are exceeded.
        It updates the chef_state to mark the migration as failed.

        Args:
            state: Internal agent state

        Returns:
            Updated state with failed chef_state
        """
        slog = logger.bind(phase="mark_failed", attempt=state.attempt)
        slog.error(
            f"Max validation attempts ({state.max_attempts}) reached, "
            "marking migration as failed"
        )

        # Mark migration as failed
        chef_state = state.chef_state.mark_failed(
            f"Validation failed after {state.max_attempts} attempts. "
            f"Errors remain:\n{state.error_report}"
        )
        # Also set validation report for debugging
        chef_state = chef_state.update(
            validation_report=(
                f"Validation incomplete after {state.attempt} attempts:\n"
                f"{state.error_report}"
            )
        )
        state.chef_state = chef_state

        return state

    # -------------------------------------------------------------------------
    # Evaluation Edge (Pure Function)
    # -------------------------------------------------------------------------

    def _evaluate_validation_node(
        self, state: ValidationAgentState
    ) -> Literal["fix_errors", "mark_failed", "__end__"]:
        """Conditional edge: Decide whether to fix errors or finish.

        This is a pure function that only returns the decision.
        State mutations are handled by the respective nodes.

        Args:
            state: Internal agent state

        Returns:
            Next node name or END
        """
        slog = logger.bind(phase="evaluate_validation", attempt=state.attempt)

        # Already complete (set by validate_node on success)
        if state.complete:
            slog.info("Validation agent complete - all validations passed")
            return "__end__"

        # No errors means success (complete flag set by validate_node)
        if not state.has_errors:
            slog.info("No validation errors, finishing")
            return "__end__"

        # Max attempts reached - go to mark_failed
        if state.attempt >= state.max_attempts:
            return "mark_failed"

        # More attempts available - try to fix
        slog.info(
            f"Attempting to fix errors (attempt {state.attempt + 1}/{state.max_attempts})"
        )
        return "fix_errors"

    # -------------------------------------------------------------------------
    # Main Entry Point
    # -------------------------------------------------------------------------

    def __call__(self, state: ChefState) -> ChefState:
        """Execute validation workflow with internal retry loop.

        Args:
            state: Current migration state

        Returns:
            Updated ChefState after validation attempts
        """
        from src.exporters.chef_to_ansible import MigrationPhase

        slog = logger.bind(phase="validate_migration")
        slog.info("Starting validation agent workflow")

        # Set current phase
        state = state.update(current_phase=MigrationPhase.VALIDATING)

        with self._get_telemetry_context(state) as metrics:
            # Store metrics reference for internal nodes to use
            self._current_metrics = metrics

            # Create internal state and run internal graph
            internal_state = ValidationAgentState(
                chef_state=state,
                attempt=0,
                max_attempts=self.max_attempts,
                complete=False,
                has_errors=False,
            )

            final_state_dict = self._graph.invoke(internal_state, get_runnable_config())

            # Convert dict back to ValidationAgentState
            final_state = ValidationAgentState(**final_state_dict)

            # Record final telemetry metrics
            if metrics:
                metrics.record_metric("attempts", final_state.attempt)
                metrics.record_metric("complete", final_state.complete)
                metrics.record_metric("has_errors", final_state.has_errors)

            # Clear metrics reference
            self._current_metrics = None

            # Update chef_state with final counter
            chef_state = final_state.chef_state
            chef_state = chef_state.update(
                validation_attempt_counter=chef_state.validation_attempt_counter
                + final_state.attempt
            )

            slog.info(
                f"Validation agent finished: complete={final_state.complete}, "
                f"attempts={final_state.attempt}/{self.max_attempts}"
            )

        return chef_state
