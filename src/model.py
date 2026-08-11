from collections import Counter
from typing import Any

import httpx
import litellm
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import RunnableConfig
from langchain_litellm import ChatLiteLLMRouter

from src.config import get_settings
from src.config.settings import LLMSettings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FinishReasonCallbackHandler(BaseCallbackHandler):
    """Log a warning when the model is cut off by its output token limit."""

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generation_list in response.generations:
            for generation in generation_list:
                info = generation.generation_info or {}
                msg = getattr(generation, "message", None)
                msg_metadata = getattr(msg, "response_metadata", {}) or {}
                if info.get("finish_reason") == "length":
                    usage = getattr(msg, "usage_metadata", None) or {}
                    model_name = msg_metadata.get("model_name", "unknown")
                    logger.warning(
                        "Model hit the output token limit",
                        model=model_name,
                        input_tokens=usage.get("input_tokens", "unknown"),
                        output_tokens=usage.get("output_tokens", "unknown"),
                        suggestion="Reduce the input size or increase MAX_TOKENS.",
                    )


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
    """Get RunnableConfig dict with recursion limit from settings"""
    settings = get_settings()
    return {
        "recursion_limit": settings.processing.recursion_limit,
        "callbacks": [DebugToolEventHandler(), FinishReasonCallbackHandler()],
    }


def _build_router(llm_settings: LLMSettings) -> litellm.Router:
    """Build a LiteLLM Router from settings"""
    timeout = httpx.Timeout(
        connect=llm_settings.connect_timeout,
        read=llm_settings.read_timeout,
        write=llm_settings.read_timeout,
        pool=llm_settings.connect_timeout,
    )

    litellm_params: dict[str, Any] = {
        "model": llm_settings.model,
        "timeout": timeout,
        "max_tokens": llm_settings.max_tokens,
        "temperature": llm_settings.temperature,
    }

    if llm_settings.reasoning_effort is not None:
        litellm_params["reasoning_effort"] = llm_settings.reasoning_effort

    return litellm.Router(
        model_list=[
            {
                "model_name": llm_settings.model,
                "litellm_params": litellm_params,
            }
        ],
        num_retries=llm_settings.max_retries,
    )


def get_model() -> BaseChatModel:
    """Initialize and return the configured language model via LiteLLM Router.

    Model strings follow LiteLLM format: provider/model-name
      openai/gpt-4o
      anthropic/claude-3-5-sonnet-20241022
      bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0
      gemini/gemini-1.5-pro
      vertex_ai/gemini-1.5-pro

    All provider credentials (OPENAI_API_KEY, OPENAI_API_BASE, ANTHROPIC_API_KEY,
    AWS_ACCESS_KEY_ID, etc.) are read directly from the environment by LiteLLM.
    """
    llm_settings = get_settings().llm

    kwargs: dict[str, Any] = {
        "router": _build_router(llm_settings),
    }

    if llm_settings.rate_limit_requests:
        kwargs["rate_limiter"] = InMemoryRateLimiter(
            requests_per_second=llm_settings.rate_limit_requests,
            check_every_n_seconds=0.2,
            max_bucket_size=10,
        )

    chat_model = ChatLiteLLMRouter(**kwargs)

    model_name, provider, *_ = litellm.get_llm_provider(chat_model.model)
    log_kwargs: dict[str, Any] = {
        "provider": provider,
        "model": model_name,
        "max_tokens": llm_settings.max_tokens,
        "temperature": llm_settings.temperature,
        "max_retries": llm_settings.max_retries,
        "connect_timeout": llm_settings.connect_timeout,
        "read_timeout": llm_settings.read_timeout,
        "rate_limit_requests_per_second": llm_settings.rate_limit_requests,
    }
    if llm_settings.reasoning_effort is not None:
        log_kwargs["reasoning_effort"] = llm_settings.reasoning_effort
    logger.info("LLM initialized", **log_kwargs)

    return chat_model
