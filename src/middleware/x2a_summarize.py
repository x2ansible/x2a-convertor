"""Middleware that summarizes non-original conversation messages when context grows too large.

Preserves the original system/user messages (tagged via additional_kwargs) verbatim
and only summarizes the tool-call/AI-response conversation that follows.
"""

from __future__ import annotations

import uuid
from functools import partial
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AnyMessage, RemoveMessage, ToolMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, get_buffer_string
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime

from prompts.get_prompt import get_prompt
from src.const import X2A_ORIGINAL_MESSAGE
from src.utils.logging import get_logger

logger = get_logger(__name__)


class X2ASummarizationMiddleware(AgentMiddleware):
    """Summarizes non-original messages when token usage exceeds a threshold.

    Original messages (tagged with X2A_ORIGINAL_MESSAGE in additional_kwargs)
    are always preserved verbatim. Only the tool-call/AI-response conversation
    is summarized into a concise action log.
    """

    def __init__(
        self,
        model: BaseChatModel,
        *,
        messages_to_keep: int = 6,
        max_tokens: int = 20_000,
        original_messages_tag: str = X2A_ORIGINAL_MESSAGE,
    ) -> None:
        self._model = model
        self._messages_to_keep = messages_to_keep
        self._max_tokens = max_tokens
        self._original_messages_tag = original_messages_tag
        self._token_counter = partial(
            count_tokens_approximately, use_usage_metadata_scaling=True
        )

    def before_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        messages: list[AnyMessage] = state["messages"]
        self._ensure_message_ids(messages)

        result = self._prepare_summarization(messages)
        if result is None:
            return None

        original, to_summarize, kept = result
        summary_text = self._create_summary(to_summarize)

        if summary_text is None:
            return None
        return self._build_result(original, summary_text, kept, len(to_summarize))

    async def abefore_model(
        self, state: Any, runtime: Runtime
    ) -> dict[str, Any] | None:
        messages: list[AnyMessage] = state["messages"]
        self._ensure_message_ids(messages)

        result = self._prepare_summarization(messages)
        if result is None:
            return None

        original, to_summarize, kept = result
        summary_text = await self._acreate_summary(to_summarize)

        if summary_text is None:
            return None

        return self._build_result(original, summary_text, kept, len(to_summarize))

    def _prepare_summarization(
        self, messages: list[AnyMessage]
    ) -> tuple[list[AnyMessage], list[AnyMessage], list[AnyMessage]] | None:
        token_count = self._token_counter(messages)
        if token_count < self._max_tokens:
            return None

        logger.info(
            "Token threshold exceeded, summarizing",
            token_count=token_count,
            max_tokens=self._max_tokens,
            message_count=len(messages),
        )

        original, non_original = self._partition_by_tag(messages)

        if not non_original:
            return None

        kept = self._select_recent_messages(non_original)
        to_summarize = non_original[: len(non_original) - len(kept)]

        if not to_summarize:
            return None

        return original, to_summarize, kept

    def _partition_by_tag(
        self, messages: list[AnyMessage]
    ) -> tuple[list[AnyMessage], list[AnyMessage]]:
        original = [
            msg
            for msg in messages
            if getattr(msg, "additional_kwargs", {}).get(self._original_messages_tag)
        ]
        non_original = [
            msg
            for msg in messages
            if not getattr(msg, "additional_kwargs", {}).get(
                self._original_messages_tag
            )
        ]
        return original, non_original

    def _build_result(
        self,
        original: list[AnyMessage],
        summary_text: str,
        kept: list[AnyMessage],
        summarized_count: int,
    ) -> dict[str, Any]:
        summary_message = HumanMessage(
            content=f"Summary of previous actions:\n\n{summary_text}",
            id=str(uuid.uuid4()),
        )

        logger.info(
            "Summarization complete",
            original_count=len(original),
            summarized_count=summarized_count,
            kept_count=len(kept),
        )

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *original,
                summary_message,
                *kept,
            ]
        }

    def _select_recent_messages(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        if len(messages) <= self._messages_to_keep:
            return list(messages)

        cutoff = len(messages) - self._messages_to_keep
        cutoff = self._adjust_cutoff_for_tool_pairs(messages, cutoff)
        return messages[cutoff:]

    def _create_summary(self, messages: list[AnyMessage]) -> str | None:
        if not messages:
            return "No previous actions to summarize."

        prompt_text = self._build_summary_prompt(messages)

        try:
            response = self._model.invoke(prompt_text)
            return response.text.strip()
        except Exception as e:
            logger.error(
                "Summarization failed, keeping original messages", error=str(e)
            )
            return None

    async def _acreate_summary(self, messages: list[AnyMessage]) -> str | None:
        if not messages:
            return "No previous actions to summarize."

        prompt_text = self._build_summary_prompt(messages)

        try:
            response = await self._model.ainvoke(prompt_text)
            return response.text.strip()
        except Exception as e:
            logger.error(
                "Summarization failed, keeping original messages", error=str(e)
            )
            return None

    def _build_summary_prompt(self, messages: list[AnyMessage]) -> str:
        formatted = get_buffer_string(messages)
        prompt_template = get_prompt("x2a_summarize")
        return prompt_template.format(messages=formatted)

    @staticmethod
    def _adjust_cutoff_for_tool_pairs(messages: list[AnyMessage], cutoff: int) -> int:
        if cutoff >= len(messages):
            return cutoff

        if not isinstance(messages[cutoff], ToolMessage):
            return cutoff

        for i in range(cutoff - 1, -1, -1):
            if isinstance(messages[i], AIMessage) and getattr(
                messages[i], "tool_calls", None
            ):
                return i

        idx = cutoff
        while idx < len(messages) and isinstance(messages[idx], ToolMessage):
            idx += 1
        return idx

    @staticmethod
    def _ensure_message_ids(messages: list[AnyMessage]) -> None:
        for msg in messages:
            if msg.id is None:
                msg.id = str(uuid.uuid4())
