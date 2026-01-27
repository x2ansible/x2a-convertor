"""Tests for telemetry data structures and functionality."""

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from src.model import ToolCallCounter
from src.types.telemetry import (
    TELEMETRY_FILENAME,
    AgentMetrics,
    Telemetry,
    telemetry_context,
)


class TestAgentMetrics:
    """Tests for AgentMetrics dataclass."""

    def test_initialization(self):
        """Test that AgentMetrics initializes with correct defaults."""
        metrics = AgentMetrics(name="TestAgent")
        assert metrics.name == "TestAgent"
        assert metrics.started_at is None
        assert metrics.ended_at is None
        assert metrics.duration_seconds == 0.0
        assert metrics.metrics == {}
        assert metrics.tool_calls == {}

    def test_start_records_timestamp(self):
        """Test that start() records a timestamp."""
        metrics = AgentMetrics(name="TestAgent")
        before = datetime.now()
        result = metrics.start()
        after = datetime.now()

        assert metrics.started_at is not None
        assert before <= metrics.started_at <= after
        assert result is metrics  # Method chaining

    def test_stop_calculates_duration(self):
        """Test that stop() calculates duration correctly."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.start()
        time.sleep(0.01)  # Small delay to ensure non-zero duration
        result = metrics.stop()

        assert metrics.ended_at is not None
        assert metrics.duration_seconds > 0
        assert metrics.duration_seconds < 1  # Should be small
        assert result is metrics  # Method chaining

    def test_start_stop_chaining(self):
        """Test that method chaining works for start/stop."""
        metrics = AgentMetrics(name="TestAgent").start()
        assert metrics.started_at is not None

        metrics.stop()
        assert metrics.ended_at is not None
        assert metrics.duration_seconds > 0

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("test_string", "value"),
            ("test_int", 42),
            ("test_float", 3.14),
            ("test_bool", True),
            ("test_list", [1, 2, 3]),
            ("test_dict", {"nested": "value"}),
        ],
    )
    def test_record_metric_various_types(self, key, value):
        """Test recording metrics with various value types."""
        metrics = AgentMetrics(name="TestAgent")
        result = metrics.record_metric(key, value)

        assert metrics.metrics[key] == value
        assert result is metrics  # Method chaining

    def test_record_metric_overwrites(self):
        """Test that recording same metric key updates the value."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.record_metric("count", 1)
        assert metrics.metrics["count"] == 1

        metrics.record_metric("count", 2)
        assert metrics.metrics["count"] == 2

    def test_record_tool_calls_empty(self):
        """Test recording empty tool calls."""
        metrics = AgentMetrics(name="TestAgent")
        result = metrics.record_tool_calls(ToolCallCounter())

        assert metrics.tool_calls == {}
        assert result is metrics  # Method chaining

    def test_record_tool_calls_single(self):
        """Test recording single tool call."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.record_tool_calls(ToolCallCounter({"read_file": 5}))

        assert metrics.tool_calls == {"read_file": 5}

    def test_record_tool_calls_accumulates(self):
        """Test that multiple record_tool_calls accumulates counts."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.record_tool_calls(ToolCallCounter({"read_file": 5}))
        metrics.record_tool_calls(ToolCallCounter({"read_file": 3}))

        assert metrics.tool_calls["read_file"] == 8

    def test_record_tool_calls_multiple_tools(self):
        """Test recording multiple different tools."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.record_tool_calls(ToolCallCounter({"read_file": 5, "write_file": 2}))
        metrics.record_tool_calls(ToolCallCounter({"ansible_lint": 10}))

        assert metrics.tool_calls == {
            "read_file": 5,
            "write_file": 2,
            "ansible_lint": 10,
        }

    def test_to_dict_complete(self):
        """Test serialization to dict with complete data."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.start()
        time.sleep(0.01)
        metrics.stop()
        metrics.record_metric("files_created", 5)
        metrics.record_tool_calls(ToolCallCounter({"read_file": 10}))

        result = metrics.to_dict()

        assert result["name"] == "TestAgent"
        assert "started_at" in result
        assert "ended_at" in result
        assert result["duration_seconds"] > 0
        assert result["metrics"] == {"files_created": 5}
        assert result["tool_calls"] == {"read_file": 10}

        # Verify ISO 8601 format
        datetime.fromisoformat(result["started_at"])
        datetime.fromisoformat(result["ended_at"])

    def test_to_dict_before_stop(self):
        """Test serialization before stop() is called."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.start()

        result = metrics.to_dict()

        assert result["name"] == "TestAgent"
        assert result["started_at"] is not None
        assert result["ended_at"] is None
        assert result["duration_seconds"] == 0.0

    def test_to_dict_with_metrics_and_tools(self):
        """Test serialization includes all metrics and tool calls."""
        metrics = AgentMetrics(name="TestAgent")
        metrics.record_metric("key1", "value1")
        metrics.record_metric("key2", 42)
        metrics.record_tool_calls(ToolCallCounter({"tool1": 5, "tool2": 10}))

        result = metrics.to_dict()

        assert result["metrics"] == {"key1": "value1", "key2": 42}
        assert result["tool_calls"] == {"tool1": 5, "tool2": 10}


class TestTelemetry:
    """Tests for Telemetry phase-level collector."""

    def test_initialization_with_phase(self):
        """Test Telemetry initialization with phase name."""
        telemetry = Telemetry(phase="test_phase")

        assert telemetry.phase == "test_phase"
        assert telemetry.started_at is not None
        assert telemetry.ended_at is None
        assert telemetry.agents == {}

    def test_started_at_auto_set(self):
        """Test that started_at is automatically set on creation."""
        before = datetime.now()
        telemetry = Telemetry(phase="test")
        after = datetime.now()

        assert before <= telemetry.started_at <= after

    def test_get_or_create_agent_new(self):
        """Test getting a new agent creates it."""
        telemetry = Telemetry(phase="test")
        agent = telemetry.get_or_create_agent("NewAgent")

        assert isinstance(agent, AgentMetrics)
        assert agent.name == "NewAgent"
        assert "NewAgent" in telemetry.agents

    def test_get_or_create_agent_existing(self):
        """Test getting existing agent returns same instance."""
        telemetry = Telemetry(phase="test")
        agent1 = telemetry.get_or_create_agent("TestAgent")
        agent1.record_metric("test", 42)

        agent2 = telemetry.get_or_create_agent("TestAgent")

        assert agent1 is agent2
        assert agent2.metrics["test"] == 42

    def test_multiple_agents(self):
        """Test managing multiple different agents."""
        telemetry = Telemetry(phase="test")
        agent1 = telemetry.get_or_create_agent("Agent1")
        agent2 = telemetry.get_or_create_agent("Agent2")

        assert len(telemetry.agents) == 2
        assert telemetry.agents["Agent1"] is agent1
        assert telemetry.agents["Agent2"] is agent2

    def test_stop_sets_ended_at(self):
        """Test that stop() sets ended_at timestamp."""
        telemetry = Telemetry(phase="test")
        assert telemetry.ended_at is None

        result = telemetry.stop()

        assert telemetry.ended_at is not None
        assert result is telemetry  # Method chaining

    def test_duration_seconds_calculated(self):
        """Test duration_seconds property calculates correctly."""
        telemetry = Telemetry(phase="test")
        time.sleep(0.01)
        telemetry.stop()

        assert telemetry.duration_seconds > 0
        assert telemetry.duration_seconds < 1

    def test_duration_before_stop_is_zero(self):
        """Test duration is zero before stop() is called."""
        telemetry = Telemetry(phase="test")

        assert telemetry.duration_seconds == 0.0

    def test_get_total_tool_calls_empty(self):
        """Test total tool calls with no agents."""
        telemetry = Telemetry(phase="test")

        assert telemetry.get_total_tool_calls() == {}

    def test_get_total_tool_calls_single_agent(self):
        """Test total tool calls with single agent."""
        telemetry = Telemetry(phase="test")
        agent = telemetry.get_or_create_agent("TestAgent")
        agent.record_tool_calls(ToolCallCounter({"read_file": 5, "write_file": 2}))

        total = telemetry.get_total_tool_calls()

        assert total == {"read_file": 5, "write_file": 2}

    def test_get_total_tool_calls_multiple_agents(self):
        """Test total tool calls aggregates across agents."""
        telemetry = Telemetry(phase="test")
        agent1 = telemetry.get_or_create_agent("Agent1")
        agent1.record_tool_calls(ToolCallCounter({"read_file": 5, "write_file": 2}))

        agent2 = telemetry.get_or_create_agent("Agent2")
        agent2.record_tool_calls(ToolCallCounter({"ansible_lint": 10}))

        total = telemetry.get_total_tool_calls()

        assert total == {"read_file": 5, "write_file": 2, "ansible_lint": 10}

    def test_get_total_tool_calls_same_tool_different_agents(self):
        """Test total tool calls sums same tool across agents."""
        telemetry = Telemetry(phase="test")
        agent1 = telemetry.get_or_create_agent("Agent1")
        agent1.record_tool_calls(ToolCallCounter({"read_file": 5}))

        agent2 = telemetry.get_or_create_agent("Agent2")
        agent2.record_tool_calls(ToolCallCounter({"read_file": 3}))

        total = telemetry.get_total_tool_calls()

        assert total == {"read_file": 8}

    def test_to_dict_complete(self):
        """Test serialization to dict with complete data."""
        telemetry = Telemetry(phase="test")
        agent = telemetry.get_or_create_agent("TestAgent")
        agent.start()
        agent.record_tool_calls(ToolCallCounter({"read_file": 5}))
        agent.stop()
        telemetry.stop()

        result = telemetry.to_dict()

        assert result["phase"] == "test"
        assert "started_at" in result
        assert "ended_at" in result
        assert result["duration_seconds"] > 0
        assert "TestAgent" in result["agents"]
        assert result["total_tool_calls"] == {"read_file": 5}

        # Verify ISO 8601 format
        datetime.fromisoformat(result["started_at"])
        datetime.fromisoformat(result["ended_at"])

    def test_to_dict_with_multiple_agents(self):
        """Test serialization includes all agents."""
        telemetry = Telemetry(phase="test")
        agent1 = telemetry.get_or_create_agent("Agent1")
        agent1.record_metric("metric1", 1)

        agent2 = telemetry.get_or_create_agent("Agent2")
        agent2.record_metric("metric2", 2)

        result = telemetry.to_dict()

        assert len(result["agents"]) == 2
        assert "Agent1" in result["agents"]
        assert "Agent2" in result["agents"]
        assert result["agents"]["Agent1"]["metrics"] == {"metric1": 1}
        assert result["agents"]["Agent2"]["metrics"] == {"metric2": 2}

    def test_to_summary_readable_format(self):
        """Test to_summary produces readable output."""
        telemetry = Telemetry(phase="migrate")
        agent = telemetry.get_or_create_agent("TestAgent")
        agent.start()
        time.sleep(0.01)
        agent.stop()
        agent.record_metric("files_created", 5)
        agent.record_tool_calls(ToolCallCounter({"read_file": 10, "write_file": 5}))
        telemetry.stop()

        summary = telemetry.to_summary()

        assert "Phase: migrate" in summary
        assert "Duration:" in summary
        assert "TestAgent:" in summary
        assert "Tools: read_file: 10, write_file: 5" in summary
        assert "files_created: 5" in summary


class TestTelemetryContext:
    """Tests for telemetry_context context manager."""

    def test_context_with_telemetry(self):
        """Test context manager with valid telemetry."""
        telemetry = Telemetry(phase="test")

        with telemetry_context(telemetry, "TestAgent") as metrics:
            assert metrics is not None
            assert isinstance(metrics, AgentMetrics)
            assert metrics.name == "TestAgent"

    def test_context_with_none_telemetry(self):
        """Test context manager with None telemetry (no-op mode)."""
        with telemetry_context(None, "TestAgent") as metrics:
            assert metrics is None

    def test_context_starts_and_stops_timing(self):
        """Test that context manager automatically handles timing."""
        telemetry = Telemetry(phase="test")

        with telemetry_context(telemetry, "TestAgent") as metrics:
            assert metrics is not None
            assert metrics.started_at is not None
            assert metrics.ended_at is None
            time.sleep(0.01)

        agent = telemetry.agents["TestAgent"]
        assert agent.ended_at is not None
        assert agent.duration_seconds > 0

    def test_context_yields_agent_metrics(self):
        """Test that context manager yields correct AgentMetrics."""
        telemetry = Telemetry(phase="test")

        with telemetry_context(telemetry, "TestAgent") as metrics:
            assert metrics is not None
            metrics.record_metric("test_key", "test_value")

        agent = telemetry.agents["TestAgent"]
        assert agent.metrics["test_key"] == "test_value"

    def test_context_stops_timing_on_exception(self):
        """Test that timing stops even when exception is raised."""
        telemetry = Telemetry(phase="test")

        with pytest.raises(ValueError), telemetry_context(telemetry, "TestAgent"):
            raise ValueError("Test exception")

        agent = telemetry.agents["TestAgent"]
        assert agent.started_at is not None
        assert agent.ended_at is not None
        assert agent.duration_seconds > 0

    def test_context_preserves_exception(self):
        """Test that exceptions are properly propagated."""
        telemetry = Telemetry(phase="test")

        with (
            pytest.raises(RuntimeError, match="Custom error"),
            telemetry_context(telemetry, "TestAgent"),
        ):
            raise RuntimeError("Custom error")

    def test_context_creates_new_agent(self):
        """Test that context creates agent if it doesn't exist."""
        telemetry = Telemetry(phase="test")
        assert "NewAgent" not in telemetry.agents

        with telemetry_context(telemetry, "NewAgent"):
            pass

        assert "NewAgent" in telemetry.agents

    def test_context_reuses_existing_agent(self):
        """Test that context reuses existing agent."""
        telemetry = Telemetry(phase="test")
        agent = telemetry.get_or_create_agent("ExistingAgent")
        agent.record_metric("existing", True)

        with telemetry_context(telemetry, "ExistingAgent") as metrics:
            assert metrics is not None
            assert metrics.metrics["existing"] is True

    def test_multiple_contexts_same_agent(self):
        """Test multiple context uses with same agent name."""
        telemetry = Telemetry(phase="test")

        with telemetry_context(telemetry, "Agent") as metrics:
            assert metrics is not None
            metrics.record_tool_calls(ToolCallCounter({"tool1": 5}))

        # Second context with same agent should reuse and accumulate
        with telemetry_context(telemetry, "Agent") as metrics:
            assert metrics is not None
            metrics.record_tool_calls(ToolCallCounter({"tool1": 3}))

        agent = telemetry.agents["Agent"]
        # Tool calls should accumulate
        assert agent.tool_calls["tool1"] == 8


class TestTelemetryPersistence:
    """Tests for file I/O operations."""

    def test_save_default_filename(self, tmp_path, monkeypatch):
        """Test saving with default filename."""
        monkeypatch.chdir(tmp_path)
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        result_path = telemetry.save()

        assert result_path == Path(TELEMETRY_FILENAME)
        assert result_path.exists()

    @pytest.mark.parametrize(
        "custom_path",
        [
            "custom-telemetry.json",
            "subdir/telemetry.json",
        ],
    )
    def test_save_custom_path(self, tmp_path, custom_path):
        """Test saving with custom path."""
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        # Create subdirectory if needed
        full_path = tmp_path / custom_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        result_path = telemetry.save(str(full_path))

        assert result_path == full_path
        assert result_path.exists()

    def test_save_with_path_object(self, tmp_path):
        """Test saving with Path object."""
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        path = tmp_path / "telemetry.json"
        result_path = telemetry.save(path)

        assert result_path == path
        assert result_path.exists()

    def test_save_returns_path(self, tmp_path):
        """Test that save returns the Path object."""
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        path = tmp_path / "test.json"
        result = telemetry.save(path)

        assert isinstance(result, Path)
        assert result == path

    def test_saved_json_is_valid(self, tmp_path):
        """Test that saved file contains valid JSON."""
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        path = tmp_path / "test.json"
        telemetry.save(path)

        content = path.read_text()
        data = json.loads(content)  # Should not raise

        assert isinstance(data, dict)

    def test_saved_json_has_required_fields(self, tmp_path):
        """Test that saved JSON has all required fields."""
        telemetry = Telemetry(phase="test")
        agent = telemetry.get_or_create_agent("TestAgent")
        agent.start()
        agent.stop()
        telemetry.stop()

        path = tmp_path / "test.json"
        telemetry.save(path)

        data = json.loads(path.read_text())

        assert "phase" in data
        assert "started_at" in data
        assert "ended_at" in data
        assert "duration_seconds" in data
        assert "agents" in data
        assert "total_tool_calls" in data

    def test_saved_json_roundtrip(self, tmp_path):
        """Test saving and loading back preserves data."""
        telemetry = Telemetry(phase="migrate")
        agent = telemetry.get_or_create_agent("TestAgent")
        agent.start()
        agent.record_metric("files_created", 5)
        agent.record_tool_calls(ToolCallCounter({"read_file": 10}))
        agent.stop()
        telemetry.stop()

        path = tmp_path / "test.json"
        telemetry.save(path)

        # Load back and verify
        loaded_data = json.loads(path.read_text())

        assert loaded_data["phase"] == "migrate"
        assert loaded_data["agents"]["TestAgent"]["metrics"]["files_created"] == 5
        assert loaded_data["agents"]["TestAgent"]["tool_calls"]["read_file"] == 10
        assert loaded_data["total_tool_calls"]["read_file"] == 10

    def test_json_formatting_indented(self, tmp_path):
        """Test that saved JSON is indented for readability."""
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        path = tmp_path / "test.json"
        telemetry.save(path)

        content = path.read_text()

        # Indented JSON should have newlines and spaces
        assert "\n" in content
        assert "  " in content  # Two-space indentation

    def test_save_overwrites_existing(self, tmp_path):
        """Test that saving overwrites existing file."""
        path = tmp_path / "test.json"
        path.write_text('{"old": "data"}')

        telemetry = Telemetry(phase="new_phase")
        telemetry.stop()
        telemetry.save(path)

        data = json.loads(path.read_text())
        assert data["phase"] == "new_phase"
        assert "old" not in data

    def test_save_in_nonexistent_directory_fails(self, tmp_path):
        """Test that saving to nonexistent directory raises error."""
        telemetry = Telemetry(phase="test")
        telemetry.stop()

        nonexistent_path = tmp_path / "nonexistent" / "subdir" / "test.json"

        with pytest.raises(FileNotFoundError):
            telemetry.save(nonexistent_path)


@pytest.fixture
def sample_telemetry():
    """Create a sample Telemetry instance with some data."""
    telemetry = Telemetry(phase="test")
    agent1 = telemetry.get_or_create_agent("TestAgent1")
    agent1.start()
    agent1.record_metric("test_value", 42)
    agent1.record_tool_calls(ToolCallCounter({"read_file": 5, "write_file": 2}))
    agent1.stop()
    telemetry.stop()
    return telemetry
