import os
import logging
from collections import Counter
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from src.utils.config import RECURSION_LIMIT

logger = logging.getLogger(__name__)


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
    return {"recursion_limit": RECURSION_LIMIT}


def get_model() -> BaseChatModel:
    """Initialize and return the configured language model"""
    model_name = os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022")
    logger.info(f"Initializing model: {model_name}")
    logger.debug(f"OPENAI_API_BASE: {os.getenv('OPENAI_API_BASE')}")
    logger.debug(f"MAX_TOKENS: {os.getenv('MAX_TOKENS')}")
    logger.debug(f"TEMPERATURE: {os.getenv('TEMPERATURE')}")

    # Handle OpenAI-compatible local APIs
    if os.getenv("OPENAI_API_BASE"):
        return init_chat_model(
            model_name,
            base_url=os.getenv("OPENAI_API_BASE"),
            model_provider="openai",
            api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
            max_tokens=int(os.getenv("MAX_TOKENS", "8192")),
            temperature=float(os.getenv("TEMPERATURE", "0.1")),
        )

    return init_chat_model(model_name)
