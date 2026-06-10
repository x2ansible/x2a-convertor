"""Middleware that dumps agent messages to JSON Lines format for debugging."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.config import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AgentDumpMiddleware(AgentMiddleware):
    """Dumps agent conversation messages to JSON Lines file.

    Writes messages in Claude Code JSON Lines format to enable debugging
    and inspection of agent conversations.
    """

    def __init__(self, agent_name: str, agent_id: str) -> None:
        self._agent_name = agent_name
        self._agent_id = agent_id
        self._message_counter = 0

    @property
    def file_name(self) -> str:
        return f"{self._agent_name}-{self._agent_id}.jsonl"

    def _get_output_path(self) -> Path | None:
        """Get the output file path from settings."""
        settings = get_settings()
        if not settings.logging.json_lines:
            return None

        output_dir = Path(settings.logging.json_lines)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{self.file_name}"

    def _convert_message_to_snapshot(self, message: BaseMessage) -> dict[str, Any]:
        """Convert LangChain message to Claude Code snapshot format."""
        if isinstance(message, HumanMessage):
            return {
                "role": "user",
                "content": [{"type": "text", "text": str(message.content)}],
            }

        if isinstance(message, AIMessage):
            content_parts: list[dict[str, Any]] = []

            if message.content:
                content_parts.append({"type": "text", "text": str(message.content)})

            if hasattr(message, "tool_calls") and message.tool_calls:
                for tool_call in message.tool_calls:
                    content_parts.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.get("id", f"tool_{self._message_counter}"),
                            "name": tool_call.get("name", "unknown"),
                            "input": tool_call.get("args", {}),
                        }
                    )

            return {"role": "assistant", "content": content_parts}

        if isinstance(message, ToolMessage):
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": getattr(message, "tool_call_id", "unknown"),
                        "content": str(message.content),
                    }
                ],
            }

        return {
            "role": "user",
            "content": [{"type": "text", "text": str(message.content)}],
        }

    def _write_snapshot(self, state: Any) -> None:
        """Write current conversation state to JSON Lines file."""
        output_path = self._get_output_path()
        if not output_path:
            return

        try:
            messages = state.get("messages", [])
            if not messages:
                return

            snapshot = [self._convert_message_to_snapshot(msg) for msg in messages]

            self._message_counter += 1
            entry = {
                "type": "snapshot",
                "messageId": f"msg_{self._agent_id}_{self._message_counter}",
                "snapshot": snapshot,
                "isSnapshotUpdate": True,
            }

            with output_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")

            logger.debug(
                "Wrote message snapshot",
                agent_name=self._agent_name,
                agent_id=self._agent_id,
                message_count=len(messages),
                output_path=str(output_path),
            )

        except Exception as exc:
            logger.warning(
                "Failed to write message snapshot",
                agent_name=self._agent_name,
                agent_id=self._agent_id,
                error=str(exc),
            )

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Write message snapshot after agent execution."""
        self._write_snapshot(state)
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async variant of after_agent."""
        self._write_snapshot(state)
        return None
