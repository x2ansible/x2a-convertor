"""Base class for all export agents.

Centralises the RULES_FILE assignment so individual export agents
inherit it instead of repeating the constant.
"""

from typing import ClassVar

from langchain_core.tools import BaseTool

from src.base_agent import BaseAgent
from src.const import EXPORT_AGENTS_FILE
from src.exporters.state import ExportState
from src.types.base_state import BaseState


class ExportAgent[S: BaseState](BaseAgent[S]):
    """Base class for all export agents.

    Sets RULES_FILE to EXPORT_AGENTS_FILE so every subclass
    automatically receives export-agent rules via RulesMiddleware.

    Provides a default ``extra_tools_from_state`` that extracts
    checklist tools from an ``ExportState``.  When GoalValidationMiddleware
    calls back through invoke_react, state is a plain dict (LangGraph's
    internal AgentState) that cannot be converted to ExportState, so
    state-derived tools are skipped.
    """

    RULES_FILE: ClassVar[str] = EXPORT_AGENTS_FILE

    def extra_tools_from_state(self, state: S) -> list[BaseTool]:
        """Return checklist tools from the ExportState.

        GoalValidationMiddleware operates inside LangGraph's inner agent
        graph whose state is a plain dict with only ``messages``.
        The dict cannot be converted to an ExportState (required fields
        like module, path, checklist are absent), so we return an empty
        list in that case.
        """
        if not isinstance(state, ExportState):
            return []
        if state.checklist is None:
            return []
        return state.checklist.get_tools()
