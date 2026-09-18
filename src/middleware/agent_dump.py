"""Middleware and callbacks for dumping agent messages to JSON Lines format."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)

from src.config import get_settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SnapshotWriter:
    """Converts LangChain messages to Claude Code snapshot format and writes JSONL.

    Pure writer with no framework coupling — can be composed into middleware,
    callbacks, or any other hook mechanism.
    """

    def __init__(self, agent_name: str, agent_id: str) -> None:
        self._agent_name = agent_name
        self._agent_id = agent_id
        self._message_counter = 0

    @property
    def file_name(self) -> str:
        return f"{self._agent_name}-{self._agent_id}.jsonl"

    def _get_output_path(self) -> Path | None:
        settings = get_settings()
        if not settings.logging.json_lines:
            return None

        output_dir = Path(settings.logging.json_lines)
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / self.file_name

    def _convert_message(self, message: BaseMessage) -> dict[str, Any]:
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

    def write_snapshot(self, messages: list[BaseMessage]) -> None:
        output_path = self._get_output_path()
        if not output_path:
            return

        if not messages:
            return

        try:
            snapshot = [self._convert_message(msg) for msg in messages]
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


class AgentDumpMiddleware(AgentMiddleware):
    """Accumulates agent conversation messages and writes them to JSONL once,
    when the agent run finishes.

    Used with invoke_react where the full middleware pipeline is available.

    Messages are still accumulated on every before_model call (not just at
    the end), because X2ASummarizationMiddleware can evict messages from live
    graph state (RemoveMessage(REMOVE_ALL_MESSAGES)) partway through a run.
    Capturing them incrementally in memory as they appear is what lets the
    final write reflect the full conversation even though the live state no
    longer does. Only the on-disk write is deferred to after_agent; nothing
    is written to disk before then.

    This should always be registered before the summarization middleware, so
    its before_model hook sees each turn's messages before summarization can
    evict them.
    """

    def __init__(self, writer: SnapshotWriter) -> None:
        self._writer = writer
        self._seen_ids: set[str] = set()
        self._cumulative_messages: list[BaseMessage] = []

    @property
    def file_name(self) -> str:
        return self._writer.file_name

    def _reset(self) -> None:
        """Clear accumulated history at the start of a new agent run.

        AgentMiddleware instances are cached on BaseAgent across multiple
        invoke_react() calls (see BaseAgent.middleware()), so an agent that
        calls invoke_react() more than once (e.g. WriteAgent's internal retry
        loop) reuses this same instance. Without an explicit reset at the
        start of each graph run (before_agent fires once per invoke_react()
        call), _cumulative_messages would silently pool messages across
        unrelated calls.
        """
        self._seen_ids = set()
        self._cumulative_messages = []

    def _accumulate(self, state: Any) -> None:
        """Merge state's messages into the in-memory cumulative history.

        Deduplicates by message id so messages already captured on an
        earlier turn (before eviction) are not counted twice. Does not write
        to disk -- see _dump().
        """
        messages = state.get("messages", [])

        for msg in messages:
            if isinstance(msg, RemoveMessage):
                continue

            msg_id = msg.id or str(id(msg))

            if msg_id in self._seen_ids:
                continue
            self._seen_ids.add(msg_id)
            self._cumulative_messages.append(msg)

    def _dump(self) -> None:
        """Write the full cumulative history to disk as a single snapshot."""
        self._writer.write_snapshot(self._cumulative_messages)

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._reset()
        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._reset()
        return None

    def before_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._accumulate(state)
        return None

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._accumulate(state)
        return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._accumulate(state)
        self._dump()
        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        self._accumulate(state)
        self._dump()
        return None


class AgentDumpCallbackHandler(BaseCallbackHandler):
    """LangChain callback that captures LLM calls and writes JSONL snapshots.

    Used with invoke_llm and invoke_structured where middleware is not available.
    Hooks on_chat_model_start to capture input messages and on_llm_end to capture
    the response, then writes the full conversation as a snapshot.
    """

    def __init__(self, writer: SnapshotWriter) -> None:
        super().__init__()
        self._writer = writer
        self._pending_messages: list[BaseMessage] = []

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        **kwargs: Any,
    ) -> None:
        self._pending_messages = list(messages[0]) if messages else []

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        self._pending_messages = []

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        generations = getattr(response, "generations", [])
        if not generations or not generations[0]:
            self._writer.write_snapshot(self._pending_messages)
            self._pending_messages = []
            return

        generation = generations[0][0]
        if hasattr(generation, "message"):
            self._pending_messages.append(generation.message)

        self._writer.write_snapshot(self._pending_messages)
        self._pending_messages = []
