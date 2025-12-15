"""Test cases for analyze.py MigrationState."""

from src.inputs.analyze import MigrationState
from src.utils.technology import Technology


class TestMigrationStateGetMigrationPlanPath:
    """Test cases for MigrationState.get_migration_plan_path method."""

    def test_with_name_set(self) -> None:
        """Test that name takes precedence when set."""
        state = MigrationState(
            user_message="test message",
            path="/some/path/module",
            name="my_module",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-my_module.md"

    def test_with_empty_name_uses_path(self) -> None:
        """Test that path is used when name is empty."""
        state = MigrationState(
            user_message="test message",
            path="/some/path/nginx",
            name="",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-nginx.md"

    def test_with_relative_path(self) -> None:
        """Test with relative path."""
        state = MigrationState(
            user_message="test message",
            path="./cookbooks/apache",
            name="",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-apache.md"

    def test_with_simple_path(self) -> None:
        """Test with simple path without slashes."""
        state = MigrationState(
            user_message="test message",
            path="mymodule",
            name="",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-mymodule.md"

    def test_with_empty_path(self) -> None:
        """Test with empty path defaults to 'unknown'."""
        state = MigrationState(
            user_message="test message",
            path="",
            name="",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-unknown.md"

    def test_name_priority_over_path(self) -> None:
        """Test that name takes priority even when path is set."""
        state = MigrationState(
            user_message="test message",
            path="/different/path/other_module",
            name="override_name",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-override_name.md"
        assert "other_module" not in result

    def test_with_trailing_slash_in_path(self) -> None:
        """Test path with trailing slash extracts correct module name.

        Note: Current implementation has a bug where trailing slashes result in
        empty module name. The path.split('/')[-1] returns '' for '/path/'.
        This test documents the current behavior.
        """
        state = MigrationState(
            user_message="test message",
            path="/cookbooks/mysql/",
            name="",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        # Current behavior: trailing slash causes empty module name
        assert result == "migration-plan-.md"

    def test_with_complex_module_name(self) -> None:
        """Test with complex module name containing special characters."""
        state = MigrationState(
            user_message="test message",
            path="/path/to/my-complex_module.v2",
            name="",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-my-complex_module.v2.md"

    def test_name_with_spaces(self) -> None:
        """Test name with spaces is tokenized with underscores."""
        state = MigrationState(
            user_message="test message",
            path="/some/path",
            name="my module name",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-my_module_name.md"

    def test_name_with_multiple_spaces(self) -> None:
        """Test name with multiple consecutive spaces."""
        state = MigrationState(
            user_message="test message",
            path="/some/path",
            name="my  module   name",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-my__module___name.md"

    def test_name_with_leading_trailing_spaces(self) -> None:
        """Test name with leading and trailing spaces."""
        state = MigrationState(
            user_message="test message",
            path="/some/path",
            name="  my module  ",
            technology=Technology.CHEF,
            migration_plan_content="",
            module_migration_plan="",
            module_plan_path="",
        )
        result = state.get_migration_plan_path()
        assert result == "migration-plan-__my_module__.md"
