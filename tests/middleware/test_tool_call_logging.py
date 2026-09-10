"""Tests for ToolCallLoggingMiddleware."""

import asyncio
from typing import ClassVar, cast

import pytest
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.messages.tool import ToolCall
from langgraph.prebuilt.tool_node import ToolRuntime

from src.middleware.tool_call_logging import ToolCallLoggingMiddleware
from tools.base_tool import X2ATool


class ToolWithDebugArgs(X2ATool):
    name: str = "with_debug_args"
    description: str = "test tool"
    DEBUG_LOG_ARGS: ClassVar[list[str]] = ["file_path"]

    def _run(self, file_path: str, content: str) -> str:
        return "ok"


class ToolWithoutDebugArgs(X2ATool):
    name: str = "without_debug_args"
    description: str = "test tool"

    def _run(self, first: str, second: str) -> str:
        return "ok"


class ToolWithEmptyDebugArgs(X2ATool):
    name: str = "with_empty_debug_args"
    description: str = "test tool"
    DEBUG_LOG_ARGS: ClassVar[list[str]] = []

    def _run(self, file_path: str) -> str:
        return "ok"


def _make_request(tool: X2ATool, args: dict) -> ToolCallRequest:
    tool_call = cast(
        ToolCall,
        {"name": tool.name, "args": args, "id": "call-1", "type": "tool_call"},
    )
    return ToolCallRequest(
        tool_call=tool_call,
        tool=tool,
        state=None,
        runtime=cast(ToolRuntime, None),
    )


class TestToolCallLoggingMiddleware:
    def test_wrap_tool_call_returns_handler_result(self):
        middleware = ToolCallLoggingMiddleware()
        request = _make_request(
            ToolWithDebugArgs(), {"file_path": "a.yml", "content": "big"}
        )
        expected = ToolMessage(content="ok", tool_call_id="call-1")

        result = middleware.wrap_tool_call(request, lambda _req: expected)

        assert result is expected

    def test_select_args_restricted_to_debug_log_args(self):
        request = _make_request(
            ToolWithDebugArgs(), {"file_path": "a.yml", "content": "big"}
        )

        selected = ToolCallLoggingMiddleware._select_args(request)

        assert selected == {"file_path": "a.yml"}

    def test_select_args_empty_when_undeclared(self):
        request = _make_request(
            ToolWithoutDebugArgs(), {"first": "one", "second": "two"}
        )

        selected = ToolCallLoggingMiddleware._select_args(request)

        assert selected == {}

    def test_select_args_empty_when_tool_missing_debug_log_args_attr(self):
        """Plain @tool-decorated helpers (not X2ATool) fail closed too."""

        class PlainToolStub:
            name = "plain_tool"

        tool_call = cast(
            ToolCall,
            {
                "name": "plain_tool",
                "args": {"first": "one"},
                "id": "call-1",
                "type": "tool_call",
            },
        )
        request = ToolCallRequest(
            tool_call=tool_call,
            tool=cast(X2ATool, PlainToolStub()),
            state=None,
            runtime=cast(ToolRuntime, None),
        )

        selected = ToolCallLoggingMiddleware._select_args(request)

        assert selected == {}

    def test_select_args_empty_when_no_args(self):
        request = _make_request(ToolWithoutDebugArgs(), {})

        selected = ToolCallLoggingMiddleware._select_args(request)

        assert selected == {}

    def test_select_args_empty_list_logs_nothing(self):
        request = _make_request(ToolWithEmptyDebugArgs(), {"file_path": "a.yml"})

        selected = ToolCallLoggingMiddleware._select_args(request)

        assert selected == {}

    def test_wrap_tool_call_logs_failure_and_reraises(self, mocker):
        mock_logger = mocker.patch("src.middleware.tool_call_logging.logger")
        middleware = ToolCallLoggingMiddleware()
        request = _make_request(ToolWithDebugArgs(), {"file_path": "a.yml"})

        def _raise(_req):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            middleware.wrap_tool_call(request, _raise)

        mock_logger.exception.assert_called_once()
        assert mock_logger.exception.call_args.args[0] == "Tool call failed"
        assert mock_logger.exception.call_args.kwargs["tool"] == "with_debug_args"

    def test_wrap_tool_call_logs_success(self, mocker):
        mock_logger = mocker.patch("src.middleware.tool_call_logging.logger")
        middleware = ToolCallLoggingMiddleware()
        request = _make_request(ToolWithDebugArgs(), {"file_path": "a.yml"})
        expected = ToolMessage(content="ok", tool_call_id="call-1")

        middleware.wrap_tool_call(request, lambda _req: expected)

        mock_logger.info.assert_called_once()
        assert mock_logger.info.call_args.args[0] == "Tool call finished"
        assert mock_logger.info.call_args.kwargs["tool"] == "with_debug_args"

    def test_wrap_tool_call_async_returns_handler_result(self):
        middleware = ToolCallLoggingMiddleware()
        request = _make_request(
            ToolWithDebugArgs(), {"file_path": "a.yml", "content": "big"}
        )
        expected = ToolMessage(content="ok", tool_call_id="call-1")

        async def _handler(_req):
            return expected

        result = asyncio.run(middleware.wrap_tool_call_async(request, _handler))

        assert result is expected

    def test_wrap_tool_call_async_logs_failure_and_reraises(self, mocker):
        mock_logger = mocker.patch("src.middleware.tool_call_logging.logger")
        middleware = ToolCallLoggingMiddleware()
        request = _make_request(ToolWithDebugArgs(), {"file_path": "a.yml"})

        async def _raise(_req):
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            asyncio.run(middleware.wrap_tool_call_async(request, _raise))

        mock_logger.exception.assert_called_once()
        assert mock_logger.exception.call_args.args[0] == "Tool call failed"
