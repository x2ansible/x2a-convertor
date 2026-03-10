"""Tests for BaseAgent token extraction functionality."""

from typing import cast

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.ai import UsageMetadata

from src.base_agent import BaseAgent
from src.types.base_state import BaseState


class ConcreteAgent(BaseAgent[BaseState]):
    """Concrete implementation of BaseAgent for testing."""

    def execute(self, state: BaseState, metrics):
        """Minimal execute implementation."""
        return state


class TestBaseAgentTokenExtraction:
    """Tests for BaseAgent._extract_token_usage method."""

    @pytest.fixture
    def agent(self):
        """Create a test agent instance."""
        return ConcreteAgent()

    def test_extract_token_usage_empty_messages(self, agent):
        """Test extraction with no messages."""
        result = {"messages": []}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 0
        assert output_tokens == 0

    def test_extract_token_usage_no_ai_messages(self, agent):
        """Test extraction with no AI messages."""
        result = {
            "messages": [
                HumanMessage(content="Hello"),
                HumanMessage(content="World"),
            ]
        }
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 0
        assert output_tokens == 0

    def test_extract_token_usage_single_ai_message(self, agent):
        """Test extraction from single AI message."""
        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        result = {"messages": [ai_msg]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 100
        assert output_tokens == 50

    def test_extract_token_usage_multiple_ai_messages(self, agent):
        """Test extraction accumulates across multiple AI messages."""
        ai_msg1 = AIMessage(content="First")
        ai_msg1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg2 = AIMessage(content="Second")
        ai_msg2.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 200, "output_tokens": 75}
        )

        result = {"messages": [ai_msg1, ai_msg2]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 300
        assert output_tokens == 125

    def test_extract_token_usage_mixed_messages(self, agent):
        """Test extraction with mixed message types."""
        human_msg = HumanMessage(content="Question")
        ai_msg1 = AIMessage(content="Answer 1")
        ai_msg1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg2 = AIMessage(content="Answer 2")
        ai_msg2.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 150, "output_tokens": 60}
        )

        result = {"messages": [human_msg, ai_msg1, human_msg, ai_msg2]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 250
        assert output_tokens == 110

    def test_extract_token_usage_missing_metadata(self, agent):
        """Test extraction handles AI messages without usage_metadata."""
        ai_msg_with_metadata = AIMessage(content="First")
        ai_msg_with_metadata.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg_without_metadata = AIMessage(content="Second")
        # No usage_metadata attribute

        result = {"messages": [ai_msg_with_metadata, ai_msg_without_metadata]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 100
        assert output_tokens == 50

    def test_extract_token_usage_none_metadata(self, agent):
        """Test extraction handles None usage_metadata."""
        ai_msg1 = AIMessage(content="First")
        ai_msg1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg2 = AIMessage(content="Second")
        ai_msg2.usage_metadata = None

        result = {"messages": [ai_msg1, ai_msg2]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 100
        assert output_tokens == 50

    def test_extract_token_usage_partial_metadata(self, agent):
        """Test extraction handles missing keys in usage_metadata."""
        ai_msg1 = AIMessage(content="First")
        ai_msg1.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 100, "output_tokens": 50}
        )

        ai_msg2 = AIMessage(content="Second")
        ai_msg2.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 75}
        )  # Missing output_tokens

        ai_msg3 = AIMessage(content="Third")
        ai_msg3.usage_metadata = cast(
            UsageMetadata, {"output_tokens": 25}
        )  # Missing input_tokens

        result = {"messages": [ai_msg1, ai_msg2, ai_msg3]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 175  # 100 + 75 + 0
        assert output_tokens == 75  # 50 + 0 + 25

    def test_extract_token_usage_zero_tokens(self, agent):
        """Test extraction with zero token values."""
        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 0, "output_tokens": 0}
        )

        result = {"messages": [ai_msg]}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 0
        assert output_tokens == 0

    def test_extract_token_usage_missing_messages_key(self, agent):
        """Test extraction when result has no messages key."""
        result = {}
        input_tokens, output_tokens = agent._extract_token_usage(result)

        assert input_tokens == 0
        assert output_tokens == 0


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
    def mock_model(self, agent):
        """Create a mock structured model."""
        from unittest.mock import Mock

        mock = Mock()
        structured_mock = Mock()
        mock.with_structured_output.return_value = structured_mock
        agent.model = mock
        return mock, structured_mock

    def test_invoke_structured_records_tokens_with_metrics(self, agent, mock_model):
        """Test that invoke_structured records tokens when metrics is provided."""
        from src.types.telemetry import AgentMetrics

        _, structured_mock = mock_model

        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 500, "output_tokens": 200}
        )

        return_value = {
            "parsed": {"field": "value"},
            "raw": ai_msg,
        }
        structured_mock.invoke.return_value = return_value

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == {"field": "value"}
        assert metrics.input_tokens == 500
        assert metrics.output_tokens == 200

    def test_invoke_structured_without_metrics(self, agent, mock_model):
        """Test that invoke_structured works without metrics."""
        _, structured_mock = mock_model

        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = cast(
            UsageMetadata, {"input_tokens": 500, "output_tokens": 200}
        )

        return_value = {
            "parsed": {"field": "value"},
            "raw": ai_msg,
        }
        structured_mock.invoke.return_value = return_value

        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], None
        )

        assert result == {"field": "value"}

    def test_invoke_structured_without_raw_message(self, agent, mock_model):
        """Test that invoke_structured handles missing parsed key in result."""
        from src.types.telemetry import AgentMetrics

        _, structured_mock = mock_model

        structured_mock.invoke.return_value = {"field": "value"}

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        # Returns None since there's no "parsed" key
        assert result is None
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_structured_raw_without_usage_metadata(self, agent, mock_model):
        """Test that invoke_structured handles raw message without usage_metadata."""
        from src.types.telemetry import AgentMetrics

        _, structured_mock = mock_model

        ai_msg = AIMessage(content="Response")
        # No usage_metadata

        return_value = {
            "parsed": {"field": "value"},
            "raw": ai_msg,
        }
        structured_mock.invoke.return_value = return_value

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == {"field": "value"}
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_structured_raw_with_none_usage_metadata(self, agent, mock_model):
        """Test that invoke_structured handles raw message with None usage_metadata."""
        from src.types.telemetry import AgentMetrics

        _, structured_mock = mock_model

        ai_msg = AIMessage(content="Response")
        ai_msg.usage_metadata = None

        return_value = {
            "parsed": {"field": "value"},
            "raw": ai_msg,
        }
        structured_mock.invoke.return_value = return_value

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == {"field": "value"}
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0

    def test_invoke_structured_raw_not_ai_message(self, agent, mock_model):
        """Test that invoke_structured handles raw that is not AIMessage."""
        from src.types.telemetry import AgentMetrics

        _, structured_mock = mock_model

        return_value = {
            "parsed": {"field": "value"},
            "raw": "not an AI message",
        }
        structured_mock.invoke.return_value = return_value

        metrics = AgentMetrics(name="TestAgent")
        result = agent.invoke_structured(
            dict, [{"role": "user", "content": "test"}], metrics
        )

        assert result == {"field": "value"}
        assert metrics.input_tokens == 0
        assert metrics.output_tokens == 0
