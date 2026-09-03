"""Middleware that records LLM token usage into per-invocation AgentMetrics.

Mirrors deepagents' CostTrackingMiddleware: it wraps every model call made
within the agent's graph via wrap_model_call/awrap_model_call and records
usage against the AgentMetrics carried in the per-invocation
AgentRuntimeContext, so tokens are captured at the source regardless of
which node triggered the call -- without every call site having to
remember to record them manually.

This middleware is intentionally a pure observer:
- It calls the handler exactly once and never retries, short-circuits, or
  rewrites the request/response.
- It never raises from the handler call itself; a bug in metrics recording
  must never break agent execution, so recording is wrapped defensively.
- It keeps no state on self; everything it needs is read per-call from
  request.runtime.context, so it is safe to share/cache across
  invocations like the other middleware.

It should be placed last in the middleware stack (closest to the actual
model call) so it always measures the real call and is never skipped by
an earlier middleware short-circuiting.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage

from src.types.telemetry import AgentRuntimeContext
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TelemetryMiddleware(AgentMiddleware):
    """Records token usage for every model call in this invocation into AgentMetrics."""

    name = "Telemetry"

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        response = handler(request)
        self._record(request, response)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        response = await handler(request)
        self._record(request, response)
        return response

    @staticmethod
    def _record(request: ModelRequest, response: ModelResponse) -> None:
        try:
            metrics = AgentRuntimeContext.metrics_from(request.runtime)
            if metrics is None:
                return
            for message in response.result:
                if not isinstance(message, AIMessage):
                    continue
                usage = getattr(message, "usage_metadata", None)
                if not usage:
                    continue
                metrics.record_tokens(
                    usage.get("input_tokens", 0), usage.get("output_tokens", 0)
                )
        except Exception as e:
            logger.error("Failed to record telemetry for model call", error=str(e))
