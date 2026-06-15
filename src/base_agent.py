"""Generic base agent for all migration workflow phases.

Provides a reusable foundation with:
- Automatic telemetry wrapping via __call__ -> execute()
- Declarative tool configuration via BASE_TOOLS
- State-derived tool hook via extra_tools_from_state()
- LLM invocation helpers (react, structured, direct)
"""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.structured_output import StructuredOutputValidationError
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from src.config import get_settings
from src.middleware.agent_dump import AgentDumpMiddleware
from src.middleware.rules import RulesMiddleware
from src.model import get_model, get_runnable_config, report_tool_calls
from src.types.base_state import BaseState
from src.types.telemetry import AgentMetrics, telemetry_context
from src.utils.logging import get_logger
from tools.base_tool import X2ATool


class BaseAgent[S: BaseState](ABC):
    """Generic base class for all migration agents.

    Subclasses should:
    - Define BASE_TOOLS as a list of tool factory callables
    - Implement execute(state, metrics) with core logic
    - Optionally override extra_tools_from_state() for state-derived tools
    - Optionally override middleware() to customise conversation compaction
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = []
    _NAME: ClassVar[str | None] = None
    RULES_FILE: ClassVar[str | None] = None

    def __init__(self, model: BaseChatModel | None = None):
        self.model = model or get_model()
        self.agent_id = str(uuid.uuid4())
        self._log = get_logger(self.__class__.__module__).bind(
            agent=self.agent_name, agent_id=self.agent_id
        )

    @property
    def agent_name(self) -> str:
        if self._NAME:
            return self._NAME
        return self.__class__.__name__

    def extra_tools_from_state(self, state: S) -> list[BaseTool]:
        """Hook for state-derived tools (e.g., checklist tools).

        Override in subclasses that need dynamic tools based on state.
        """
        return []

    def middleware(self) -> list:
        """Return middleware list for conversation compaction.

        When RULES_FILE is set, RulesMiddleware is included
        to inject rules as a message at agent startup.
        When JSON_LINES is configured, AgentDumpMiddleware is included
        to dump messages for debugging.
        """
        stack: list[AgentMiddleware] = []
        if self.RULES_FILE:
            stack.append(RulesMiddleware(self.RULES_FILE))
        stack.append(
            SummarizationMiddleware(
                model=self.model,
                max_tokens_before_summary=20000,
                messages_to_keep=20,
            ),
        )
        settings = get_settings()
        if settings.logging.json_lines:
            stack.append(AgentDumpMiddleware(self.agent_name, self.agent_id))
        return stack

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

    def _get_tools(self, state: S) -> list[BaseTool]:
        """Build tools from BASE_TOOLS and state, binding agent name on X2ATool instances."""
        tools = [factory() for factory in self.BASE_TOOLS]
        tools.extend(self.extra_tools_from_state(state))
        return [
            tool.with_agent(self.agent_name) if isinstance(tool, X2ATool) else tool
            for tool in tools
        ]

    def _extract_token_usage(self, result: dict) -> tuple[int, int]:
        """Extract total input and output tokens from AIMessage objects.

        Returns:
            Tuple of (input_tokens, output_tokens)
        """
        input_tokens = 0
        output_tokens = 0

        for msg in result.get("messages", []):
            if not isinstance(msg, AIMessage):
                continue
            if not hasattr(msg, "usage_metadata") or not msg.usage_metadata:
                continue

            input_tokens += msg.usage_metadata.get("input_tokens", 0)
            output_tokens += msg.usage_metadata.get("output_tokens", 0)

        return input_tokens, output_tokens

    def invoke_react(
        self,
        state: S,
        messages: list[dict[str, str]],
        metrics: AgentMetrics | None = None,
    ) -> dict:
        """Build tools, create ReAct agent, invoke, and report tool calls.

        Returns the raw result dict from the agent.
        """
        tools = self._get_tools(state)

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
            input_tokens, output_tokens = self._extract_token_usage(result)
            metrics.record_tokens(input_tokens, output_tokens)

        return result

    def invoke_structured(
        self,
        schema: type,
        messages: Any,
        metrics: AgentMetrics | None = None,
    ) -> Any:
        """Invoke model with structured output schema.

        Returns the parsed schema instance, or None if validation fails.

        The reason why it's an agent it to be able to iterate if the model cannot do it in the first run.
        """
        agent = create_agent(
            model=self.model,
            middleware=self.middleware(),
            response_format=schema,
        )

        try:
            result = agent.invoke(
                {"messages": messages},
                get_runnable_config(),
            )

        except StructuredOutputValidationError as e:
            schema_name = getattr(schema, "__name__", str(schema))
            self._log.error(
                f"Structured output validation failed for schema '{schema_name}': {e.source}",
                tool_name=e.tool_name,
                ai_message_content=str(e.ai_message.content),
            )
            return None

        if metrics:
            input_tokens, output_tokens = self._extract_token_usage(result)
            metrics.record_tokens(input_tokens, output_tokens)

        return result.get("structured_response")

    def invoke_llm(
        self,
        messages: list[dict[str, str]],
        metrics: AgentMetrics | None = None,
    ) -> str:
        """Direct model invocation, returns content string."""
        result = self.model.invoke(messages, config=get_runnable_config())
        if (
            metrics
            and isinstance(result, AIMessage)
            and hasattr(result, "usage_metadata")
            and result.usage_metadata
        ):
            input_tokens = result.usage_metadata.get("input_tokens", 0)
            output_tokens = result.usage_metadata.get("output_tokens", 0)
            metrics.record_tokens(input_tokens, output_tokens)

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
