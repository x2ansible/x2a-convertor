"""Tests for TelemetryMiddleware."""

import asyncio
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.middleware.telemetry import TelemetryMiddleware
from src.types.telemetry import AgentMetrics, AgentRuntimeContext


def _ai_message(input_tokens: int, output_tokens: int) -> AIMessage:
    return AIMessage(
        content="response",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


def _response(*messages):
    return Mock(result=list(messages))


def _request(metrics: AgentMetrics | None):
    runtime = Mock(context=AgentRuntimeContext(metrics=metrics))
    return Mock(runtime=runtime)


class TestWrapModelCall:
    """Tests for the synchronous wrap_model_call hook."""

    def test_records_tokens_on_metrics(self):
        metrics = AgentMetrics(name="TestAgent")
        request = _request(metrics)
        response = _response(_ai_message(100, 50))
        handler = Mock(return_value=response)

        middleware = TelemetryMiddleware()
        result = middleware.wrap_model_call(request, handler)

        assert result is response
        handler.assert_called_once_with(request)
        assert metrics.input_tokens == 100
        assert metrics.output_tokens == 50

    def test_accumulates_across_multiple_ai_messages(self):
        metrics = AgentMetrics(name="TestAgent")
        request = _request(metrics)
        response = _response(
            HumanMessage(content="not counted"),
            _ai_message(10, 5),
            ToolMessage(content="tool result", tool_call_id="1"),
        )
        handler = Mock(return_value=response)

        TelemetryMiddleware().wrap_model_call(request, handler)

        assert metrics.input_tokens == 10
        assert metrics.output_tokens == 5

    def test_noop_without_metrics_on_context(self):
        request = _request(None)
        response = _response(_ai_message(10, 5))
        handler = Mock(return_value=response)

        result = TelemetryMiddleware().wrap_model_call(request, handler)

        assert result is response
        handler.assert_called_once_with(request)

    def test_noop_when_runtime_has_no_context(self):
        request = Mock(runtime=Mock(spec=[]))
        response = _response(_ai_message(10, 5))
        handler = Mock(return_value=response)

        result = TelemetryMiddleware().wrap_model_call(request, handler)

        assert result is response

    def test_ignores_ai_message_without_usage_metadata(self):
        metrics = AgentMetrics(name="TestAgent")
        request = _request(metrics)
        response = _response(AIMessage(content="no usage info"))
        handler = Mock(return_value=response)

        TelemetryMiddleware().wrap_model_call(request, handler)

        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_never_raises_when_recording_fails(self):
        """A telemetry bug must never break agent execution."""
        request = Mock(runtime=Mock(context=object()))
        response = _response(_ai_message(10, 5))
        handler = Mock(return_value=response)

        # Should not raise even though runtime.context has no .metrics
        result = TelemetryMiddleware().wrap_model_call(request, handler)

        assert result is response

    def test_calls_handler_exactly_once(self):
        """Middleware must be a pure observer: never retries or short-circuits."""
        metrics = AgentMetrics(name="TestAgent")
        request = _request(metrics)
        response = _response(_ai_message(1, 1))
        handler = Mock(return_value=response)

        TelemetryMiddleware().wrap_model_call(request, handler)

        assert handler.call_count == 1

    def test_propagates_handler_exceptions(self):
        """Errors from the actual model call must not be swallowed."""
        request = _request(AgentMetrics(name="TestAgent"))
        handler = Mock(side_effect=RuntimeError("model failed"))

        with pytest.raises(RuntimeError, match="model failed"):
            TelemetryMiddleware().wrap_model_call(request, handler)


class TestAWrapModelCall:
    """Tests for the async awrap_model_call hook."""

    def test_records_tokens_on_metrics(self):
        metrics = AgentMetrics(name="TestAgent")
        request = _request(metrics)
        response = _response(_ai_message(20, 8))

        async def handler(_request):
            return response

        result = asyncio.run(TelemetryMiddleware().awrap_model_call(request, handler))

        assert result is response
        assert metrics.input_tokens == 20
        assert metrics.output_tokens == 8
