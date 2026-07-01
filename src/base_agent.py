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
from src.middleware.goal_validation import GoalValidationMiddleware
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
    GOAL: ClassVar[str | None] = None
    MAX_TOKENS_BEFORE_SUMMARY: ClassVar[int] = 20000
    MESSAGES_TO_KEEP: ClassVar[int] = 20

    STRUCTURED_OUTPUT_INSTRUCTION = """CRITICAL INSTRUCTION - STRUCTURED OUTPUT REQUIRED:

You MUST use the structured output tool that has been provided to you. This is NOT optional.

DO NOT write a text response. DO NOT write explanatory text. DO NOT write conversational output.

REQUIRED ACTION:
1. Analyze the input according to the instructions
2. IMMEDIATELY call the structured output tool with your analysis
3. Ensure the tool call includes ALL required fields from the schema

The structured output tool is the ONLY way to respond. Any text response will be rejected.

If you are uncertain about any field, make your best analysis and include it in the tool call.
If a field is optional and you have no data, you may omit it or use null.
But you MUST call the tool - there is no alternative response format."""

    STRUCTURED_ERROR = """You failed to generate a valid structured output. The validation error was:

{validation_error}

Schema required: {schema_name}

Your response content was:
{ai_message_content}

Common issues:
1. You returned a simple value (string, number, boolean) instead of a JSON object
2. You're missing required fields defined in the schema
3. Field types don't match the schema (e.g., string instead of list)
4. Field names don't match exactly (check spelling and case)

Please provide a complete response that:
- Returns a valid JSON object (not a primitive value)
- Includes ALL required fields from the {schema_name} schema
- Uses correct data types for each field
- Follows the exact field names specified in the schema

Retry your response now, ensuring it matches the schema structure exactly."""

    def __init__(self, model: BaseChatModel | None = None):
        self.model = model or get_model()
        self.agent_id = str(uuid.uuid4())
        self._log = get_logger(self.__class__.__module__).bind(
            agent=self.agent_name, agent_id=self.agent_id
        )
        # Cache middleware instances to preserve state (e.g., retry_count)
        self._middleware_cache: list[AgentMiddleware] | None = None

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

        When GOAL is set, GoalValidationMiddleware is added first
        to validate goal achievement and retry if necessary.
        When RULES_FILE is set, RulesMiddleware is included
        to inject rules as a message at agent startup.
        When JSON_LINES is configured, AgentDumpMiddleware is included
        to dump messages for debugging.

        Middleware instances are cached to preserve state across invocations
        (e.g., retry_count in GoalValidationMiddleware).
        """
        # Return cached middleware if available
        if self._middleware_cache is not None:
            return self._middleware_cache

        # Build middleware stack once
        stack: list[AgentMiddleware] = []
        if self.GOAL:
            stack.append(GoalValidationMiddleware(self.GOAL, agent=self))
        if self.RULES_FILE:
            stack.append(RulesMiddleware(self.RULES_FILE))
        stack.append(
            SummarizationMiddleware(
                model=self.model,
                max_tokens_before_summary=self.MAX_TOKENS_BEFORE_SUMMARY,
                messages_to_keep=self.MESSAGES_TO_KEEP,
            ),
        )
        settings = get_settings()
        if settings.logging.json_lines:
            stack.append(AgentDumpMiddleware(self.agent_name, self.agent_id))

        # Cache for reuse
        self._middleware_cache = stack
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
        max_retries: int = 3,
        **kwargs,
    ) -> Any:
        """Invoke model with structured output schema.

        Returns the parsed schema instance, or None if validation fails.

        The reason why it's an agent it to be able to iterate if the model cannot do it in the first run.

        Args:
            schema: Pydantic model schema for structured output
            messages: Messages to send to the model
            metrics: Optional metrics collector
            middleware: Middleware stack to use. If None, uses self.middleware().
                        Pass [] to bypass middleware (e.g., for validation to avoid recursion)
            **kwargs: Additional arguments (e.g., tools=[...])
        """
        if max_retries <= 0:
            max_retries = 1

        current_messages = [
            {"role": "system", "content": self.STRUCTURED_OUTPUT_INSTRUCTION},
            *messages,
        ]

        structured_model = self.model.with_structured_output(
            schema, method="function_calling", include_raw=True
        )
        for attempt in range(max_retries):
            try:
                result = structured_model.invoke(
                    current_messages,
                    get_runnable_config(),
                )

                if (
                    metrics
                    and isinstance(result, dict)
                    and isinstance(result.get("raw"), AIMessage)
                    and hasattr(result["raw"], "usage_metadata")
                    and result["raw"].usage_metadata
                ):
                    input_tokens = result["raw"].usage_metadata.get("input_tokens", 0)
                    output_tokens = result["raw"].usage_metadata.get("output_tokens", 0)
                    metrics.record_tokens(input_tokens, output_tokens)

                parsed_result = (
                    result.get("parsed") if isinstance(result, dict) else result
                )

                if parsed_result is None:
                    schema_name = getattr(schema, "__name__", str(schema))
                    raise StructuredOutputValidationError(
                        tool_name=schema_name,
                        source=ValueError(
                            f"Model returned None instead of calling {schema_name} tool"
                        ),
                        ai_message=AIMessage(content="No tool call made"),
                    )

                return parsed_result

            except StructuredOutputValidationError as e:
                is_last_attempt = attempt == max_retries - 1
                schema_name = getattr(schema, "__name__", str(schema))
                ai_content = (
                    str(e.ai_message.content)
                    if hasattr(e, "ai_message") and e.ai_message
                    else "No content"
                )

                self._log.error(
                    f"Structured output validation failed for schema '{schema_name}' "
                    f"(attempt {attempt + 1}/{max_retries}): {e.source}",
                    tool_name=getattr(e, "tool_name", None),
                    ai_message_content=ai_content,
                )

                if is_last_attempt:
                    return None

                error_message = self.STRUCTURED_ERROR.format(
                    validation_error=str(e.args[0]) if e.args else str(e),
                    schema_name=schema_name,
                    ai_message_content=ai_content,
                )
                current_messages.append({"role": "user", "content": error_message})
                continue

        return None

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

        if isinstance(result, AIMessage) and hasattr(result, "text"):
            return result.text
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
