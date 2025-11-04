"""State management for Chef to Ansible migration workflow.

This module defines the state object that tracks the migration process
through its various phases.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from src.types import AnsibleModule, Checklist, DocumentFile, MigrationStateInterface


# Constants
ANSIBLE_PATH_TEMPLATE = "ansible/{module}"
CHECKLIST_FILENAME = ".checklist.json"


@dataclass
class ChefState(MigrationStateInterface):
    """State object for tracking Chef to Ansible migration workflow.

    This is the aggregate root for the migration domain in DDD terms.
    All domain state flows through this object, making agents stateless
    and ensuring proper separation of concerns.

    This state is passed through the LangGraph workflow and tracks:
    - Source Chef module information
    - Migration plans and documentation
    - Workflow phase and attempt counters
    - Validation reports and outputs
    - Migration checklist (domain state)
    - Failure state and reason

    Attributes:
        path: Path to the Chef cookbook/module
        module: AnsibleModule value object representing the module being migrated
        user_message: Original user message/requirements
        module_migration_plan: Detailed migration plan document
        high_level_migration_plan: High-level migration strategy document
        directory_listing: List of files in the source directory
        current_phase: Current phase of the migration workflow
        write_attempt_counter: Number of write attempts made
        validation_attempt_counter: Number of validation attempts made
        validation_report: Latest validation report
        last_output: Last output from the workflow
        checklist: Migration checklist tracking file transformations
        failed: Whether the migration has failed
        failure_reason: Human-readable reason for failure
    """

    path: str
    module: AnsibleModule
    user_message: str
    module_migration_plan: DocumentFile
    high_level_migration_plan: DocumentFile
    directory_listing: list[str]
    current_phase: str
    write_attempt_counter: int
    validation_attempt_counter: int
    validation_report: str
    last_output: str
    checklist: Optional[Checklist] = None
    failed: bool = False
    failure_reason: str = ""

    def get_ansible_path(self) -> str:
        """Get the Ansible output path for this module.

        Returns:
            Path string in format ansible/{module}
        """
        return ANSIBLE_PATH_TEMPLATE.format(module=str(self.module))

    def get_checklist_path(self) -> Path:
        """Get the path to the checklist JSON file.

        Returns:
            Path object pointing to the checklist file
        """
        return Path(self.get_ansible_path()) / CHECKLIST_FILENAME

    def update(self, **kwargs) -> "ChefState":
        """Create a new ChefState instance with updated fields.

        This helper method provides immutable state updates using dataclasses.replace(),
        making state transformations more functional and explicit.

        Args:
            **kwargs: Fields to update (must be valid ChefState attributes)

        Returns:
            New ChefState instance with updated fields

        Example:
            new_state = state.update(checklist=new_checklist, current_phase="writing")
        """
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "ChefState":
        """Mark this migration as failed with a reason.

        This is a convenience method for agents to signal failure in a clean way.
        The parent workflow can check state.failed to decide whether to continue.

        Args:
            reason: Human-readable failure reason

        Returns:
            New ChefState with failed=True and failure_reason set

        Example:
            return state.mark_failed("Failed to create 5 files after 3 attempts")
        """
        return self.update(failed=True, failure_reason=reason)

    def did_fail(self) -> bool:
        """Check if the migration failed.

        Returns:
            True if migration failed, False otherwise
        """
        return self.failed

    def get_failure_reason(self) -> str:
        """Get the reason for migration failure.

        Returns:
            Human-readable failure reason string, empty if not failed
        """
        return self.failure_reason

    def get_output(self) -> str:
        """Get the final migration output/summary.

        Returns:
            Migration output string (success or failure summary)
        """
        return self.last_output
