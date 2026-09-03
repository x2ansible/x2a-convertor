"""Tests for BaseAgent functionality."""

from typing import ClassVar, cast
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.tools import BaseTool

from src.base_agent import BaseAgent
from src.config import reset_settings
from src.middleware.goal_validation import GoalValidationMiddleware
from src.middleware.rules import RulesMiddleware
from src.middleware.telemetry import TelemetryMiddleware
from src.middleware.x2a_summarize import X2ASummarizationMiddleware
from src.types.base_state import BaseState


class ConcreteAgent(BaseAgent[BaseState]):
    """Concrete implementation of BaseAgent for testing."""

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class NamedAgent(BaseAgent[BaseState]):
    """Agent with a custom _NAME for testing."""

    _NAME = "My Custom Agent"

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class RuledAgent(BaseAgent[BaseState]):
    """Agent with RULES_FILE set for testing."""

    RULES_FILE = "INPUT-AGENTS.md"

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class GoalAgent(BaseAgent[BaseState]):
    """Agent with GOAL set for testing."""

    GOAL = "Verify output file exists"

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class TestBaseAgentName:
    """Tests for BaseAgent.agent_name property."""

    def test_agent_name_defaults_to_class_name(self):
        agent = ConcreteAgent()
        assert agent.agent_name == "ConcreteAgent"

    def test_agent_name_uses_custom_name_when_defined(self):
        agent = NamedAgent()
        assert agent.agent_name == "My Custom Agent"


class TestBaseAgentInvokeLLM:
    """Tests for BaseAgent.invoke_llm token tracking."""

    @pytest.fixture
    def agent(self):
        """Create a test agent instance."""
        return ConcreteAgent()

    @pytest.fixture
    def mock_model(self, agent):
        """Create a mock model."""
        from unittest.mock import Mock

        mock = Mock()
        agent.model = mock
        return mock

    def test_invoke_llm_records_tokens_with_metrics(self, agent, mock_model):
        """Test that invoke_llm records tokens when metrics is provided."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response text")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 250, "output_tokens": 100}
        )
        mock_model.invoke.return_value = ai_msg

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_llm([{"role": "user", "content": "test"}], metrics)

        assert result == "Response text"
        assert metrics.input_tokens == 250
        assert metrics.output_tokens == 100

    def test_invoke_llm_without_metrics(self, agent, mock_model):
        """Test that invoke_llm works without metrics."""
        ai_msg = AIMessage(content="Response text")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 250, "output_tokens": 100}
        )
        mock_model.invoke.return_value = ai_msg

        result = agent.invoke_llm([{"role": "user", "content": "test"}], None)

        assert result == "Response text"

    def test_invoke_llm_without_usage_metadata(self, agent, mock_model):
        """Test that invoke_llm handles missing usage_metadata."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response text")
        # No usage_metadata
        mock_model.invoke.return_value = ai_msg

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_llm([{"role": "user", "content": "test"}], metrics)

        assert result == "Response text"
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_llm_with_none_usage_metadata(self, agent, mock_model):
        """Test that invoke_llm handles None usage_metadata."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response text")
        ai_msg.usage_metadata = None
        mock_model.invoke.return_value = ai_msg

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_llm([{"role": "user", "content": "test"}], metrics)

        assert result == "Response text"
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_llm_with_partial_usage_metadata(self, agent, mock_model):
        """Test that invoke_llm handles partial usage_metadata."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response text")
        ai_msg.usage_metadata = cast(
            UsageMetadata,
            {"input_tokens": 100},  # Missing output_tokens
        )
        mock_model.invoke.return_value = ai_msg

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_llm([{"role": "user", "content": "test"}], metrics)

        assert result == "Response text"
        assert metrics.input_tokens == 100
        assert metrics.output_tokens == 0


class TestBaseAgentInvokeStructured:
    """Tests for BaseAgent.invoke_structured token tracking."""

    @pytest.fixture
    def agent(self):
        """Create a test agent instance."""
        return ConcreteAgent()

    @pytest.fixture
    def mock_structured_model(self, agent):
        """Mock the model's with_structured_output method."""
        from unittest.mock import Mock

        mock_structured = Mock()
        mock_model = Mock()
        mock_model.with_structured_output.return_value = mock_structured

        agent.model = mock_model

        return mock_structured

    def test_invoke_structured_records_tokens_with_metrics(
        self, agent, mock_structured_model
    ):
        """Test that invoke_structured records tokens when metrics is provided."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 500, "output_tokens": 200}
        )

        parsed_obj = {"field": "value"}
        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": parsed_obj,
        }

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == parsed_obj
        assert metrics.input_tokens == 500
        assert metrics.output_tokens == 200

    def test_invoke_structured_without_metrics(self, agent, mock_structured_model):
        """Test that invoke_structured works without metrics."""
        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 500, "output_tokens": 200}
        )

        parsed_obj = {"field": "value"}
        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": parsed_obj,
        }

        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], None
        )

        assert result == parsed_obj

    def test_invoke_structured_without_structured_response(
        self, agent, mock_structured_model
    ):
        """Test that invoke_structured handles None result (model didn't call tool)."""
        from src.types.telemetry import AgentMetrics

        mock_structured_model.invoke.return_value = {
            "raw": AIMessage(content=""),
            "parsed": None,
        }

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics, max_retries=1
        )

        assert result is None
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_structured_without_usage_metadata(
        self, agent, mock_structured_model
    ):
        """Test that invoke_structured handles messages without usage_metadata."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response")
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": parsed_obj,
        }

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == parsed_obj
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_structured_with_none_usage_metadata(
        self, agent, mock_structured_model
    ):
        """Test that invoke_structured handles messages with None usage_metadata."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = None
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": parsed_obj,
        }

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == parsed_obj
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_structured_no_ai_messages(self, agent, mock_structured_model):
        """Test that invoke_structured handles result without usage metadata."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="Response")
        parsed_result = {"field": "value"}
        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": parsed_result,
        }

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == parsed_result
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0


class TestBaseAgentInvokeStructuredRetries:
    """Tests for BaseAgent.invoke_structured retry mechanism."""

    @pytest.fixture
    def agent(self):
        """Create a test agent instance."""
        return ConcreteAgent()

    @pytest.fixture
    def mock_structured_model(self, agent):
        """Mock the model's with_structured_output method."""
        from unittest.mock import Mock

        mock_structured = Mock()
        mock_model = Mock()
        mock_model.with_structured_output.return_value = mock_structured

        agent.model = mock_model

        return mock_structured

    def test_retry_on_first_failure_then_success(self, agent, mock_structured_model):
        """Test that invoke_structured retries after first failure and succeeds."""
        from src.types.telemetry import AgentMetrics

        # First attempt: parsing_error is set, parsed is None
        ai_msg_1 = AIMessage(content="invalid response")
        ai_msg_1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        # Second attempt: success
        ai_msg_2 = AIMessage(content="valid response")
        ai_msg_2.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 150, "output_tokens": 75}
        )
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.side_effect = [
            {
                "raw": ai_msg_1,
                "parsed": None,
                "parsing_error": "ValidationError: missing required field",
            },
            {"raw": ai_msg_2, "parsed": parsed_obj},
        ]

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics, max_retries=3
        )

        assert result == parsed_obj
        assert mock_structured_model.invoke.call_count == 2
        # Token usage accumulated across both attempts
        assert metrics.input_tokens == 250  # 100 + 150
        assert metrics.output_tokens == 125  # 50 + 75

    def test_retry_on_multiple_failures_then_success(
        self, agent, mock_structured_model
    ):
        """Test multiple failures before success."""
        from src.types.telemetry import AgentMetrics

        ai_msg_1 = AIMessage(content="fail 1")
        ai_msg_1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg_2 = AIMessage(content="fail 2")
        ai_msg_2.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 110, "output_tokens": 55}
        )

        ai_msg_3 = AIMessage(content="success")
        ai_msg_3.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 120, "output_tokens": 60}
        )
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.side_effect = [
            {"raw": ai_msg_1, "parsed": None, "parsing_error": "Error 1"},
            {"raw": ai_msg_2, "parsed": None, "parsing_error": "Error 2"},
            {"raw": ai_msg_3, "parsed": parsed_obj},
        ]

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics, max_retries=3
        )

        assert result == parsed_obj
        assert mock_structured_model.invoke.call_count == 3
        assert metrics.input_tokens == 330  # 100 + 110 + 120
        assert metrics.output_tokens == 165  # 50 + 55 + 60

    def test_max_retries_reached_returns_none(self, agent, mock_structured_model):
        """Test that None is returned when max_retries is exhausted."""
        from src.types.telemetry import AgentMetrics

        ai_msg = AIMessage(content="always fails")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": None,
            "parsing_error": "Persistent validation error",
        }

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict,
            [{"role": "user", "content": "test"}],
            metrics,
            max_retries=3,
        )

        assert result is None
        # Should attempt exactly max_retries times
        assert mock_structured_model.invoke.call_count == 3
        # Tokens accumulated across all attempts
        assert metrics.input_tokens == 300  # 100 * 3
        assert metrics.output_tokens == 150  # 50 * 3

    def test_retry_messages_include_error_feedback(self, agent, mock_structured_model):
        """Test that retry attempts include error feedback message."""
        ai_msg_1 = AIMessage(content="invalid")
        ai_msg_1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg_2 = AIMessage(content="valid")
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.side_effect = [
            {
                "raw": ai_msg_1,
                "parsed": None,
                "parsing_error": "Missing required field: name",
            },
            {"raw": ai_msg_2, "parsed": parsed_obj},
        ]

        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "original request"}], max_retries=2
        )

        assert result == parsed_obj
        # Check that second invocation includes feedback message
        second_call_messages = mock_structured_model.invoke.call_args_list[1][0][0]
        assert len(second_call_messages) == 3  # system + user + error feedback
        assert second_call_messages[2]["role"] == "user"
        assert "Missing required field: name" in second_call_messages[2]["content"]
        assert "dict" in second_call_messages[2]["content"]  # schema name

    def test_max_retries_minimum_of_one(self, agent, mock_structured_model):
        """Test that max_retries=0 is clamped to 1."""
        ai_msg = AIMessage(content="response")
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.return_value = {
            "raw": ai_msg,
            "parsed": parsed_obj,
        }

        result = agent.invoke_structured(
            dict,
            [{"role": "user", "content": "test"}],
            max_retries=0,  # Should be clamped to 1
        )

        assert result == parsed_obj
        # Should invoke at least once
        assert mock_structured_model.invoke.call_count == 1

    def test_retry_without_metrics(self, agent, mock_structured_model):
        """Test that retries work without metrics tracking."""
        ai_msg_1 = AIMessage(content="fail")
        ai_msg_2 = AIMessage(content="success")
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.side_effect = [
            {"raw": ai_msg_1, "parsed": None, "parsing_error": "Error"},
            {"raw": ai_msg_2, "parsed": parsed_obj},
        ]

        result = agent.invoke_structured(
            dict,
            [{"role": "user", "content": "test"}],
            metrics=None,
            max_retries=2,
        )

        assert result == parsed_obj
        assert mock_structured_model.invoke.call_count == 2

    def test_retry_with_missing_parsing_error_key(self, agent, mock_structured_model):
        """Test handling when parsing_error key is missing from result."""
        from src.types.telemetry import AgentMetrics

        ai_msg_1 = AIMessage(content="fail")
        ai_msg_1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg_2 = AIMessage(content="success")
        parsed_obj = {"field": "value"}

        mock_structured_model.invoke.side_effect = [
            {"raw": ai_msg_1, "parsed": None},  # No parsing_error key
            {"raw": ai_msg_2, "parsed": parsed_obj},
        ]

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics, max_retries=2
        )

        assert result == parsed_obj
        # Should still retry despite missing parsing_error
        assert mock_structured_model.invoke.call_count == 2

    def test_retry_accumulates_messages_correctly(self, agent, mock_structured_model):
        """Test that each retry adds to the message history."""
        # Track messages at call time (not after mutation)
        call_time_messages = []

        def capture_and_return(messages, *args, **kwargs):
            # Capture a COPY of the messages at call time
            call_time_messages.append(list(messages))
            # Return responses in order
            return_values = [
                {
                    "raw": AIMessage(content="fail 1"),
                    "parsed": None,
                    "parsing_error": "Error 1",
                },
                {
                    "raw": AIMessage(content="fail 2"),
                    "parsed": None,
                    "parsing_error": "Error 2",
                },
                {"raw": AIMessage(content="success"), "parsed": {"field": "value"}},
            ]
            return return_values[len(call_time_messages) - 1]

        mock_structured_model.invoke.side_effect = capture_and_return

        result = agent.invoke_structured(
            dict,
            [{"role": "user", "content": "original"}],
            max_retries=3,
        )

        assert result == {"field": "value"}
        assert mock_structured_model.invoke.call_count == 3

        # Verify message count increases with each retry
        assert len(call_time_messages) == 3

        # First call: system + original
        assert len(call_time_messages[0]) == 2
        assert call_time_messages[0][0]["role"] == "system"
        assert call_time_messages[0][1]["content"] == "original"

        # Second call: system + original + error feedback from attempt 1
        assert len(call_time_messages[1]) == 3
        assert "Error 1" in call_time_messages[1][2]["content"]

        # Third call: system + original + error1 + error2
        assert len(call_time_messages[2]) == 4
        assert "Error 1" in call_time_messages[2][2]["content"]
        assert "Error 2" in call_time_messages[2][3]["content"]

    def test_retry_includes_ai_message_content_in_error(
        self, agent, mock_structured_model
    ):
        """Test that error feedback includes the AI's actual response content."""
        ai_msg = AIMessage(content="I returned a string instead of calling the tool")

        mock_structured_model.invoke.side_effect = [
            {
                "raw": ai_msg,
                "parsed": None,
                "parsing_error": "Expected tool call, got text",
            },
            {"raw": AIMessage(content=""), "parsed": {"field": "value"}},
        ]

        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], max_retries=2
        )

        assert result == {"field": "value"}

        # Check error message includes AI content
        second_call = mock_structured_model.invoke.call_args_list[1][0][0]
        error_message = second_call[2]["content"]
        assert "I returned a string instead of calling the tool" in error_message


class TestBaseAgentTagOriginalMessages:
    """Tests for BaseAgent._tag_original_messages static method."""

    def test_tag_single_user_message(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "Hello"
        assert result[0].additional_kwargs.get("x2a_original_message") is True

    def test_tag_single_system_message(self):
        from langchain_core.messages import SystemMessage

        messages = [{"role": "system", "content": "You are a helpful assistant"}]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], SystemMessage)
        assert result[0].content == "You are a helpful assistant"
        assert result[0].additional_kwargs.get("x2a_original_message") is True

    def test_tag_mixed_messages(self):
        from langchain_core.messages import SystemMessage

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User question"},
        ]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 2
        assert isinstance(result[0], SystemMessage)
        assert isinstance(result[1], HumanMessage)
        assert result[0].additional_kwargs.get("x2a_original_message") is True
        assert result[1].additional_kwargs.get("x2a_original_message") is True

    def test_tag_multiple_user_messages(self):
        messages = [
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 3
        for msg in result:
            assert isinstance(msg, HumanMessage)
            assert msg.additional_kwargs.get("x2a_original_message") is True

    def test_tag_empty_content(self):
        messages = [{"role": "user", "content": ""}]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 1
        assert result[0].content == ""
        assert result[0].additional_kwargs.get("x2a_original_message") is True

    def test_tag_missing_role_defaults_to_user(self):
        messages = [{"content": "Message without role"}]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].additional_kwargs.get("x2a_original_message") is True

    def test_tag_missing_content_defaults_to_empty(self):
        messages = [{"role": "user"}]
        result = ConcreteAgent._tag_original_messages(messages)

        assert len(result) == 1
        assert result[0].content == ""

    def test_tag_preserves_independence(self):
        """Ensure each message gets its own independent tag dict."""
        messages = [
            {"role": "user", "content": "First"},
            {"role": "user", "content": "Second"},
        ]
        result = ConcreteAgent._tag_original_messages(messages)

        # Modify one tag and ensure the other is unaffected
        result[0].additional_kwargs["modified"] = True
        assert "modified" not in result[1].additional_kwargs


class TestBaseAgentInvokeReact:
    """Tests for BaseAgent.invoke_react message tagging."""

    @pytest.fixture
    def agent(self):
        """Create a test agent instance."""
        return ConcreteAgent()

    @pytest.fixture
    def mock_agent_create(self, monkeypatch):
        """Mock the create_agent function."""
        from unittest.mock import Mock

        mock_create = Mock()
        monkeypatch.setattr("src.base_agent.create_agent", mock_create)
        return mock_create

    def test_invoke_react_tags_messages(self, agent, mock_agent_create):
        """Test that invoke_react tags messages before passing to agent."""
        from unittest.mock import Mock

        from langchain_core.messages import SystemMessage

        mock_agent_instance = Mock()
        mock_agent_instance.invoke.return_value = {"messages": []}
        mock_agent_create.return_value = mock_agent_instance

        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User input"},
        ]

        state = BaseState(user_message="test", path="/test")
        agent.invoke_react(state, messages)

        # Verify create_agent was called
        assert mock_agent_create.called

        # Verify invoke was called with tagged messages
        invoke_call = mock_agent_instance.invoke.call_args
        invoked_messages = invoke_call[0][0]["messages"]

        assert len(invoked_messages) == 2
        assert isinstance(invoked_messages[0], SystemMessage)
        assert isinstance(invoked_messages[1], HumanMessage)
        assert invoked_messages[0].additional_kwargs.get("x2a_original_message") is True
        assert invoked_messages[1].additional_kwargs.get("x2a_original_message") is True

    def test_invoke_react_preserves_message_content(self, agent, mock_agent_create):
        """Test that message content is preserved during tagging."""
        from unittest.mock import Mock

        mock_agent_instance = Mock()
        mock_agent_instance.invoke.return_value = {"messages": []}
        mock_agent_create.return_value = mock_agent_instance

        messages = [{"role": "user", "content": "Specific content to preserve"}]

        state = BaseState(user_message="test", path="/test")
        agent.invoke_react(state, messages)

        invoke_call = mock_agent_instance.invoke.call_args
        invoked_messages = invoke_call[0][0]["messages"]

        assert invoked_messages[0].content == "Specific content to preserve"

    def test_invoke_react_passes_metrics_via_runtime_context(
        self, agent, mock_agent_create
    ):
        """invoke_react must pass `metrics` through LangGraph's `context`
        argument (surfaced to middleware as `runtime.context`), since that is
        the only channel middleware -- cached across invocations -- has to
        learn which AgentMetrics belongs to the invocation currently running.
        """
        from unittest.mock import Mock

        from src.types.telemetry import AgentMetrics, AgentRuntimeContext

        mock_agent_instance = Mock()
        mock_agent_instance.invoke.return_value = {"messages": []}
        mock_agent_create.return_value = mock_agent_instance

        metrics = AgentMetrics(name="ConcreteAgent")
        state = BaseState(user_message="test", path="/test")
        agent.invoke_react(state, [{"role": "user", "content": "hi"}], metrics=metrics)

        # context_schema wired into create_agent so LangGraph accepts context=
        assert mock_agent_create.call_args.kwargs["context_schema"] is (
            AgentRuntimeContext
        )

        invoke_call = mock_agent_instance.invoke.call_args
        passed_context = invoke_call.kwargs["context"]
        assert isinstance(passed_context, AgentRuntimeContext)
        assert passed_context.metrics is metrics

    def test_invoke_react_passes_none_metrics_via_runtime_context(
        self, agent, mock_agent_create
    ):
        from unittest.mock import Mock

        from src.types.telemetry import AgentRuntimeContext

        mock_agent_instance = Mock()
        mock_agent_instance.invoke.return_value = {"messages": []}
        mock_agent_create.return_value = mock_agent_instance

        state = BaseState(user_message="test", path="/test")
        agent.invoke_react(state, [{"role": "user", "content": "hi"}])

        passed_context = mock_agent_instance.invoke.call_args.kwargs["context"]
        assert isinstance(passed_context, AgentRuntimeContext)
        assert passed_context.metrics is None


class FooTool(BaseTool):
    """Simple tool used to identify which tool set was built."""

    name: str = "foo_tool"
    description: str = "foo tool"

    def _run(self, *args, **kwargs):
        return "foo"


class BarTool(BaseTool):
    """A second, distinct tool used for GOAL_TOOLS assertions."""

    name: str = "bar_tool"
    description: str = "bar tool"

    def _run(self, *args, **kwargs):
        return "bar"


class BaseToolsOnlyAgent(BaseAgent[BaseState]):
    """Agent that only defines BASE_TOOLS, leaving GOAL_TOOLS at its default (empty)."""

    BASE_TOOLS: ClassVar[list] = [lambda: FooTool()]

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class GoalToolsAgent(BaseAgent[BaseState]):
    """Agent that defines a distinct, smaller GOAL_TOOLS set than BASE_TOOLS."""

    BASE_TOOLS: ClassVar[list] = [lambda: FooTool()]
    GOAL_TOOLS: ClassVar[list] = [lambda: BarTool()]

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class TestBaseAgentGoalTools:
    """Tests for BaseAgent.get_goal_tools when GOAL_TOOLS is/isn't defined."""

    def test_get_goal_tools_returns_none_when_undefined(self):
        """When GOAL_TOOLS is not overridden (default empty list), get_goal_tools returns None."""
        agent = BaseToolsOnlyAgent()
        state = BaseState(user_message="test", path="/test")

        assert agent.GOAL_TOOLS == []
        assert agent.get_goal_tools(state) is None

    def test_invoke_react_falls_back_to_base_tools_when_goal_tools_undefined(
        self, monkeypatch
    ):
        """invoke_react should use BASE_TOOLS when no explicit tools/GOAL_TOOLS are provided."""
        from unittest.mock import Mock

        mock_create = Mock()
        mock_agent_instance = Mock()
        mock_agent_instance.invoke.return_value = {"messages": []}
        mock_create.return_value = mock_agent_instance
        monkeypatch.setattr("src.base_agent.create_agent", mock_create)

        agent = BaseToolsOnlyAgent()
        state = BaseState(user_message="test", path="/test")

        agent.invoke_react(state, [{"role": "user", "content": "hi"}])

        used_tools = mock_create.call_args.kwargs["tools"]
        assert len(used_tools) == 1
        assert isinstance(used_tools[0], FooTool)

    def test_get_goal_tools_returns_goal_tools_when_defined(self):
        """When GOAL_TOOLS is defined, get_goal_tools builds instances from it, not BASE_TOOLS."""
        agent = GoalToolsAgent()
        state = BaseState(user_message="test", path="/test")

        goal_tools = agent.get_goal_tools(state)

        assert goal_tools is not None
        assert len(goal_tools) == 1
        assert isinstance(goal_tools[0], BarTool)
        assert not any(isinstance(tool, FooTool) for tool in goal_tools)


class TestBaseAgentMiddleware:
    """Tests for BaseAgent.middleware() configuration."""

    def test_middleware_without_rules_or_goal(self):
        agent = ConcreteAgent()
        stack = agent.middleware()

        assert len(stack) == 2
        assert isinstance(stack[0], X2ASummarizationMiddleware)
        assert isinstance(stack[1], TelemetryMiddleware)

    def test_middleware_with_rules_file(self):
        agent = RuledAgent()
        stack = agent.middleware()

        assert len(stack) == 3
        assert isinstance(stack[0], RulesMiddleware)
        assert isinstance(stack[1], X2ASummarizationMiddleware)
        assert isinstance(stack[2], TelemetryMiddleware)

    def test_middleware_with_goal(self):
        agent = GoalAgent()
        stack = agent.middleware()

        assert len(stack) == 3
        assert isinstance(stack[0], GoalValidationMiddleware)
        assert isinstance(stack[1], X2ASummarizationMiddleware)
        assert isinstance(stack[2], TelemetryMiddleware)

    def test_middleware_telemetry_is_last(self):
        """TelemetryMiddleware must stay innermost (last), see middleware() docstring."""
        agent = GoalAgent()
        stack = agent.middleware()

        assert isinstance(stack[-1], TelemetryMiddleware)

    def test_middleware_with_goal_passes_agent_reference(self):
        agent = GoalAgent()
        stack = agent.middleware()
        goal_mw = stack[0]

        assert goal_mw.agent is agent
        assert goal_mw.goal_description == "Verify output file exists"

    def test_middleware_is_cached(self):
        agent = GoalAgent()
        first = agent.middleware()
        second = agent.middleware()

        assert first is second

    def test_rules_file_classvar_defaults_to_none(self):
        agent = ConcreteAgent()
        assert agent.RULES_FILE is None

    def test_goal_classvar_defaults_to_none(self):
        agent = ConcreteAgent()
        assert agent.GOAL is None

    def test_rules_file_classvar_set_on_subclass(self):
        agent = RuledAgent()
        assert agent.RULES_FILE == "INPUT-AGENTS.md"

    def test_goal_classvar_set_on_subclass(self):
        agent = GoalAgent()
        assert agent.GOAL == "Verify output file exists"


class HighThresholdAgent(BaseAgent[BaseState]):
    """Agent with a high MAX_TOKENS_BEFORE_SUMMARY for testing scaling."""

    MAX_TOKENS_BEFORE_SUMMARY = 50_000

    def execute(self, state, metrics):
        return state


class TestEffectiveSummaryThreshold:
    """Tests for BaseAgent._effective_summary_threshold()."""

    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    @patch("src.base_agent.get_context_window", return_value=200_000)
    def test_compact_returns_base_value(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "compact")
        reset_settings()
        agent = ConcreteAgent()
        assert agent._effective_summary_threshold() == 20_000

    @patch("src.base_agent.get_context_window", return_value=200_000)
    def test_medium_scales_by_1_5(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "medium")
        reset_settings()
        agent = ConcreteAgent()
        assert agent._effective_summary_threshold() == 30_000

    @patch("src.base_agent.get_context_window", return_value=200_000)
    def test_large_scales_by_2(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "large")
        reset_settings()
        agent = ConcreteAgent()
        assert agent._effective_summary_threshold() == 40_000

    @patch("src.base_agent.get_context_window", return_value=200_000)
    def test_full_scales_by_3(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "full")
        reset_settings()
        agent = ConcreteAgent()
        assert agent._effective_summary_threshold() == 60_000

    @patch("src.base_agent.get_context_window", return_value=200_000)
    def test_applies_to_agent_specific_threshold(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "large")
        reset_settings()
        agent = HighThresholdAgent()
        assert agent._effective_summary_threshold() == 100_000

    @patch("src.base_agent.get_context_window", return_value=25_000)
    def test_caps_at_context_window(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "full")
        reset_settings()
        agent = ConcreteAgent()  # 20_000 * 3 = 60_000 > 25_000
        assert agent._effective_summary_threshold() == 25_000

    @patch("src.base_agent.get_context_window", return_value=40_000)
    def test_caps_high_threshold_agent_at_context_window(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "full")
        reset_settings()
        agent = HighThresholdAgent()  # 50_000 * 3 = 150_000 > 40_000
        assert agent._effective_summary_threshold() == 40_000

    @patch("src.base_agent.get_context_window", return_value=200_000)
    def test_messages_to_keep_unchanged(self, _mock_cw, monkeypatch):
        monkeypatch.setenv("SUMMARY_CONTEXT_SIZE", "full")
        reset_settings()
        agent = ConcreteAgent()
        assert agent.MESSAGES_TO_KEEP == 6
