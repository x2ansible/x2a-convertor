from collections import Counter
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import RunnableConfig
from pydantic import SecretStr

from src.config import get_settings
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
    """Get RunnableConfig dict with recursion limit from settings"""
    settings = get_settings()
    return {
        "recursion_limit": settings.processing.recursion_limit,
        "callbacks": [DebugToolEventHandler()],
    }


def get_model() -> BaseChatModel:
    """Initialize and return the configured language model"""
    settings = get_settings()

    model_name = settings.llm.model
    logger.info(f"Initializing model: {model_name}")

    kwargs: dict[str, Any] = {
        "max_tokens": settings.llm.max_tokens,
        "temperature": settings.llm.temperature,
    }

    if settings.llm.reasoning_effort:
        kwargs["reasoning_effort"] = settings.llm.reasoning_effort

    # Configure rate limiter if enabled
    if settings.llm.rate_limit_requests:
        requests_per_second = settings.llm.rate_limit_requests
        rate_limiter = InMemoryRateLimiter(
            requests_per_second=requests_per_second,
            check_every_n_seconds=0.2,
            max_bucket_size=10,
        )
        kwargs["rate_limiter"] = rate_limiter
        logger.info(f"Rate limiter enabled: {requests_per_second} requests/second")

    logger.debug(f"Model parameters: {kwargs}")

    # Default
    provider = "openai"

    # If AWS_BEARER_TOKEN_BEDROCK is set, use the AWS Bedrock
    if settings.aws.bearer_token_bedrock or settings.aws.access_key_id:
        provider = "bedrock_converse"
        region_name = settings.aws.region
        kwargs["region_name"] = region_name
        logger.debug(f"AWS_REGION: {region_name}")

        # If we have access keys, pass them as SecretStr
        if settings.aws.access_key_id and settings.aws.secret_access_key:
            access_key_id = settings.aws.access_key_id.get_secret_value()
            secret_access_key = settings.aws.secret_access_key.get_secret_value()

            # Debug logging to verify credentials are loaded
            logger.debug(f"AWS_ACCESS_KEY_ID length: {len(access_key_id)}")
            logger.debug(f"AWS_SECRET_ACCESS_KEY length: {len(secret_access_key)}")
            logger.debug(
                f"AWS_ACCESS_KEY_ID starts with: {access_key_id[:4] if len(access_key_id) >= 4 else 'N/A'}"
            )

            # Wrap credentials in SecretStr as required by ChatBedrockConverse
            kwargs["aws_access_key_id"] = SecretStr(access_key_id)
            kwargs["aws_secret_access_key"] = SecretStr(secret_access_key)

            # Include session token if present (for temporary credentials)
            if settings.aws.session_token:
                session_token = settings.aws.session_token.get_secret_value()
                kwargs["aws_session_token"] = SecretStr(session_token)
                logger.debug(f"AWS_SESSION_TOKEN length: {len(session_token)}")

            logger.info("Using AWS credentials from environment with Bedrock provider")

    # If the provider is OpenAI, use the specific OpenAI endpoint information
    if provider == "openai":
        kwargs["base_url"] = settings.openai.api_base
        kwargs["api_key"] = settings.openai.api_key.get_secret_value()
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
