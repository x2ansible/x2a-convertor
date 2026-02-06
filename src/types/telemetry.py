"""Telemetry data structures for migration workflow tracking.

This module provides:
- AgentMetrics: Per-agent telemetry (timing, tool calls, custom metrics)
- Telemetry: Phase-level telemetry collector
- telemetry_context: Context manager for agent execution timing
"""

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.model import ToolCallCounter

# Default telemetry file name
TELEMETRY_FILENAME = ".x2a-telemetry.json"


@dataclass
class AgentMetrics:
    """Telemetry data for a single agent execution.

    Tracks timing, tool calls, and custom metrics for each agent
    in the migration workflow.

    Attributes:
        name: Agent identifier (e.g., "PlanningAgent", "WriteAgent")
        started_at: When agent execution started
        ended_at: When agent execution completed
        duration_seconds: Calculated duration (set by stop())
        metrics: Custom key-value metrics recorded by the agent
        tool_calls: Tool call counts (tool_name -> count)
    """

    name: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    tool_calls: dict[str, int] = field(default_factory=dict)

    def start(self) -> "AgentMetrics":
        """Mark the start of agent execution.

        Returns:
            Self for method chaining
        """
        self.started_at = datetime.now()
        return self

    def stop(self) -> "AgentMetrics":
        """Mark the end of agent execution and calculate duration.

        Returns:
            Self for method chaining
        """
        self.ended_at = datetime.now()
        if self.started_at:
            delta = self.ended_at - self.started_at
            self.duration_seconds = delta.total_seconds()
        return self

    def record_tool_calls(self, counter: "ToolCallCounter") -> "AgentMetrics":
        """Merge tool call counts from a ToolCallCounter.

        Args:
            counter: ToolCallCounter from report_tool_calls()

        Returns:
            Self for method chaining
        """
        for tool_name, count in counter.items():
            self.tool_calls[tool_name] = self.tool_calls.get(tool_name, 0) + count
        return self

    def record_metric(self, key: str, value: Any) -> "AgentMetrics":
        """Record a custom metric.

        Args:
            key: Metric name
            value: Metric value

        Returns:
            Self for method chaining
        """
        self.metrics[key] = value
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "metrics": self.metrics,
            "tool_calls": self.tool_calls,
        }


@dataclass
class Telemetry:
    """Phase-level telemetry collector attached to state.

    Collects timing and metrics for a migration phase, including
    all agent executions within that phase.

    Attributes:
        phase: Current phase name (e.g., "init", "analyze", "migrate", "publish")
        started_at: When the phase started
        ended_at: When the phase completed
        agents: Per-agent metrics (agent_name -> AgentMetrics)
        summary: Human-readable summary of the phase execution (default: empty string)
    """

    phase: str
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: datetime | None = None
    agents: dict[str, AgentMetrics] = field(default_factory=dict)
    summary: str = ""

    def get_or_create_agent(self, name: str) -> AgentMetrics:
        """Get existing agent metrics or create new.

        Args:
            name: Agent name (typically class name)

        Returns:
            AgentMetrics instance for the agent
        """
        if name not in self.agents:
            self.agents[name] = AgentMetrics(name=name)
        return self.agents[name]

    def stop(self) -> "Telemetry":
        """Mark the end of phase execution.

        Returns:
            Self for method chaining
        """
        self.ended_at = datetime.now()
        return self

    def with_summary(self, summary: str) -> "Telemetry":
        """Set the summary text for this telemetry instance.

        Args:
            summary: Human-readable summary of the phase execution

        Returns:
            Self for method chaining
        """
        self.summary = summary
        return self

    @property
    def duration_seconds(self) -> float:
        """Calculate total phase duration."""
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at).total_seconds()
        return 0.0

    def get_total_tool_calls(self) -> dict[str, int]:
        """Aggregate tool calls across all agents."""
        total: dict[str, int] = {}
        for agent in self.agents.values():
            for tool_name, count in agent.tool_calls.items():
                total[tool_name] = total.get(tool_name, 0) + count
        return total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "phase": self.phase,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "agents": {name: agent.to_dict() for name, agent in self.agents.items()},
            "total_tool_calls": self.get_total_tool_calls(),
            "summary": self.summary,
        }

    def to_summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Phase: {self.phase}",
            f"Duration: {self.duration_seconds:.2f}s",
        ]
        if self.agents:
            lines.append("")
            lines.append("Agent Metrics:")
            for agent in self.agents.values():
                lines.append(f"  {agent.name}: {agent.duration_seconds:.2f}s")
                if agent.tool_calls:
                    tool_summary = ", ".join(
                        f"{k}: {v}" for k, v in sorted(agent.tool_calls.items())
                    )
                    lines.append(f"    Tools: {tool_summary}")
                if agent.metrics:
                    for key, value in agent.metrics.items():
                        lines.append(f"    {key}: {value}")
        return "\n".join(lines)

    def save(self, path: Path | str | None = None) -> Path:
        """Save telemetry data to a JSON file.

        Args:
            path: Optional path to save to. If None, uses TELEMETRY_FILENAME
                  in the current directory.

        Returns:
            Path to the saved file
        """
        if path is None:
            path = Path(TELEMETRY_FILENAME)
        elif isinstance(path, str):
            path = Path(path)

        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path


@contextmanager
def telemetry_context(telemetry: "Telemetry | None", agent_name: str):
    """Context manager for timing agent execution.

    Handles start/stop timing automatically. Safe to use even when
    telemetry is None (no-op in that case).

    Args:
        telemetry: Telemetry instance or None
        agent_name: Name of the agent being executed

    Yields:
        AgentMetrics instance or None

    Example:
        with telemetry_context(state.telemetry, self.__class__.__name__) as metrics:
            # Agent execution here
            if metrics:
                metrics.record_metric("files_processed", 5)
    """
    if telemetry is None:
        yield None
        return

    agent_metrics = telemetry.get_or_create_agent(agent_name)
    agent_metrics.start()
    try:
        yield agent_metrics
    finally:
        agent_metrics.stop()
