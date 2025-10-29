"""Validation agent for Chef to Ansible migration.

Validates and fixes migration output issues.
"""

from typing import Literal, TYPE_CHECKING

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langgraph.graph import StateGraph, START, END

from src.exporters.agent_state import ValidationAgentState
from src.exporters.base_agent import BaseAgent
from src.exporters.state import ChefState
from src.model import (
    get_last_ai_message,
    get_runnable_config,
    report_tool_calls,
)
from src.types import SUMMARY_SUCCESS_MESSAGE
from src.utils.config import get_config_int
from src.utils.logging import get_logger
from src.validation.service import ValidationService
from src.validation.validators import AnsibleLintValidator, RoleStructureValidator
from prompts.get_prompt import get_prompt
from tools.ansible_lint import AnsibleLintTool
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.ansible_write import AnsibleWriteTool
from tools.copy_file import CopyFileWithMkdirTool
from tools.diff_file import DiffFileTool
from tools.validated_write import ValidatedWriteTool

if TYPE_CHECKING:
    from src.exporters.chef_to_ansible import MigrationPhase

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
    BASE_TOOLS = [
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

    def _build_internal_graph(self):
        """Build the internal StateGraph for validation workflow.

        Graph structure:
        START → validate → evaluate → END
                    ↑          ↓
                    └─ fix_errors (if has errors)
        """
        workflow = StateGraph(ValidationAgentState)
        workflow.add_node("validate", self._validate_node)
        workflow.add_node("fix_errors", self._fix_errors_node)

        workflow.add_edge(START, "validate")
        workflow.add_conditional_edges("validate", self._evaluate_validation_node)
        workflow.add_edge("fix_errors", "validate")  # Loop back to re-validate

        return workflow.compile()

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

        # Update internal state
        state.validation_results = results
        state.has_errors = self.validation_service.has_errors(results)

        if state.has_errors:
            error_report = self.validation_service.format_error_report(results)
            state.error_report = error_report
            slog.warning(f"Validation errors found:\n{error_report}")
        else:
            slog.info("All validations passed")
            validation_report = (
                f"{SUMMARY_SUCCESS_MESSAGE}\n\n"
                + self.validation_service.get_success_message(results)
            )
            chef_state = chef_state.update(validation_report=validation_report)
            state.chef_state = chef_state
            state.complete = True

        return state

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

        slog.info(f"Validation agent tools: {report_tool_calls(result).to_string()}")
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

    def _evaluate_validation_node(
        self, state: ValidationAgentState
    ) -> Literal["fix_errors", "__end__"]:
        """Conditional edge: Decide whether to fix errors or finish.

        Args:
            state: Internal agent state

        Returns:
            Next node name or END
        """
        slog = logger.bind(phase="evaluate_validation", attempt=state.attempt)

        if state.complete:
            slog.info("Validation agent complete - all validations passed")
            return "__end__"

        if not state.has_errors:
            slog.info("No validation errors, finishing")
            state.complete = True
            return "__end__"

        if state.attempt >= state.max_attempts:
            slog.error(
                f"Max validation attempts ({state.max_attempts}) reached, marking migration as failed"
            )
            # Mark migration as failed
            chef_state = state.chef_state.mark_failed(
                f"Validation failed after {state.max_attempts} attempts. Errors remain:\n{state.error_report}"
            )
            # Also set validation report for debugging
            chef_state = chef_state.update(
                validation_report=f"Validation incomplete after {state.attempt} attempts:\n{state.error_report}"
            )
            state.chef_state = chef_state
            return "__end__"

        slog.info(
            f"Attempting to fix errors (attempt {state.attempt + 1}/{state.max_attempts})"
        )
        return "fix_errors"

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
