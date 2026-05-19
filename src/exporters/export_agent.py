"""Base class for all export agents.

Centralises the RULES_FILE assignment so individual export agents
inherit it instead of repeating the constant.
"""

from typing import ClassVar

from src.base_agent import BaseAgent
from src.const import EXPORT_AGENTS_FILE
from src.types.base_state import BaseState


class ExportAgent[S: BaseState](BaseAgent[S]):
    """Base class for all export agents.

    Sets RULES_FILE to EXPORT_AGENTS_FILE so every subclass
    automatically receives export-agent rules via RulesMiddleware.
    """

    RULES_FILE: ClassVar[str] = EXPORT_AGENTS_FILE
