"""LangChain tools for interacting with migration checklists"""

import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.types import Checklist, ChecklistStatus

logger = logging.getLogger(__name__)

# Constants
MAX_INCOMPLETE_ITEMS_DISPLAY = 5


class AddChecklistTaskInput(BaseModel):
    """Input schema for adding a new checklist task."""

    category: str = Field(
        description="Category of the migration task. Must be one of: 'templates', 'recipes', 'attributes', 'files', 'structure'"
    )
    source_path: str = Field(
        description="Chef source file path (e.g., 'templates/default/nginx.conf.erb') or 'N/A' for generated files"
    )
    target_path: str = Field(
        description="Ansible target file path (e.g., 'templates/nginx.conf.j2')"
    )
    description: str = Field(
        default="",
        description="Optional description of what this task does",
    )


class UpdateChecklistTaskInput(BaseModel):
    """Input schema for updating a checklist task."""

    source_path: str = Field(
        description="Chef source file path (e.g., 'templates/default/nginx.conf.erb')"
    )
    target_path: str = Field(
        description="Ansible target file path (e.g., 'templates/nginx.conf.j2')"
    )
    status: str = Field(
        description="New status for the task. Must be one of: 'complete', 'pending', 'missing', 'error'"
    )
    notes: str = Field(
        default="",
        description="Optional notes about the status (e.g., error messages, validation notes)",
    )


class GetChecklistSummaryInput(BaseModel):
    """Input schema for getting checklist summary (no parameters needed)."""

    pass


class ChecklistAddTaskTool(BaseTool):
    """Tool for adding new tasks to the migration checklist."""

    name: str = "add_checklist_task"
    description: str = (
        "Add a new migration task to the checklist. "
        "Use this when planning a migration to record all files that need conversion. "
        "All tasks start with 'pending' status by default."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = AddChecklistTaskInput

    # Injected dependencies
    checklist: Checklist
    checklist_path: Path

    # pyrefly: ignore
    def _run(
        self, category: str, source_path: str, target_path: str, description: str = ""
    ) -> str:
        """Add a new task to the checklist"""
        try:
            self.checklist.add_task(
                category=category,
                source_path=source_path,
                target_path=target_path,
                description=description or f"{source_path} → {target_path}",
                status=ChecklistStatus.PENDING,
            )

            self.checklist.save(self.checklist_path)
            logger.info(f"Added task: {source_path} → {target_path} ({category})")

            return f"SUCCESS: Added {source_path} → {target_path} ({category})"

        except ValueError as e:
            logger.warning(f"Validation error adding task: {e}")
            return f"ERROR: {e}"
        except OSError as e:
            logger.error(f"Failed to save checklist: {e}")
            return f"ERROR: Failed to save checklist: {e}"


class ChecklistUpdateTool(BaseTool):
    """Tool for updating migration checklist task status."""

    name: str = "update_checklist_task"
    description: str = (
        "Update the status of a migration checklist task. "
        "Use this to mark tasks as 'complete' when successfully migrated, "
        "'error' when issues occur, or 'missing' when files don't exist. "
        "You must provide the exact source_path and target_path from the checklist."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = UpdateChecklistTaskInput

    # Injected dependencies
    checklist: Checklist
    checklist_path: Path

    # pyrefly: ignore
    def _run(
        self, source_path: str, target_path: str, status: str, notes: str = ""
    ) -> str:
        """Update task status in the checklist"""
        try:
            success = self.checklist.update_task(
                source_path, target_path, status, notes
            )

            if not success:
                return (
                    f"ERROR: Task not found: {source_path} → {target_path}\n"
                    f"Verify that source_path and target_path match exactly"
                )

            self.checklist.save(self.checklist_path)
            logger.info(f"Updated task: {source_path} → {target_path} to {status}")

            notes_text = f" - {notes}" if notes else ""
            return f"SUCCESS: Updated {source_path} → {target_path} to '{status}'{notes_text}"

        except ValueError as e:
            logger.warning(f"Validation error updating task: {e}")
            return f"ERROR: {e}"
        except OSError as e:
            logger.error(f"Failed to save checklist: {e}")
            return f"ERROR: Failed to save checklist: {e}"


class ChecklistSummaryTool(BaseTool):
    """Tool for getting current checklist summary and statistics."""

    name: str = "get_checklist_summary"
    description: str = (
        "Get current migration checklist summary with statistics. "
        "Shows total tasks, completed tasks, pending tasks, missing tasks, and errors. "
        "Use this to check overall migration progress."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = GetChecklistSummaryInput

    # Injected dependencies
    checklist: Checklist

    # pyrefly: ignore
    def _run(self) -> str:
        """Get checklist summary and statistics"""
        try:
            stats = self.checklist.get_stats()

            total = stats["total"]
            complete = stats["complete"]
            percentage = (complete / total * 100) if total > 0 else 0

            summary = [
                f"## Checklist Summary: {self.checklist.module_name}",
                "",
                f"**Progress**: {complete}/{total} tasks completed ({percentage:.1f}%)",
                "",
                "**Statistics**:",
                f"- Complete: {stats['complete']}",
                f"- Pending: {stats['pending']}",
                f"- Missing: {stats['missing']}",
                f"- Error: {stats['error']}",
                f"- Total: {stats['total']}",
            ]

            # Add incomplete items if any
            if not self.checklist.is_complete():
                summary.append("")
                summary.append("**Incomplete Items**:")

                for status_type in [
                    ChecklistStatus.ERROR,
                    ChecklistStatus.MISSING,
                    ChecklistStatus.PENDING,
                ]:
                    items = self.checklist.get_items_by_status(status_type.value)
                    if items:
                        summary.append(f"\n{status_type.value.title()}:")
                        for item in items[:MAX_INCOMPLETE_ITEMS_DISPLAY]:
                            summary.append(
                                f"  - {item.source_path} → {item.target_path}"
                            )
                        if len(items) > MAX_INCOMPLETE_ITEMS_DISPLAY:
                            summary.append(
                                f"  ... and {len(items) - MAX_INCOMPLETE_ITEMS_DISPLAY} more"
                            )

            return "\n".join(summary)

        except Exception as e:
            logger.error(f"Failed to get checklist summary: {e}")
            return f"ERROR: Failed to get summary: {e}"


def create_checklist_tools(
    checklist: Checklist, checklist_path: str | Path, include_add: bool = False
) -> list[BaseTool]:
    """Create checklist tools with injected dependencies

    Args:
        checklist: The Checklist instance to use
        checklist_path: Path where checklist JSON is stored
        include_add: If True, include add_checklist_task tool (for planning phase)

    Returns:
        List of BaseTool instances for LangChain agents
    """
    checklist_path = Path(checklist_path)

    tools: list[BaseTool] = [
        ChecklistUpdateTool(checklist=checklist, checklist_path=checklist_path),
        ChecklistSummaryTool(checklist=checklist),
    ]

    if include_add:
        tools.insert(
            0, ChecklistAddTaskTool(checklist=checklist, checklist_path=checklist_path)
        )

    return tools
