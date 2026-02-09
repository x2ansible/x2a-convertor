"""Base tool class with agent-aware structured logging."""

from __future__ import annotations

from langchain_core.tools import BaseTool
from pydantic import PrivateAttr

from src.utils.logging import get_logger


class X2ATool(BaseTool):
    """Base class for all x2a-convertor tools.

    Provides agent-aware logging via a ``log`` property that automatically
    includes the tool name and, when set, the invoking agent name.

    Usage inside a tool subclass::

        slog = self.log.bind(file_path=path)
        slog.info("wrote file")
    """

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
