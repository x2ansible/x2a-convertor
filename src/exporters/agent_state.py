"""Internal state classes for agent workflows.

These states are used within agents' internal StateGraphs to manage
their work/validation loops independently from the parent workflow.
"""

from dataclasses import dataclass
from typing import Any

from src.exporters.state import ChefState


@dataclass
class BaseAgentState:
    """Base internal state for agent workflows.

    This state is used within an agent's internal StateGraph to track
    progress through work/validation loops. It wraps the parent ChefState
    and adds agent-specific tracking fields.

    Attributes:
        chef_state: Reference to the parent migration state
        attempt: Current attempt number (0-indexed)
        max_attempts: Maximum number of attempts before giving up
        complete: Whether the agent has completed its work successfully
        last_result: Last result from agent execution (optional)
    """

    chef_state: ChefState
    attempt: int = 0
    max_attempts: int = 3
    complete: bool = False
    last_result: Any = None


@dataclass
class WriteAgentState(BaseAgentState):
    """Internal state for WriteAgent workflow.

    Tracks file creation progress through the checklist.

    Attributes:
        missing_files: List of file paths that haven't been created yet
    """

    missing_files: list[str] | None = None


@dataclass
class ValidationAgentState(BaseAgentState):
    """Internal state for ValidationAgent workflow.

    Tracks validation results and error fixing progress.

    Attributes:
        validation_results: Results from validation service (dict of validator results)
        error_report: Formatted error report for LLM
        has_errors: Whether validation found errors
    """

    validation_results: dict | None = None
    error_report: str = ""
    has_errors: bool = False


@dataclass
class PlanningAgentState(BaseAgentState):
    """Internal state for PlanningAgent workflow.

    Tracks checklist creation and validation.

    Attributes:
        checklist_valid: Whether the generated checklist is valid
    """

    checklist_valid: bool = False
