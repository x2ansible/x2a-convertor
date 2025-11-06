import os
from collections import Counter
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.utils.config import get_config_int
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DebugToolEventHandler(BaseCallbackHandler):
    """Callback handler to log tool execution events"""

    def __init__(self):
        super().__init__()
        self._tool_names = {}  # Maps run_id to tool_name
        self._logger = get_logger(__name__)

    def get_tool_name(self, run_id):
        """Get and remove tool name from cache"""
        return self._tool_names.pop(run_id, "unknown") if run_id else "unknown"

    def on_tool_start(self, serialized, input_str, **kwargs):
        tool_name = serialized.get("name", "unknown")
        run_id = kwargs.get("run_id")
        if run_id:
            self._tool_names[run_id] = tool_name
        self._logger.debug("Tool Started", tool_name=tool_name, input=input_str)

    def on_tool_end(self, output, **kwargs):
        tool_name = self.get_tool_name(kwargs.get("run_id"))
        output_str = str(output)[:30]
        self._logger.info("Tool Ended", tool_name=tool_name, output=output_str)

    def on_tool_error(self, error, **kwargs):
        tool_name = self.get_tool_name(kwargs.get("run_id"))
        error_str = str(error)[:30]
        self._logger.error("Tool Error", tool_name=tool_name, error=error_str)


class ToolCallCounter(Counter):
    def to_string(self) -> str:
        """Returns compact string representation"""
        return ", ".join(f"{tool}: {count} calls" for tool, count in self.items())

    def to_pretty_string(self) -> str:
        """Returns formatted string representation"""
        report_lines = [f"{tool}: {count} calls" for tool, count in self.items()]
        return "Tool calls:\n\t -" + "\n\t- ".join(report_lines)


def report_tool_calls(state: dict[str, Any]) -> ToolCallCounter:
    messages = state.get("messages", [])
    tool_call_counts = ToolCallCounter()

    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_name = (
                    tool_call.get("name")
                    if isinstance(tool_call, dict)
                    else tool_call.name
                )
                tool_call_counts[tool_name] += 1

    return tool_call_counts


def get_last_ai_message(state: dict[str, Any]):
    messages = state.get("messages", [])

    last_ai_message = next(
        filter(lambda msg: isinstance(msg, AIMessage), reversed(messages)), None
    )

    return last_ai_message


def get_runnable_config() -> RunnableConfig:
    """Get RunnableConfig dict with recursion limit from environment"""
    return {
        "recursion_limit": get_config_int("RECURSION_LIMIT"),
        "callbacks": [DebugToolEventHandler()],
    }


def get_model() -> BaseChatModel:
    """Initialize and return the configured language model"""
    model_name = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    logger.info(f"Initializing model: {model_name}")

    kwargs: dict[str, Any] = {
        "max_tokens": int(os.getenv("MAX_TOKENS", "8192")),
        "temperature": float(os.getenv("TEMPERATURE", "0.1")),
    }

    reasoning_effort = os.getenv("REASONING_EFFORT", None)
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort

    logger.debug(f"Model parameters: {kwargs}")

    # Default
    provider = "openai"

    # If AWS_BEARER_TOKEN_BEDROCK is set, use the AWS Bedrock
    if os.getenv("AWS_BEARER_TOKEN_BEDROCK"):
        provider = "bedrock_converse"
        region_name = os.getenv("AWS_REGION", "eu-west-2")
        kwargs["region_name"] = region_name
        logger.debug(f"AWS_REGION: {region_name}")

    # If the provider is OpenAI, use the specific OpenAI endpoint information
    if provider == "openai":
        kwargs["base_url"] = os.getenv("OPENAI_API_BASE")
        kwargs["api_key"] = os.getenv("OPENAI_API_KEY", "not-needed")
        if not kwargs["base_url"]:
            logger.warning("OPENAI_API_BASE is not set")
        logger.debug(f"OPENAI_API_BASE: {kwargs['base_url']}")

    kwargs["model_provider"] = provider
    logger.info(
        f"Using the '{provider}' provider with the '{model_name}' model for accessing LLM"
    )

    return init_chat_model(
        model_name,
        **kwargs,
    )
