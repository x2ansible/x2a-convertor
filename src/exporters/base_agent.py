"""Base agent class for Chef to Ansible migration.

Provides common functionality for all migration agents.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, ClassVar

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from src.exporters.state import ChefState
from src.model import get_model
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.language_models import BaseLanguageModel

logger = get_logger(__name__)


class BaseAgent(ABC):
    """Base class for migration agents.

    Provides common functionality:
    - Model initialization
    - React agent creation with tools derived from state
    - Tool management (base tools + checklist tools)

    Subclasses should:
    - Define BASE_TOOLS as a list of tool factory lambdas
    - Implement __call__(state: ChefState) -> ChefState
    """

    # Subclasses should override this with their specific tools
    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = []

    @abstractmethod
    def __call__(self, state: ChefState) -> ChefState:
        """Process the state through this agent.

        Args:
            state: ChefState to process

        Returns:
            Updated ChefState
        """
        ...

    def __init__(self, model: "BaseLanguageModel | None" = None):
        """Initialize agent with optional model.

        Args:
            model: LLM model to use (defaults to get_model())
        """
        self.model = model or get_model()

    def _create_react_agent(self, chef_state: ChefState):
        """Create a react agent with tools derived from chef_state.

        Combines BASE_TOOLS with tools from the checklist (if present).

        Args:
            chef_state: ChefState containing checklist and other domain data

        Returns:
            Configured react agent
        """
        agent_name = self.__class__.__name__
        logger.info(f"Creating {agent_name} react agent")

        # Build tools from base + checklist
        tools = [factory() for factory in self.BASE_TOOLS]
        if chef_state.checklist is not None:
            tools.extend(chef_state.checklist.get_tools())

        return create_react_agent(model=self.model, tools=tools)  # pyrefly: ignore
