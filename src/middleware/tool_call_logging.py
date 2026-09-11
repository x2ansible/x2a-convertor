"""Middleware that logs every tool call made by an agent.

Pure observer: it calls the handler exactly once and never retries,
short-circuits, or rewrites the request/response. Both the synchronous
`wrap_tool_call` and asynchronous `wrap_tool_call_async` hooks are
implemented so tool calls are logged regardless of whether the agent is
invoked via `invoke()`/`stream()` or `ainvoke()`/`astream()`.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.utils.logging import get_logger

logger = get_logger(__name__)


class ToolCallLoggingMiddleware(AgentMiddleware):
    """Logs tool name, duration, and args for every tool call in the agent."""

    name = "ToolCallLogging"

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "unknown")
        start = time.monotonic()
        try:
            result = handler(request)
        except Exception:
            self._log_failure(tool_name, start, request)
            raise
        self._log_success(tool_name, start, request)
        return result

    async def wrap_tool_call_async(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "unknown")
        start = time.monotonic()
        try:
            result = await handler(request)
        except Exception:
            self._log_failure(tool_name, start, request)
            raise
        self._log_success(tool_name, start, request)
        return result

    def _log_success(
        self, tool_name: str, start: float, request: ToolCallRequest
    ) -> None:
        duration = time.monotonic() - start
        logger.info(
            "Tool call finished",
            tool=tool_name,
            duration_s=round(duration, 3),
            tool_args=self._select_args(request),
        )

    def _log_failure(
        self, tool_name: str, start: float, request: ToolCallRequest
    ) -> None:
        duration = time.monotonic() - start
        logger.exception(
            "Tool call failed",
            tool=tool_name,
            duration_s=round(duration, 3),
            tool_args=self._select_args(request),
        )

    @staticmethod
    def _select_args(request: ToolCallRequest) -> dict[str, Any]:
        """Pick the args worth logging for a tool call.

        DEBUG_LOG_ARGS is a ClassVar[list[str]] on X2ATool subclasses naming
        which args are safe/useful to log. Tools that don't declare it
        (including plain @tool-decorated helpers that don't inherit
        X2ATool) fail closed: nothing is logged besides name/duration.
        """
        tool_args = request.tool_call.get("args", {})
        allowed = getattr(request.tool, "DEBUG_LOG_ARGS", [])
        return {key: value for key, value in tool_args.items() if key in allowed}
