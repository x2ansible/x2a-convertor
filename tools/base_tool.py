"""Base tool class with agent-aware structured logging."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from langchain_core.tools import BaseTool, tool
from pydantic import PrivateAttr

from src.utils.logging import get_logger


class X2ATool(BaseTool):
    """Base class for all x2a-convertor tools.

    Provides agent-aware logging via a ``log`` property that automatically
    includes the tool name and, when set, the invoking agent name.

    Usage inside a tool subclass::

        slog = self.log.bind(file_path=path)
        slog.info("wrote file")

    Subclasses must declare DEBUG_LOG_ARGS, the list of arg names that
    ToolCallLoggingMiddleware is allowed to log for tool calls, e.g.:

        DEBUG_LOG_ARGS: ClassVar[list[str]] = ["file_path"]

    Defaults to an empty list so tools that forget to declare it fail
    closed -- only name/duration are logged, never arg values.
    """

    DEBUG_LOG_ARGS: ClassVar[list[str]] = []

    _agent_name: str = PrivateAttr(default="")

    def with_agent(self, name: str) -> X2ATool:
        """Bind the invoking agent name for structured logging.

        Returns *self* so it can be used inline::

            tool = MyTool().with_agent("MigrationAgent")
        """
        self._agent_name = name
        return self

    @property
    def log(self):
        """Return a structlog logger bound to this tool (and agent, if set)."""
        bindings: dict[str, str] = {"tool": self.name}
        if self._agent_name:
            bindings["agent"] = self._agent_name
        return get_logger(self.__class__.__module__).bind(**bindings)


def logged_tool(
    name: str, *, debug_log_args: list[str] | None = None
) -> Callable[[Callable[..., Any]], BaseTool]:
    """Like ``langchain_core.tools.tool``, but also declares a DEBUG_LOG_ARGS
    allowlist for ``ToolCallLoggingMiddleware``.

    Plain ``@tool``-decorated functions produce a pydantic ``StructuredTool``
    that -- unlike ``X2ATool`` subclasses -- can't carry a class-level
    ``DEBUG_LOG_ARGS`` attribute (pydantic rejects the unknown field). They
    can, however, carry it in the ``metadata`` dict that ``BaseTool`` already
    declares, which is what ``ToolCallLoggingMiddleware`` falls back to.

    Usage::

        @logged_tool("add_checklist_task", debug_log_args=["source_path"])
        def add_task_tool(source_path: str, content: str) -> str:
            ...

    is equivalent to::

        @tool("add_checklist_task")
        def add_task_tool(source_path: str, content: str) -> str:
            ...

        add_task_tool.metadata = {"DEBUG_LOG_ARGS": ["source_path"]}

    Omitting ``debug_log_args`` fails closed -- nothing is logged besides
    name/duration, same as a tool that declares no allowlist at all.
    """

    def decorator(func: Callable[..., Any]) -> BaseTool:
        wrapped = tool(name)(func)
        wrapped.metadata = {"DEBUG_LOG_ARGS": debug_log_args or []}
        return wrapped

    return decorator
