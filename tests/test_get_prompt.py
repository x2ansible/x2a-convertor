import tempfile
from pathlib import Path

import pytest

from prompts.get_prompt import JinjaTemplate, get_prompt, jinja_env


@pytest.fixture
def temp_prompts_dir(monkeypatch):
    """Create a temporary directory with test prompt files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Create a .md file with Python format strings
        md_content = "Hello {name}, your age is {age}."
        (tmp_path / "test_md.md").write_text(md_content, encoding="utf-8")

        # Create a .j2 file with Jinja2 syntax
        j2_content = "Hello {{ name }}, your age is {{ age }}."
        (tmp_path / "test_jinja.j2").write_text(j2_content, encoding="utf-8")

        # Create a .j2 file with Jinja2 features (loops, conditionals)
        j2_advanced = """Items:
{% for item in items %}
- {{ item }}
{% endfor %}
{% if show_total %}
Total: {{ items|length }}
{% endif %}"""
        (tmp_path / "test_advanced.j2").write_text(j2_advanced, encoding="utf-8")

        # Patch the base_path in get_prompt module
        import prompts.get_prompt as gp_module

        monkeypatch.setattr(gp_module, "base_path", tmp_path)

        # Update jinja_env loader
        from jinja2 import FileSystemLoader

        jinja_env.loader = FileSystemLoader(tmp_path)

        yield tmp_path


def test_md_file_returns_string(temp_prompts_dir):
    """Test that .md files return a plain string."""
    result = get_prompt("test_md")
    assert isinstance(result, str)
    assert result == "Hello {name}, your age is {age}."


def test_md_file_format_works(temp_prompts_dir):
    """Test that .md files work with .format()."""
    result = get_prompt("test_md")
    formatted = result.format(name="Alice", age=30)
    assert formatted == "Hello Alice, your age is 30."


def test_j2_file_returns_jinja_template(temp_prompts_dir):
    """Test that .j2 files return a JinjaTemplate wrapper."""
    result = get_prompt("test_jinja")
    assert isinstance(result, JinjaTemplate)


def test_j2_file_format_works(temp_prompts_dir):
    """Test that .j2 files work with .format() method."""
    result = get_prompt("test_jinja")
    formatted = result.format(name="Bob", age=25)
    assert formatted == "Hello Bob, your age is 25."


def test_j2_advanced_features(temp_prompts_dir):
    """Test that Jinja2 advanced features work (loops, conditionals)."""
    result = get_prompt("test_advanced")
    formatted = result.format(items=["apple", "banana", "cherry"], show_total=True)

    assert "- apple" in formatted
    assert "- banana" in formatted
    assert "- cherry" in formatted
    assert "Total: 3" in formatted


def test_j2_conditional_false(temp_prompts_dir):
    """Test Jinja2 conditionals with False value."""
    result = get_prompt("test_advanced")
    formatted = result.format(items=["apple"], show_total=False)

    assert "- apple" in formatted
    assert "Total:" not in formatted


def test_j2_priority_over_md(temp_prompts_dir):
    """Test that .j2 files take priority over .md files."""
    # Create both .md and .j2 files with same base name
    (temp_prompts_dir / "priority.md").write_text("MD content", encoding="utf-8")
    (temp_prompts_dir / "priority.j2").write_text("J2 content", encoding="utf-8")

    result = get_prompt("priority")
    assert isinstance(result, JinjaTemplate)
    assert result.format() == "J2 content"
