"""State management for analyze workflow.

This module defines the state object and structured output models
for the analyze phase, following the pattern from src/exporters/state.py.
"""

from dataclasses import dataclass, field, replace

from pydantic import BaseModel

from src.const import MODULE_MIGRATION_PLAN_TEMPLATE
from src.types import BaseState
from src.utils.technology import Technology


class ModuleSelection(BaseModel):
    """Structured output for module selection."""

    name: str
    path: str
    technology: str = "Chef"


@dataclass
class MigrationState(BaseState):
    """State for analyze phase workflow.

    Inherits from BaseState for common fields (user_message, path, telemetry,
    failed, failure_reason).

    Analyze-specific attributes:
        name: Module/cookbook name selected for analysis
        technology: Source technology (Chef, Puppet, Salt)
        migration_plan_content: Content of high-level migration plan
        module_migration_plan: Generated module-specific migration plan
        module_plan_path: Path where module plan was written
    """

    # Fields inherited from BaseState:
    # - user_message: str
    # - path: str
    # - telemetry: Telemetry | None (kw_only)
    # - failed: bool (kw_only)
    # - failure_reason: str (kw_only)

    name: str = field(kw_only=True)
    technology: Technology | None = field(kw_only=True)
    migration_plan_content: str = field(kw_only=True)
    module_migration_plan: str = field(kw_only=True)
    module_plan_path: str = field(kw_only=True)

    def get_migration_plan_path(self) -> str:
        if self.name:
            tokenized_name = self.name.replace(" ", "_")
            return MODULE_MIGRATION_PLAN_TEMPLATE.format(module=tokenized_name)

        module = self.path.split("/")[-1] if self.path else "unknown"
        return MODULE_MIGRATION_PLAN_TEMPLATE.format(module=module)

    def update(self, **kwargs) -> "MigrationState":
        """Create new MigrationState with updated fields (immutable pattern).

        Args:
            **kwargs: Fields to update (must be valid MigrationState attributes)

        Returns:
            New MigrationState instance with updated fields
        """
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> "MigrationState":
        """Mark this operation as failed with a reason.

        Args:
            reason: Human-readable failure reason

        Returns:
            New MigrationState with failed=True and failure_reason set
        """
        return self.update(failed=True, failure_reason=reason)
