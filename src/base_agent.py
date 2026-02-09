"""Generic base agent for all migration workflow phases.

Provides a reusable foundation with:
- Automatic telemetry wrapping via __call__ -> execute()
- Declarative tool configuration via BASE_TOOLS
- State-derived tool hook via extra_tools_from_state()
- LLM invocation helpers (react, structured, direct)
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from src.model import get_model, get_runnable_config, report_tool_calls
from src.types.base_state import BaseState
from src.types.telemetry import AgentMetrics, telemetry_context
from src.utils.logging import get_logger


class BaseAgent[S: BaseState](ABC):
    """Generic base class for all migration agents.

    Subclasses should:
    - Define BASE_TOOLS as a list of tool factory callables
    - Implement execute(state, metrics) with core logic
    - Optionally override extra_tools_from_state() for state-derived tools
    - Optionally override middleware() to customise conversation compaction
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = []

    def __init__(self, model: BaseChatModel | None = None):
        self.model = model or get_model()
        self._log = get_logger(self.__class__.__module__).bind(agent=self.agent_name)

    @property
    def agent_name(self) -> str:
        return self.__class__.__name__

    def extra_tools_from_state(self, state: S) -> list[BaseTool]:
        """Hook for state-derived tools (e.g., checklist tools).

        Override in subclasses that need dynamic tools based on state.
        """
        return []

    def middleware(self) -> list:
        """Return middleware list for conversation compaction."""
        return [
            SummarizationMiddleware(
                model=self.model,
                max_tokens_before_summary=20000,
                messages_to_keep=20,
            ),
        ]

    def __call__(self, state: S) -> S:
        """Entry point. Wraps execute() with automatic telemetry + logging."""
        self._log.info("Starting execution")
        with telemetry_context(state.telemetry, self.agent_name) as metrics:
            result = self.execute(state, metrics)
        self._log.info("Execution completed")
        return result

    @abstractmethod
    def execute(self, state: S, metrics: AgentMetrics | None) -> S:
        """Core logic. Subclasses implement this instead of __call__."""
        ...

    # --- Invocation Helpers ---

    def invoke_react(
        self,
        state: S,
        messages: list[dict[str, str]],
        metrics: AgentMetrics | None = None,
    ) -> dict:
        """Build tools, create ReAct agent, invoke, and report tool calls.

        Returns the raw result dict from the agent.
        """
        tools = [factory() for factory in self.BASE_TOOLS]
        tools.extend(self.extra_tools_from_state(state))

        agent = create_agent(
            model=self.model, middleware=self.middleware(), tools=tools
        )

        result = agent.invoke(
            {"messages": messages},
            get_runnable_config(),
        )

        tool_calls = report_tool_calls(result)
        self._log.info(f"Tool calls: {tool_calls.to_string()}")

        if metrics:
            metrics.record_tool_calls(tool_calls)

        return result

    def invoke_structured(
        self,
        schema: type,
        messages: Any,
        metrics: AgentMetrics | None = None,
    ) -> Any:
        """Invoke model with structured output schema.

        Returns the parsed schema instance.
        """
        structured_model = self.model.with_structured_output(schema)
        return structured_model.invoke(messages, config=get_runnable_config())

    def invoke_llm(
        self,
        messages: list[dict[str, str]],
        metrics: AgentMetrics | None = None,
    ) -> str:
        """Direct model invocation, returns content string."""
        result = self.model.invoke(messages, config=get_runnable_config())
        if isinstance(result.content, str):
            return result.content
        return str(result.content)

    @staticmethod
    def get_last_ai_message(result: dict) -> AIMessage | None:
        """Extract last AI message from agent result dict."""
        messages = result.get("messages", [])
        return next(
            filter(lambda msg: isinstance(msg, AIMessage), reversed(messages)),
            None,
        )
