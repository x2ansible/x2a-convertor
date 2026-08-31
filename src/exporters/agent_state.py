"""Internal state classes for agent workflows.

These states are used within agents' internal StateGraphs to manage
their work/validation loops independently from the parent workflow.
"""

from dataclasses import dataclass
from typing import Any

from src.exporters.state import ExportState
from src.exporters.tools.apme import CheckReport


@dataclass
class BaseAgentState:
    """Base internal state for agent workflows.

    This state is used within an agent's internal StateGraph to track
    progress through work/validation loops. It wraps the parent ExportState
    and adds agent-specific tracking fields.

    Attributes:
        export_state: Reference to the parent migration state
        attempt: Current attempt number (0-indexed)
        max_attempts: Maximum number of attempts before giving up
        complete: Whether the agent has completed its work successfully
        last_result: Last result from agent execution (optional)
    """

    export_state: ExportState
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
        validation_report: Latest APME CheckReport (rule violations). Use
            ``validation_report.to_xml_prompt()`` to render it for an LLM
            prompt rather than caching a separate string -- the CheckReport
            is the single source of truth for both the violations and their
            rendering.
        previous_validation_report: Previous APME CheckReport, for stall
            detection via ``ErrorFingerprint``.
        has_errors: Whether validation found errors
    """

    validation_report: CheckReport | None = None
    previous_validation_report: CheckReport | None = None
    has_errors: bool = False

    def render_errors(self) -> str:
        """Render the current validation_report as XML for prompts/logs.

        Returns an empty-results XML stub if no check has run yet.
        """
        if self.validation_report is None:
            return CheckReport().to_xml_prompt()
        return self.validation_report.to_xml_prompt()


@dataclass
class MoleculeAgentState(BaseAgentState):
    """Internal state for MoleculeAgent workflow.

    Tracks molecule test file creation progress.

    Attributes:
        missing_files: List of molecule file paths that haven't been created yet
    """

    missing_files: list[str] | None = None


@dataclass
class PlanningAgentState(BaseAgentState):
    """Internal state for PlanningAgent workflow.

    Tracks checklist creation and validation.

    Attributes:
        checklist_valid: Whether the generated checklist is valid
    """

    checklist_valid: bool = False
