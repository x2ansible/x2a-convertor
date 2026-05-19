"""Base class for all input/analysis agents.

Centralises the RULES_FILE assignment so individual input agents
inherit it instead of repeating the constant.
"""

from typing import ClassVar

from src.base_agent import BaseAgent
from src.const import INPUT_AGENTS_FILE
from src.types.base_state import BaseState


class InputAgent[S: BaseState](BaseAgent[S]):
    """Base class for all input/analysis agents.

    Sets RULES_FILE to INPUT_AGENTS_FILE so every subclass
    automatically receives input-agent rules via RulesMiddleware.
    """

    RULES_FILE: ClassVar[str] = INPUT_AGENTS_FILE
