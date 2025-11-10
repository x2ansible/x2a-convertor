"""Migration checklist management system"""

import json
from enum import Enum
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

__all__ = [
    "SUMMARY_SUCCESS_MESSAGE",
    "Checklist",
    "ChecklistItem",
    "ChecklistStatus",
]

SUMMARY_SUCCESS_MESSAGE = "All migration tasks have been completed successfully"


class ChecklistStatus(str, Enum):
    """Status of individual checklist items"""

    PENDING = "pending"
    COMPLETE = "complete"
    MISSING = "missing"
    ERROR = "error"


class ChecklistItem(BaseModel):
    """Individual item in the checklist (Pydantic model for validation)"""

    category: str = Field(description="Category of the item")
    source_path: str = Field(description="Source file path")
    target_path: str = Field(description="Target file path")
    status: ChecklistStatus = Field(
        default=ChecklistStatus.PENDING, description="Current status"
    )
    description: str = Field(default="", description="Human-readable description")
    notes: str = Field(
        default="",
        description="Error messages, validation notes, or additional info",
    )

    def target_exists(self) -> bool:
        """Check if the target file exists on the filesystem

        Returns:
            True if target_path exists as a file, False otherwise
        """
        return Path(self.target_path).is_file()


class Checklist:
    """Encapsulates checklist with methods for manipulation and persistence

    Generic checklist implementation that accepts category enum as dependency injection.
    """

    def __init__(
        self,
        module_name: str,
        category_enum: type[Enum],
    ):
        """Initialize checklist with injected category configuration

        Args:
            module_name: Name of the module being tracked
            category_enum: Enum class defining valid categories (must have to_title() method)
        """
        self.module_name = module_name
        self.category_enum = category_enum
        self._items: list[ChecklistItem] = []

    # ============================================================================
    # Task Management Methods
    # ============================================================================

    def add_task(
        self,
        category: str,
        source_path: str,
        target_path: str,
        description: str = "",
        status: str = ChecklistStatus.PENDING,
        notes: str = "",
    ) -> ChecklistItem:
        """Add a new task to the checklist

        Args:
            category: Category value (must match injected category_enum)
            source_path: Source file path
            target_path: Target file path
            description: Optional description
            status: Task status
            notes: Optional notes

        Returns:
            The created item

        Raises:
            ValueError: If category is not valid for the injected enum
        """
        # Check if task already exists
        existing_item = self.find_task(source_path, target_path)
        if existing_item:
            logger.warning(
                f"Task already exists: {source_path} → {target_path}, skipping add"
            )
            return existing_item

        # Validate category against injected enum
        valid_categories = [cat.value for cat in self.category_enum]
        if category not in valid_categories:
            raise ValueError(
                f"Category '{category}' not valid. Must be one of {valid_categories}"
            )

        item = ChecklistItem(
            category=category,
            source_path=source_path,
            target_path=target_path,
            status=status,
            description=description or f"{source_path} → {target_path}",
            notes=notes,
        )
        self._items.append(item)
        logger.debug(f"Added task: {source_path} → {target_path} ({status})")
        return item

    def update_task(
        self,
        source_path: str,
        target_path: str,
        status: ChecklistStatus | str,
        notes: str = "",
    ) -> bool:
        """Update status of an existing task

        Args:
            source_path: Chef source file path
            target_path: Ansible target file path
            status: New status
            notes: Optional notes to add/update

        Returns:
            True if task was found and updated, False otherwise

        Raises:
            ValueError: If status is not a valid ChecklistStatus value
        """
        # Normalize status to ChecklistStatus enum
        if isinstance(status, str):
            try:
                status_enum = ChecklistStatus(status)
            except ValueError as e:
                valid = [s.value for s in ChecklistStatus]
                raise ValueError(f"Invalid status '{status}'. Must be one of: {valid}") from e
        else:
            status_enum = status

        for item in self._items:
            if item.source_path == source_path and item.target_path == target_path:
                item.status = status_enum
                if notes:
                    item.notes = notes
                logger.debug(
                    f"Updated task: {source_path} → {target_path} to {status_enum.value}"
                )
                return True

        logger.warning(f"Task not found: {source_path} → {target_path}")
        return False

    def find_task(self, source_path: str, target_path: str) -> ChecklistItem | None:
        """Find a specific task by source and target paths

        Returns:
            The task item if found, None otherwise
        """
        for item in self._items:
            if item.source_path == source_path and item.target_path == target_path:
                return item
        return None

    # ============================================================================
    # Query Methods
    # ============================================================================

    def get_stats(self) -> dict[str, int]:
        """Get statistics about checklist completion"""
        stats = {
            "total": len(self._items),
            "complete": 0,
            "pending": 0,
            "missing": 0,
            "error": 0,
        }

        for item in self._items:
            if item.status == ChecklistStatus.COMPLETE:
                stats["complete"] += 1
            elif item.status == ChecklistStatus.PENDING:
                stats["pending"] += 1
            elif item.status == ChecklistStatus.MISSING:
                stats["missing"] += 1
            elif item.status == ChecklistStatus.ERROR:
                stats["error"] += 1

        return stats

    def is_complete(self) -> bool:
        """Check if all checklist items are complete"""
        stats = self.get_stats()
        return stats["complete"] == stats["total"] and stats["total"] > 0

    @property
    def items(self) -> tuple[ChecklistItem, ...]:
        """Get all checklist items (immutable view)"""
        return tuple(self._items)

    def __len__(self) -> int:
        """Return number of items in checklist"""
        return len(self._items)

    # ============================================================================
    # Markdown Serialization (for LLM interaction)
    # ============================================================================

    def to_markdown(self) -> str:
        """Convert checklist to markdown format for LLM prompts"""
        if not self._items:
            return ""

        # Group by category
        by_category: dict[str, list[ChecklistItem]] = {}
        for item in self._items:
            category = item.category
            if category not in by_category:
                by_category[category] = []
            by_category[category].append(item)

        # Render markdown
        lines = [f"## Checklist: {self.module_name}\n"]

        # Iterate through injected category enum
        for category in self.category_enum:
            if category.value not in by_category:
                continue

            # Use category's to_title() method or generate default
            if hasattr(category, "to_title"):
                title = category.to_title()
            else:
                title = f"### {category.value.title()}"
            lines.append(title)

            for item in by_category[category.value]:
                checkbox = self._status_to_checkbox(item.status)
                notes_text = f" - {item.notes}" if item.notes else ""
                lines.append(
                    f"{checkbox} {item.source_path} → {item.target_path} ({item.status.value}){notes_text}"
                )

            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _status_to_checkbox(status: ChecklistStatus) -> str:
        """Convert status to markdown checkbox"""
        if status == ChecklistStatus.COMPLETE:
            return "- [x]"
        elif status == ChecklistStatus.ERROR:
            return "- [!]"
        else:
            return "- [ ]"

    # ============================================================================
    # JSON Serialization (for persistence)
    # ============================================================================

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "module_name": self.module_name,
            "items": [item.model_dump() for item in self._items],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        category_enum: type[Enum],
    ) -> "Checklist":
        """Create checklist from dictionary

        Args:
            data: Dictionary with checklist data
            category_enum: Enum class defining valid categories

        Raises:
            KeyError: If required keys are missing
            ValueError: If data format is invalid
        """
        if "module_name" not in data:
            raise KeyError("Missing required key 'module_name' in checklist data")
        if "items" not in data:
            raise KeyError("Missing required key 'items' in checklist data")

        checklist = cls(data["module_name"], category_enum)
        try:
            checklist._items = [
                ChecklistItem(**item_data) for item_data in data["items"]
            ]
        except (TypeError, ValueError) as e:
            raise ValueError(f"Invalid checklist item data: {e}") from e

        return checklist

    @classmethod
    def from_json(
        cls,
        json_str: str,
        category_enum: type[Enum],
    ) -> "Checklist":
        """Deserialize from JSON string

        Args:
            json_str: JSON string to deserialize
            category_enum: Enum class defining valid categories
        """
        data = json.loads(json_str)
        return cls.from_dict(data, category_enum)

    # ============================================================================
    # File I/O Methods
    # ============================================================================

    def save(self, filepath: str | Path) -> None:
        """Save checklist to JSON file

        Args:
            filepath: Path where to save the checklist

        Raises:
            OSError: If file cannot be written
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_json())

        logger.info(f"Saved checklist to {filepath}")

    @classmethod
    def load(
        cls,
        filepath: str | Path,
        category_enum: type[Enum],
    ) -> "Checklist":
        """Load checklist from JSON file

        Args:
            filepath: Path to the checklist JSON file
            category_enum: Enum class defining valid categories

        Returns:
            Loaded Checklist instance

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file contains invalid JSON
            OSError: If file cannot be read
        """
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"Checklist file not found: {filepath}")

        with open(filepath, encoding="utf-8") as f:
            content = f.read()
            checklist = cls.from_json(content, category_enum)

        logger.info(f"Loaded checklist from {filepath} ({len(checklist)} items)")
        return checklist

    # ============================================================================
    # String representation
    # ============================================================================

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"Checklist(module='{self.module_name}', "
            f"total={stats['total']}, complete={stats['complete']}, "
            f"pending={stats['pending']}, missing={stats['missing']}, "
            f"error={stats['error']})"
        )

    def __str__(self) -> str:
        return self.to_markdown()

    # ============================================================================
    # LangChain Tool Integration
    # ============================================================================

    def get_tools(self) -> list:
        """Return LangChain tools for checklist operations

        Returns:
            List of LangChain tool instances bound to this checklist
        """

        @tool("add_checklist_task")
        def add_task_tool(
            category: str,
            source_path: str,
            target_path: str,
            description: str = "",
            status: str = "pending",
            notes: str = "",
        ) -> str:
            """Add a new task to the migration checklist.

            Args:
                category: Category of the task (e.g., 'templates', 'recipes', 'attributes')
                source_path: Source file path in Chef
                target_path: Target file path in Ansible
                description: Optional description of the task
                status: Task status (pending, complete, missing, error)
                notes: Optional notes about the task

            Returns:
                Success message with task details
            """
            try:
                self.add_task(
                    category=category,
                    source_path=source_path,
                    target_path=target_path,
                    description=description,
                    status=status,
                    notes=notes,
                )
                return f"Added task: {source_path} → {target_path} ({status})"
            except Exception as e:
                return f"Error adding task: {e!s}"

        @tool("update_checklist_task")
        def update_task_tool(
            source_path: str, target_path: str, status: str, notes: str = ""
        ) -> str:
            """Update the status of an existing checklist task.

            Args:
                source_path: Source file path in Chef
                target_path: Target file path in Ansible
                status: New status (pending, complete, missing, error)
                notes: Optional notes to add/update

            Returns:
                Success or failure message
            """
            try:
                success = self.update_task(source_path, target_path, status, notes)
                if success:
                    return f"Updated task: {source_path} → {target_path} to {status}"
                return f"Task not found: {source_path} → {target_path}"
            except Exception as e:
                return f"Error updating task: {e!s}"

        @tool("list_checklist_tasks")
        def list_tasks_tool() -> str:
            """List all tasks in the checklist.

            Returns:
                Markdown formatted list of all checklist tasks
            """
            try:
                if not self.items:
                    return "Checklist is empty - no tasks have been added yet."

                return self.to_markdown()
            except Exception as e:
                return f"Error listing tasks: {e!s}"

        @tool("get_checklist_summary")
        def checklist_summary_tool() -> str:
            """Get the summary of the checklist for the final report"""
            stats = self.get_stats()
            if stats["total"] == stats["complete"]:
                return SUMMARY_SUCCESS_MESSAGE

            return f"Checklist summary: {stats['total']} items, {stats['complete']} complete, {stats['pending']} pending, {stats['missing']} missing, {stats['error']} error"

        return [
            add_task_tool,
            update_task_tool,
            list_tasks_tool,
            checklist_summary_tool,
        ]
