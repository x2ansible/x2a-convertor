"""Tests for PrioritiesGenerationAgent."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.init.priorities_generation_agent import PrioritiesGenerationAgent
from src.types.priorities import PrioritiesOutput, PrioritiesSection
from src.types.rule_file import RuleCollection, RuleFile
from src.types.technology import Technology
from src.types.telemetry import AgentMetrics


@pytest.fixture
def agent():
    """Create a PrioritiesGenerationAgent with a mock model."""
    mock_model = MagicMock()
    return PrioritiesGenerationAgent(model=mock_model)


@pytest.fixture
def sample_priorities_output():
    """Sample PrioritiesOutput from structured LLM call."""
    return PrioritiesOutput(
        input_priorities=[
            PrioritiesSection(title="Discovery Rules", content="Check for notifies."),
            PrioritiesSection(title="Dependency Analysis", content="Map all deps."),
        ],
        export_priorities=[
            PrioritiesSection(
                title="Collection Policy", content="Use community.general."
            ),
            PrioritiesSection(title="CI Workflow", content="Include GitHub Actions."),
        ],
    )


def _make_init_state(**overrides):
    """Create a minimal InitState for testing."""
    from src.init.init_state import InitState

    return InitState(
        user_message=overrides.get("user_message", "test"),
        path=overrides.get("path", "/tmp/test"),
        directory_listing=overrides.get("directory_listing", "file1.rb\nfile2.rb"),
        migration_plan_content=overrides.get(
            "migration_plan_content", "# Chef Migration Plan\n\nSome content"
        ),
        source_technology=overrides.get("source_technology", Technology.CHEF),
    )


class TestRuleFile:
    """Tests for RuleFile class."""

    def test_from_path(self, tmp_path):
        """Creates RuleFile from a file on disk."""
        rule_path = tmp_path / "discovery.md"
        rule_path.write_text("Check for notifies", encoding="utf-8")

        rule = RuleFile.from_path(rule_path)

        assert rule.filename == "discovery.md"
        assert rule.content == "Check for notifies"

    def test_to_document(self):
        """Renders as XML document format."""
        rule = RuleFile(filename="test.md", content="Rule content here")

        result = rule.to_document()

        assert '<rule file="test.md">' in result
        assert "Rule content here" in result
        assert "</rule>" in result


class TestRuleCollection:
    """Tests for RuleCollection class."""

    def test_from_directory_missing(self, tmp_path):
        """Missing directory returns empty collection."""
        collection = RuleCollection.from_directory(tmp_path / "nonexistent")

        assert collection.is_empty()

    def test_from_directory_no_md_files(self, tmp_path):
        """Directory with no .md files returns empty collection."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "readme.txt").write_text("not a rule")

        collection = RuleCollection.from_directory(rules_dir)

        assert collection.is_empty()

    def test_from_directory_loads_files(self, tmp_path):
        """Loads all .md files from directory."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule-a.md").write_text("Rule A content")
        (rules_dir / "rule-b.md").write_text("Rule B content")

        collection = RuleCollection.from_directory(rules_dir)

        assert not collection.is_empty()
        assert len(collection.rules) == 2
        assert collection.rules[0].filename == "rule-a.md"
        assert collection.rules[0].content == "Rule A content"

    def test_from_directory_ignores_non_md(self, tmp_path):
        """Only .md files are loaded."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Valid rule")
        (rules_dir / "notes.txt").write_text("Not a rule")
        (rules_dir / "data.json").write_text("{}")

        collection = RuleCollection.from_directory(rules_dir)

        assert len(collection.rules) == 1
        assert collection.rules[0].filename == "rule.md"

    def test_from_directory_sorted_alphabetically(self, tmp_path):
        """Files are sorted alphabetically."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "zebra.md").write_text("Z")
        (rules_dir / "alpha.md").write_text("A")
        (rules_dir / "middle.md").write_text("M")

        collection = RuleCollection.from_directory(rules_dir)

        filenames = [r.filename for r in collection.rules]
        assert filenames == ["alpha.md", "middle.md", "zebra.md"]

    def test_to_document(self):
        """Renders all rules wrapped in organizational_rules tags."""
        collection = RuleCollection(
            rules=[
                RuleFile(filename="a.md", content="Content A"),
                RuleFile(filename="b.md", content="Content B"),
            ]
        )

        result = collection.to_document()

        assert "<organizational_rules>" in result
        assert "</organizational_rules>" in result
        assert '<rule file="a.md">' in result
        assert '<rule file="b.md">' in result

    def test_to_document_empty(self):
        """Empty collection returns empty string."""
        collection = RuleCollection(rules=[])

        assert collection.to_document() == ""


class TestPrioritiesOutput:
    """Tests for PrioritiesOutput file writing."""

    def test_write_input_file(self, tmp_path):
        """write_input_file writes sections with separator."""
        output = PrioritiesOutput(
            input_priorities=[
                PrioritiesSection(title="Section One", content="Content one."),
                PrioritiesSection(title="Section Two", content="Content two."),
            ],
            export_priorities=[],
        )

        filepath = str(tmp_path / "INPUT.md")
        output.write_input_file(filepath)

        result = Path(filepath).read_text(encoding="utf-8")
        assert "## Section One\n\nContent one." in result
        assert "## Section Two\n\nContent two." in result
        assert "\n\n---\n\n" in result

    def test_write_export_file(self, tmp_path):
        """write_export_file writes sections."""
        output = PrioritiesOutput(
            input_priorities=[],
            export_priorities=[
                PrioritiesSection(title="Export Rule", content="Do this."),
            ],
        )

        filepath = str(tmp_path / "EXPORT.md")
        output.write_export_file(filepath)

        result = Path(filepath).read_text(encoding="utf-8")
        assert "## Export Rule\n\nDo this." in result

    def test_empty_sections_skip_file(self, tmp_path):
        """Empty sections list does not create a file."""
        output = PrioritiesOutput(input_priorities=[], export_priorities=[])

        filepath = str(tmp_path / "EMPTY.md")
        output.write_input_file(filepath)

        assert not Path(filepath).exists()

    def test_single_section_no_separator(self, tmp_path):
        """Single section has no separator."""
        output = PrioritiesOutput(
            input_priorities=[PrioritiesSection(title="Only", content="Only content.")],
            export_priorities=[],
        )

        filepath = str(tmp_path / "SINGLE.md")
        output.write_input_file(filepath)

        result = Path(filepath).read_text(encoding="utf-8")
        assert result == "## Only\n\nOnly content."
        assert "---" not in result


class TestExecute:
    """Tests for full execute flow."""

    def test_skips_when_no_rules(self, agent, tmp_path):
        """Execute returns state unchanged when no rules found."""
        agent.RULES_DIRECTORY = str(tmp_path / "nonexistent")
        state = _make_init_state()

        result = agent.execute(state, None)

        assert result is state

    def test_skips_when_empty_plan(self, agent, tmp_path):
        """Execute returns state when migration plan is empty."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Some rule")
        agent.RULES_DIRECTORY = str(rules_dir)
        state = _make_init_state(migration_plan_content="")

        result = agent.execute(state, None)

        assert result is state

    @patch.object(PrioritiesGenerationAgent, "invoke_structured")
    def test_uses_technology_from_state(self, mock_invoke, agent, tmp_path):
        """Execute uses source_technology from state, not text parsing."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Some rule")
        agent.RULES_DIRECTORY = str(rules_dir)

        mock_invoke.return_value = PrioritiesOutput(
            input_priorities=[
                PrioritiesSection(title="Test", content="Content"),
            ],
            export_priorities=[],
        )

        state = _make_init_state(
            migration_plan_content="# Chef Migration Plan",
            source_technology=Technology.PUPPET,
        )

        with (
            patch(
                "src.init.priorities_generation_agent.INPUT_AGENTS_FILE",
                str(tmp_path / "I.md"),
            ),
            patch(
                "src.init.priorities_generation_agent.EXPORT_AGENTS_FILE",
                str(tmp_path / "E.md"),
            ),
        ):
            agent.execute(state, None)

        call_args = mock_invoke.call_args
        messages = call_args[0][1]
        system_msg = messages[0]["content"]
        assert "Puppet" in system_msg

    @patch.object(PrioritiesGenerationAgent, "invoke_structured")
    def test_defaults_to_chef_when_no_technology(self, mock_invoke, agent, tmp_path):
        """Falls back to Chef when state has no source_technology."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Some rule")
        agent.RULES_DIRECTORY = str(rules_dir)

        mock_invoke.return_value = PrioritiesOutput(
            input_priorities=[
                PrioritiesSection(title="Test", content="Content"),
            ],
            export_priorities=[],
        )

        state = _make_init_state(source_technology=None)

        with (
            patch(
                "src.init.priorities_generation_agent.INPUT_AGENTS_FILE",
                str(tmp_path / "I.md"),
            ),
            patch(
                "src.init.priorities_generation_agent.EXPORT_AGENTS_FILE",
                str(tmp_path / "E.md"),
            ),
        ):
            agent.execute(state, None)

        call_args = mock_invoke.call_args
        messages = call_args[0][1]
        system_msg = messages[0]["content"]
        assert "Chef" in system_msg

    @patch.object(PrioritiesGenerationAgent, "invoke_structured")
    def test_writes_both_files(
        self, mock_invoke, agent, tmp_path, sample_priorities_output
    ):
        """Execute writes both INPUT-AGENTS.md and EXPORT-AGENTS.md."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Some rule")
        agent.RULES_DIRECTORY = str(rules_dir)

        mock_invoke.return_value = sample_priorities_output

        input_file = str(tmp_path / "INPUT-AGENTS.md")
        export_file = str(tmp_path / "EXPORT-AGENTS.md")

        with (
            patch("src.init.priorities_generation_agent.INPUT_AGENTS_FILE", input_file),
            patch(
                "src.init.priorities_generation_agent.EXPORT_AGENTS_FILE", export_file
            ),
        ):
            state = _make_init_state()
            agent.execute(state, None)

        assert Path(input_file).exists()
        assert Path(export_file).exists()

        input_content = Path(input_file).read_text()
        assert "Discovery Rules" in input_content

        export_content = Path(export_file).read_text()
        assert "Collection Policy" in export_content

    @patch.object(PrioritiesGenerationAgent, "invoke_structured")
    def test_records_metrics(
        self, mock_invoke, agent, tmp_path, sample_priorities_output
    ):
        """Execute records section counts in metrics."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Some rule")
        agent.RULES_DIRECTORY = str(rules_dir)

        mock_invoke.return_value = sample_priorities_output
        metrics = AgentMetrics(name="Priorities Generator")

        with (
            patch(
                "src.init.priorities_generation_agent.INPUT_AGENTS_FILE",
                str(tmp_path / "INPUT.md"),
            ),
            patch(
                "src.init.priorities_generation_agent.EXPORT_AGENTS_FILE",
                str(tmp_path / "EXPORT.md"),
            ),
        ):
            state = _make_init_state()
            agent.execute(state, metrics)

        assert metrics.metrics["input_priorities_sections"] == 2
        assert metrics.metrics["export_priorities_sections"] == 2

    @patch.object(PrioritiesGenerationAgent, "invoke_structured")
    def test_handles_none_response(self, mock_invoke, agent, tmp_path):
        """Execute handles None response from LLM gracefully."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "rule.md").write_text("Some rule")
        agent.RULES_DIRECTORY = str(rules_dir)

        mock_invoke.return_value = None
        state = _make_init_state()

        result = agent.execute(state, None)

        assert result is state
