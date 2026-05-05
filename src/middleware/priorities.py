"""Middleware that injects agent priorities from a file into the system prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage

from prompts.get_prompt import get_prompt
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PrioritiesMiddleware(AgentMiddleware):
    """Injects priority rules from a file into the agent's conversation.

    Reads the file once during before_agent and injects the rendered
    content as a message. If the file does not exist, the middleware
    is a no-op.
    """

    def __init__(self, file_path: str) -> None:
        self._file_path = file_path

    def _load_and_render(self) -> dict[str, Any] | None:
        """Read priorities file and render through the Jinja2 template."""
        path = Path(self._file_path)
        if not path.is_file():
            logger.debug(
                "Priorities file not found, skipping injection",
                file_path=self._file_path,
            )
            return None

        try:
            text = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(
                "Failed to read priorities file, skipping injection",
                file_path=self._file_path,
                error=str(exc),
            )
            return None

        if not text:
            logger.debug(
                "Priorities file is empty, skipping injection",
                file_path=self._file_path,
            )
            return None

        template = get_prompt("middleware_priorities")
        rendered = template.format(priorities_content=text)

        logger.debug(
            "Loaded priorities file",
            file_path=self._file_path,
            content_length=len(text),
        )

        return {"messages": [HumanMessage(content=rendered)]}

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Read priorities file and inject as a message at agent startup."""
        return self._load_and_render()

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async variant -- delegates to sync file read."""
        return self._load_and_render()
