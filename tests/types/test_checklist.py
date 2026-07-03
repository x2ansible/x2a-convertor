"""Tests for checklist management system."""

import json
from enum import Enum

import pytest

from src.types.checklist import (
    SUMMARY_SUCCESS_MESSAGE,
    Checklist,
    ChecklistItem,
    ChecklistStats,
    ChecklistStatus,
)


class MockCategory(Enum):
    """Mock category enum for testing."""

    TEMPLATES = "templates"
    RECIPES = "recipes"
    ATTRIBUTES = "attributes"
    FILES = "files"

    def to_title(self):
        return f"### {self.value.title()}"


class TestChecklist:
    """Tests for checklist management system."""

    # ChecklistStatus enum tests
    def test_status_enum_values(self):
        """Test all status values are defined correctly."""
        assert ChecklistStatus.PENDING.value == "pending"
        assert ChecklistStatus.COMPLETE.value == "complete"
        assert ChecklistStatus.MISSING.value == "missing"
        assert ChecklistStatus.ERROR.value == "error"

    # ChecklistStats tests
    def test_stats_immutability(self):
        """Test that ChecklistStats is immutable."""
        stats = ChecklistStats(total=10, complete=5, pending=3, missing=1, error=1)
        with pytest.raises((AttributeError, TypeError)):
            stats.total = 20  # type: ignore[misc]

    def test_stats_to_markdown(self):
        """Test markdown conversion of stats."""
        stats = ChecklistStats(total=10, complete=5, pending=3, missing=1, error=1)
        markdown = stats.to_markdown()

        assert "**Total items:** 10" in markdown
        assert "**Completed:** 5" in markdown
        assert "**Pending:** 3" in markdown
        assert "**Missing:** 1" in markdown
        assert "**Errors:** 1" in markdown

    def test_item_creation_full(self):
        """Test creating item with all fields."""
        item = ChecklistItem(
            category="recipes",
            source_path="cookbooks/nginx/recipes/default.rb",
            target_path="ansible/roles/nginx/tasks/main.yml",
            status=ChecklistStatus.COMPLETE,
            description="Main nginx installation recipe",
            notes="Successfully migrated",
        )

        assert item.category == "recipes"
        assert item.status == ChecklistStatus.COMPLETE
        assert item.description == "Main nginx installation recipe"
        assert item.notes == "Successfully migrated"

    def test_item_target_exists_nonexistent_path(self):
        """Test target_exists returns False for non-existent paths."""
        item = ChecklistItem(
            category="templates",
            source_path="source.rb",
            target_path="/nonexistent/path/to/file.yml",
        )
        assert item.target_exists() is False

    def test_item_target_exists_existing_file(self, tmp_path):
        """Test target_exists returns True for existing file."""
        test_file = tmp_path / "test.yml"
        test_file.write_text("test content")

        item = ChecklistItem(
            category="templates",
            source_path="source.rb",
            target_path=str(test_file),
        )
        assert item.target_exists() is True

    # Checklist initialization tests
    def test_init_with_valid_category_enum(self):
        """Test initialization with valid category enum."""
        checklist = Checklist("test_module", MockCategory)

        assert checklist.module_name == "test_module"
        assert checklist.category_enum == MockCategory
        assert len(checklist) == 0

    def test_add_task_with_all_parameters(self):
        """Test adding task with all optional parameters."""
        checklist = Checklist("nginx", MockCategory)

        item = checklist.add_task(
            category="recipes",
            source_path="recipes/default.rb",
            target_path="ansible/roles/nginx/tasks/main.yml",
            description="Main recipe",
            status=ChecklistStatus.COMPLETE,
            notes="Migration successful",
        )

        assert item.status == ChecklistStatus.COMPLETE
        assert item.notes == "Migration successful"
        assert item.description == "Main recipe"

    def test_add_task_invalid_category(self):
        """Test adding task with invalid category raises ValueError."""
        checklist = Checklist("nginx", MockCategory)

        with pytest.raises(ValueError, match="Category 'invalid' not valid"):
            checklist.add_task(
                category="invalid",
                source_path="source.rb",
                target_path="target.yml",
            )

    def test_add_task_rejects_glob_patterns(self):
        """Test that glob patterns in target_path raise ValueError."""
        checklist = Checklist("nginx", MockCategory)

        with pytest.raises(ValueError, match="must be a concrete file path"):
            checklist.add_task(
                category="templates",
                source_path="source.rb",
                target_path="ansible/roles/nginx/templates/*.j2",
            )

        with pytest.raises(ValueError, match="must be a concrete file path"):
            checklist.add_task(
                category="templates",
                source_path="source.rb",
                target_path="ansible/roles/nginx/templates/file?.j2",
            )

        with pytest.raises(ValueError, match="must be a concrete file path"):
            checklist.add_task(
                category="templates",
                source_path="source.rb",
                target_path="ansible/roles/nginx/templates/file[0-9].j2",
            )

    def test_add_task_rejects_malformed_paths(self):
        """Test that malformed paths raise ValueError."""
        checklist = Checklist("nginx", MockCategory)

        with pytest.raises(ValueError, match="appears malformed or incomplete"):
            checklist.add_task(
                category="templates",
                source_path="source.rb",
                target_path="ansible/roles/nginx -> templates/file.j2",
            )

        with pytest.raises(ValueError, match="appears malformed or incomplete"):
            checklist.add_task(
                category="templates",
                source_path="source.rb",
                target_path="ansible/roles/nginx/templates/...",
            )

    def test_add_duplicate_task_returns_existing(self):
        """Test that adding duplicate task returns existing item."""
        checklist = Checklist("nginx", MockCategory)

        item1 = checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        item2 = checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        assert item1 == item2
        assert len(checklist) == 1

    def test_add_task_generates_default_description(self):
        """Test that default description is generated from paths."""
        checklist = Checklist("nginx", MockCategory)

        item = checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        assert item.description == "source.rb → target.yml"

    # update_task() tests
    def test_update_existing_task_status(self):
        """Test updating status of existing task."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        result = checklist.update_task(
            source_path="source.rb",
            target_path="target.yml",
            status=ChecklistStatus.COMPLETE,
        )

        assert result is True
        assert checklist.items[0].status == ChecklistStatus.COMPLETE

    def test_update_task_with_notes(self):
        """Test updating task with notes."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        checklist.update_task(
            source_path="source.rb",
            target_path="target.yml",
            status=ChecklistStatus.ERROR,
            notes="Migration failed due to syntax error",
        )

        assert checklist.items[0].status == ChecklistStatus.ERROR
        assert checklist.items[0].notes == "Migration failed due to syntax error"

    def test_update_nonexistent_task_returns_false(self):
        """Test updating non-existent task returns False."""
        checklist = Checklist("nginx", MockCategory)

        result = checklist.update_task(
            source_path="nonexistent.rb",
            target_path="nonexistent.yml",
            status=ChecklistStatus.COMPLETE,
        )

        assert result is False

    def test_update_task_with_string_status(self):
        """Test updating task with string status value."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        result = checklist.update_task(
            source_path="source.rb",
            target_path="target.yml",
            status="complete",
        )

        assert result is True
        assert checklist.items[0].status == ChecklistStatus.COMPLETE

    def test_update_task_with_invalid_status(self):
        """Test updating task with invalid status raises ValueError."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        with pytest.raises(ValueError, match="Invalid status"):
            checklist.update_task(
                source_path="source.rb",
                target_path="target.yml",
                status="invalid_status",
            )

    # find_task() tests
    def test_find_existing_task(self):
        """Test finding an existing task."""
        checklist = Checklist("nginx", MockCategory)
        added_item = checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        found_item = checklist.find_task("source.rb", "target.yml")

        assert found_item == added_item

    def test_find_nonexistent_task_returns_none(self):
        """Test finding non-existent task returns None."""
        checklist = Checklist("nginx", MockCategory)

        found_item = checklist.find_task("nonexistent.rb", "nonexistent.yml")

        assert found_item is None

    def test_find_task_normalizes_leading_dot_slash(self):
        """Test that find_task normalizes leading ./ in paths."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="target.yml",
        )

        found_item = checklist.find_task("source.rb", "./target.yml")

        assert found_item is not None

    def test_find_task_with_na_path(self):
        """Test finding task with N/A path."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            category="templates",
            source_path="source.rb",
            target_path="N/A",
        )

        found_item = checklist.find_task("source.rb", "N/A")

        assert found_item is not None

    # _normalize_path() tests
    def test_normalize_path_removes_leading_dot_slash(self):
        """Test normalization removes leading ./"""
        normalized = Checklist._normalize_path("./path/to/file.yml")
        assert normalized == "path/to/file.yml"

    def test_normalize_path_preserves_na(self):
        """Test normalization preserves N/A."""
        normalized = Checklist._normalize_path("N/A")
        assert normalized == "N/A"

    def test_get_stats_with_mixed_statuses(self):
        """Test stats calculation with various status types."""
        checklist = Checklist("nginx", MockCategory)

        checklist.add_task(
            "templates", "s1.rb", "t1.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task(
            "templates", "s2.rb", "t2.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task("recipes", "s3.rb", "t3.yml", status=ChecklistStatus.PENDING)
        checklist.add_task("recipes", "s4.rb", "t4.yml", status=ChecklistStatus.MISSING)
        checklist.add_task(
            "attributes", "s5.rb", "t5.yml", status=ChecklistStatus.ERROR
        )

        stats = checklist.get_stats()

        assert stats.total == 5
        assert stats.complete == 2
        assert stats.pending == 1
        assert stats.missing == 1
        assert stats.error == 1

    # is_complete() tests
    def test_is_complete_for_empty_checklist(self):
        """Test that empty checklist is not complete."""
        checklist = Checklist("nginx", MockCategory)
        assert checklist.is_complete() is False

    def test_is_complete_when_all_tasks_complete(self):
        """Test checklist is complete when all tasks are complete."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates", "s1.rb", "t1.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task(
            "templates", "s2.rb", "t2.yml", status=ChecklistStatus.COMPLETE
        )

        assert checklist.is_complete() is True

    def test_is_complete_with_mixed_statuses(self):
        """Test checklist is not complete with mixed statuses."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates", "s1.rb", "t1.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task(
            "templates", "s2.rb", "t2.yml", status=ChecklistStatus.PENDING
        )

        assert checklist.is_complete() is False

    # items property tests
    def test_items_returns_tuple(self):
        """Test that items property returns a tuple."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "s1.rb", "t1.yml")

        items = checklist.items

        assert isinstance(items, tuple)
        assert len(items) == 1

    def test_items_is_immutable(self):
        """Test that items tuple cannot be modified."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "s1.rb", "t1.yml")

        items = checklist.items

        with pytest.raises(TypeError):
            items[0] = None  # type: ignore[index]

    # items_by_category() tests
    def test_items_by_category_with_include(self):
        """Test filtering items by included categories."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "s1.rb", "t1.yml")
        checklist.add_task("recipes", "s2.rb", "t2.yml")
        checklist.add_task("attributes", "s3.rb", "t3.yml")

        items = checklist.items_by_category(include={"templates", "recipes"})

        assert len(items) == 2
        assert all(item.category in {"templates", "recipes"} for item in items)

    def test_items_by_category_with_exclude(self):
        """Test filtering items by excluded categories."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "s1.rb", "t1.yml")
        checklist.add_task("recipes", "s2.rb", "t2.yml")
        checklist.add_task("attributes", "s3.rb", "t3.yml")

        items = checklist.items_by_category(exclude={"attributes"})

        assert len(items) == 2
        assert all(item.category != "attributes" for item in items)

    def test_items_by_category_with_include_and_exclude(self):
        """Test filtering with both include and exclude."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "s1.rb", "t1.yml")
        checklist.add_task("recipes", "s2.rb", "t2.yml")
        checklist.add_task("attributes", "s3.rb", "t3.yml")
        checklist.add_task("files", "s4.rb", "t4.yml")

        items = checklist.items_by_category(
            include={"templates", "recipes", "attributes"}, exclude={"attributes"}
        )

        assert len(items) == 2
        assert all(item.category in {"templates", "recipes"} for item in items)

    def test_to_markdown_with_items(self):
        """Test markdown generation with items."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates",
            "templates/nginx.conf.erb",
            "ansible/roles/nginx/templates/nginx.conf.j2",
            status=ChecklistStatus.PENDING,
        )
        checklist.add_task(
            "recipes",
            "recipes/default.rb",
            "ansible/roles/nginx/tasks/main.yml",
            status=ChecklistStatus.COMPLETE,
        )

        markdown = checklist.to_markdown()

        assert "## Checklist: nginx" in markdown
        assert "### Templates" in markdown
        assert "### Recipes" in markdown
        assert "- [ ]" in markdown  # pending checkbox
        assert "- [x]" in markdown  # complete checkbox

    def test_to_markdown_with_notes(self):
        """Test markdown includes notes."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates",
            "source.rb",
            "target.yml",
            status=ChecklistStatus.ERROR,
            notes="Syntax error in template",
        )

        markdown = checklist.to_markdown()

        assert "Syntax error in template" in markdown

    def test_to_markdown_status_checkboxes(self):
        """Test correct checkbox symbols for different statuses."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates", "s1.rb", "t1.yml", status=ChecklistStatus.PENDING
        )
        checklist.add_task(
            "recipes", "s2.rb", "t2.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task(
            "attributes", "s3.rb", "t3.yml", status=ChecklistStatus.ERROR
        )
        checklist.add_task("files", "s4.rb", "t4.yml", status=ChecklistStatus.MISSING)

        markdown = checklist.to_markdown()

        assert "- [ ]" in markdown  # pending or missing
        assert "- [x]" in markdown  # complete
        assert "- [!]" in markdown  # error

    # _status_to_checkbox() tests
    def test_status_to_checkbox_complete(self):
        """Test checkbox for complete status."""
        checkbox = Checklist._status_to_checkbox(ChecklistStatus.COMPLETE)
        assert checkbox == "- [x]"

    def test_status_to_checkbox_error(self):
        """Test checkbox for error status."""
        checkbox = Checklist._status_to_checkbox(ChecklistStatus.ERROR)
        assert checkbox == "- [!]"

    def test_status_to_checkbox_pending(self):
        """Test checkbox for pending status."""
        checkbox = Checklist._status_to_checkbox(ChecklistStatus.PENDING)
        assert checkbox == "- [ ]"

    def test_status_to_checkbox_missing(self):
        """Test checkbox for missing status."""
        checkbox = Checklist._status_to_checkbox(ChecklistStatus.MISSING)
        assert checkbox == "- [ ]"

    # JSON serialization tests
    def test_to_dict(self):
        """Test conversion to dictionary."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "source.rb", "target.yml")

        data = checklist.to_dict()

        assert data["module_name"] == "nginx"
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["source_path"] == "source.rb"

    def test_to_json(self):
        """Test JSON serialization."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "source.rb", "target.yml")

        json_str = checklist.to_json()

        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["module_name"] == "nginx"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "module_name": "nginx",
            "items": [
                {
                    "category": "templates",
                    "source_path": "source.rb",
                    "target_path": "target.yml",
                    "status": "complete",
                    "description": "Test item",
                    "notes": "Test notes",
                }
            ],
        }

        checklist = Checklist.from_dict(data, MockCategory)

        assert checklist.module_name == "nginx"
        assert len(checklist) == 1
        assert checklist.items[0].status == ChecklistStatus.COMPLETE

    def test_from_dict_missing_module_name(self):
        """Test from_dict raises KeyError if module_name is missing."""
        data = {"items": []}

        with pytest.raises(KeyError, match="module_name"):
            Checklist.from_dict(data, MockCategory)

    def test_from_dict_missing_items(self):
        """Test from_dict raises KeyError if items is missing."""
        data = {"module_name": "nginx"}

        with pytest.raises(KeyError, match="items"):
            Checklist.from_dict(data, MockCategory)

    def test_from_dict_invalid_item_data(self):
        """Test from_dict raises ValueError for invalid item data."""
        data = {
            "module_name": "nginx",
            "items": [{"invalid": "data"}],
        }

        with pytest.raises(ValueError, match="Invalid checklist item data"):
            Checklist.from_dict(data, MockCategory)

    def test_from_json(self):
        """Test deserialization from JSON string."""
        json_str = """
        {
            "module_name": "nginx",
            "items": [
                {
                    "category": "templates",
                    "source_path": "source.rb",
                    "target_path": "target.yml",
                    "status": "pending",
                    "description": "",
                    "notes": ""
                }
            ]
        }
        """

        checklist = Checklist.from_json(json_str, MockCategory)

        assert checklist.module_name == "nginx"
        assert len(checklist) == 1

    def test_roundtrip_serialization(self):
        """Test that serialization and deserialization are reversible."""
        original = Checklist("nginx", MockCategory)
        original.add_task(
            "templates", "source.rb", "target.yml", status=ChecklistStatus.COMPLETE
        )
        original.add_task("recipes", "recipe.rb", "task.yml", notes="Test note")

        json_str = original.to_json()
        restored = Checklist.from_json(json_str, MockCategory)

        assert restored.module_name == original.module_name
        assert len(restored) == len(original)
        assert restored.items[0].status == ChecklistStatus.COMPLETE
        assert restored.items[1].notes == "Test note"

    # File I/O tests
    def test_save_creates_file(self, tmp_path):
        """Test that save creates a file."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "source.rb", "target.yml")

        filepath = tmp_path / "checklist.json"
        checklist.save(filepath)

        assert filepath.exists()

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test that save and load work together."""
        original = Checklist("nginx", MockCategory)
        original.add_task(
            "templates", "source.rb", "target.yml", status=ChecklistStatus.COMPLETE
        )

        filepath = tmp_path / "checklist.json"
        original.save(filepath)

        loaded = Checklist.load(filepath, MockCategory)

        assert loaded.module_name == original.module_name
        assert len(loaded) == len(original)
        assert loaded.items[0].status == ChecklistStatus.COMPLETE

    def test_load_nonexistent_file_raises_error(self, tmp_path):
        """Test that loading non-existent file raises FileNotFoundError."""
        filepath = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            Checklist.load(filepath, MockCategory)

    def test_str_returns_markdown(self):
        """Test that __str__ returns markdown format."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "source.rb", "target.yml")

        str_output = str(checklist)
        markdown_output = checklist.to_markdown()

        assert str_output == markdown_output

    # LangChain tools tests
    def test_get_tools_returns_list(self):
        """Test that get_tools returns a list of tools."""
        checklist = Checklist("nginx", MockCategory)
        tools = checklist.get_tools()

        assert isinstance(tools, list)
        assert len(tools) == 4

    def test_get_tools_names(self):
        """Test that tools have expected names."""
        checklist = Checklist("nginx", MockCategory)
        tools = checklist.get_tools()

        tool_names = [tool.name for tool in tools]

        assert "add_checklist_task" in tool_names
        assert "update_checklist_task" in tool_names
        assert "list_checklist_tasks" in tool_names
        assert "get_checklist_summary" in tool_names

    def test_add_task_tool_success(self):
        """Test add_checklist_task tool with valid input."""
        checklist = Checklist("nginx", MockCategory)
        tools = checklist.get_tools()
        add_tool = next(t for t in tools if t.name == "add_checklist_task")

        result = add_tool.invoke(
            {
                "category": "templates",
                "source_path": "source.rb",
                "target_path": "target.yml",
                "status": "pending",
            }
        )

        assert "Added task" in result
        assert len(checklist) == 1

    def test_add_task_tool_error(self):
        """Test add_checklist_task tool with invalid category."""
        checklist = Checklist("nginx", MockCategory)
        tools = checklist.get_tools()
        add_tool = next(t for t in tools if t.name == "add_checklist_task")

        result = add_tool.invoke(
            {
                "category": "invalid",
                "source_path": "source.rb",
                "target_path": "target.yml",
            }
        )

        assert "Error adding task" in result

    def test_update_task_tool_success(self):
        """Test update_checklist_task tool with existing task."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "source.rb", "target.yml")

        tools = checklist.get_tools()
        update_tool = next(t for t in tools if t.name == "update_checklist_task")

        result = update_tool.invoke(
            {
                "source_path": "source.rb",
                "target_path": "target.yml",
                "status": "complete",
            }
        )

        assert "Updated task" in result
        assert checklist.items[0].status == ChecklistStatus.COMPLETE

    def test_update_task_tool_not_found(self):
        """Test update_checklist_task tool with non-existent task."""
        checklist = Checklist("nginx", MockCategory)
        tools = checklist.get_tools()
        update_tool = next(t for t in tools if t.name == "update_checklist_task")

        result = update_tool.invoke(
            {
                "source_path": "nonexistent.rb",
                "target_path": "nonexistent.yml",
                "status": "complete",
            }
        )

        assert "Task not found" in result

    def test_list_tasks_tool_empty(self):
        """Test list_checklist_tasks tool with empty checklist."""
        checklist = Checklist("nginx", MockCategory)
        tools = checklist.get_tools()
        list_tool = next(t for t in tools if t.name == "list_checklist_tasks")

        result = list_tool.invoke({})

        assert "Checklist is empty" in result

    def test_list_tasks_tool_with_items(self):
        """Test list_checklist_tasks tool with items."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task("templates", "source.rb", "target.yml")

        tools = checklist.get_tools()
        list_tool = next(t for t in tools if t.name == "list_checklist_tasks")

        result = list_tool.invoke({})

        assert "## Checklist" in result
        assert "source.rb" in result

    def test_checklist_summary_tool_complete(self):
        """Test get_checklist_summary tool when all tasks complete."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates", "s1.rb", "t1.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task(
            "templates", "s2.rb", "t2.yml", status=ChecklistStatus.COMPLETE
        )

        tools = checklist.get_tools()
        summary_tool = next(t for t in tools if t.name == "get_checklist_summary")

        result = summary_tool.invoke({})

        assert result == SUMMARY_SUCCESS_MESSAGE

    def test_checklist_summary_tool_incomplete(self):
        """Test get_checklist_summary tool when tasks incomplete."""
        checklist = Checklist("nginx", MockCategory)
        checklist.add_task(
            "templates", "s1.rb", "t1.yml", status=ChecklistStatus.COMPLETE
        )
        checklist.add_task(
            "templates", "s2.rb", "t2.yml", status=ChecklistStatus.PENDING
        )

        tools = checklist.get_tools()
        summary_tool = next(t for t in tools if t.name == "get_checklist_summary")

        result = summary_tool.invoke({})

        assert "2 items" in result
        assert "1 complete" in result
        assert "1 pending" in result

    # Module constant test
    def test_summary_success_message_constant(self):
        """Test that SUMMARY_SUCCESS_MESSAGE is defined."""
        assert (
            SUMMARY_SUCCESS_MESSAGE
            == "All migration tasks have been completed successfully"
        )
