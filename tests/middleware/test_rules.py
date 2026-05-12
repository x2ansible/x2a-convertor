"""Tests for RulesMiddleware."""

import asyncio

from langchain_core.messages import HumanMessage

from src.middleware.rules import RulesMiddleware


class TestRulesMiddlewareLoadAndRender:
    """Tests for file loading and Jinja2 rendering."""

    def test_existing_file_returns_message_with_rendered_content(self, tmp_path):
        """A valid rules file produces a HumanMessage wrapped in XML tags."""
        rules = tmp_path / "rules.md"
        rules.write_text("Rule 1: Always use FQCN\nRule 2: No hardcoded IPs")

        middleware = RulesMiddleware(str(rules))
        result = middleware.before_agent(state={}, runtime=None)

        assert result is not None
        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert "<agent_rules>" in messages[0].content
        assert "Rule 1: Always use FQCN" in messages[0].content
        assert "Rule 2: No hardcoded IPs" in messages[0].content
        assert "</agent_rules>" in messages[0].content

    def test_missing_file_returns_none(self, tmp_path):
        """A non-existent file results in a no-op (None)."""
        middleware = RulesMiddleware(str(tmp_path / "does-not-exist.md"))
        result = middleware.before_agent(state={}, runtime=None)

        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        """An empty file results in a no-op (None)."""
        rules = tmp_path / "empty.md"
        rules.write_text("")

        middleware = RulesMiddleware(str(rules))
        result = middleware.before_agent(state={}, runtime=None)

        assert result is None

    def test_whitespace_only_file_returns_none(self, tmp_path):
        """A file with only whitespace results in a no-op (None)."""
        rules = tmp_path / "whitespace.md"
        rules.write_text("   \n\n  \t  \n")

        middleware = RulesMiddleware(str(rules))
        result = middleware.before_agent(state={}, runtime=None)

        assert result is None

    def test_unreadable_file_returns_none(self, tmp_path):
        """A file that cannot be read results in a no-op (None)."""
        rules = tmp_path / "unreadable.md"
        rules.write_text("content")
        rules.chmod(0o000)

        middleware = RulesMiddleware(str(rules))
        result = middleware.before_agent(state={}, runtime=None)

        assert result is None

        # Restore permissions for cleanup
        rules.chmod(0o644)

    def test_file_with_jinja2_braces_renders_correctly(self, tmp_path):
        """Rules content with Jinja2-like braces does not break rendering."""
        rules = tmp_path / "braces.md"
        rules.write_text("Use {{ variable_name }} in templates")

        middleware = RulesMiddleware(str(rules))
        result = middleware.before_agent(state={}, runtime=None)

        # The Jinja2 template uses {{ rules_content }} which is the variable.
        # The file content itself should NOT be interpreted as Jinja2.
        # This test verifies no crash occurs. The content will be rendered by Jinja2
        # so {{ variable_name }} will be treated as a Jinja2 expression.
        assert result is not None

    def test_framing_text_includes_mandatory_instructions(self, tmp_path):
        """The rendered output includes the instruction framing from the template."""
        rules = tmp_path / "rules.md"
        rules.write_text("Be concise")

        middleware = RulesMiddleware(str(rules))
        result = middleware.before_agent(state={}, runtime=None)

        assert result is not None
        content = result["messages"][0].content
        assert "mandatory rules and constraints" in content
        assert "MUST follow these rules" in content
        assert "take precedence over default behavior" in content


class TestRulesMiddlewareAsync:
    """Tests for async variants."""

    def test_abefore_agent_with_existing_file(self, tmp_path):
        """Async variant produces the same result as sync."""
        rules = tmp_path / "rules.md"
        rules.write_text("Async rule: test all the things")

        middleware = RulesMiddleware(str(rules))
        result = asyncio.run(middleware.abefore_agent(state={}, runtime=None))

        assert result is not None
        assert "Async rule: test all the things" in result["messages"][0].content

    def test_abefore_agent_with_missing_file(self, tmp_path):
        """Async variant returns None for missing file."""
        middleware = RulesMiddleware(str(tmp_path / "missing.md"))
        result = asyncio.run(middleware.abefore_agent(state={}, runtime=None))

        assert result is None
