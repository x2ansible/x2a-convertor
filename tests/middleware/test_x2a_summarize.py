"""Tests for X2ASummarizationMiddleware."""

from unittest.mock import Mock

import pytest
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from src.const import X2A_ORIGINAL_MESSAGE
from src.middleware.x2a_summarize import X2ASummarizationMiddleware


class MockRuntime:
    """Mock runtime for testing."""


class TestX2ASummarizationMiddleware:
    """Tests for X2ASummarizationMiddleware initialization and configuration."""

    def test_init_with_defaults(self):
        """Test middleware initialization with default parameters."""
        model = Mock()
        middleware = X2ASummarizationMiddleware(model)

        assert middleware._model is model
        assert middleware._messages_to_keep == 6
        assert middleware._max_tokens == 20_000
        assert middleware._original_messages_tag == X2A_ORIGINAL_MESSAGE

    def test_init_with_custom_parameters(self):
        """Test middleware initialization with custom parameters."""
        model = Mock()
        middleware = X2ASummarizationMiddleware(
            model,
            messages_to_keep=10,
            max_tokens=50_000,
            original_messages_tag="custom_tag",
        )

        assert middleware._messages_to_keep == 10
        assert middleware._max_tokens == 50_000
        assert middleware._original_messages_tag == "custom_tag"


class TestPartitionByTag:
    """Tests for _partition_by_tag method."""

    @pytest.fixture
    def middleware(self):
        """Create a middleware instance."""
        return X2ASummarizationMiddleware(Mock())

    def test_partition_all_original(self, middleware):
        """Test partitioning when all messages are tagged as original."""
        messages = [
            HumanMessage(
                content="First", additional_kwargs={X2A_ORIGINAL_MESSAGE: True}
            ),
            SystemMessage(
                content="Second", additional_kwargs={X2A_ORIGINAL_MESSAGE: True}
            ),
        ]

        original, non_original = middleware._partition_by_tag(messages)

        assert len(original) == 2
        assert len(non_original) == 0
        assert original == messages

    def test_partition_all_non_original(self, middleware):
        """Test partitioning when no messages are tagged as original."""
        messages = [
            AIMessage(content="First"),
            ToolMessage(content="Result", tool_call_id="123"),
        ]

        original, non_original = middleware._partition_by_tag(messages)

        assert len(original) == 0
        assert len(non_original) == 2
        assert non_original == messages

    def test_partition_mixed(self, middleware):
        """Test partitioning with mixed original and non-original messages."""
        msg1 = HumanMessage(
            content="Original", additional_kwargs={X2A_ORIGINAL_MESSAGE: True}
        )
        msg2 = AIMessage(content="Response")
        msg3 = ToolMessage(content="Tool result", tool_call_id="123")

        messages = [msg1, msg2, msg3]

        original, non_original = middleware._partition_by_tag(messages)

        assert len(original) == 1
        assert len(non_original) == 2
        assert original[0] is msg1
        assert msg2 in non_original
        assert msg3 in non_original

    def test_partition_empty_list(self, middleware):
        """Test partitioning with empty message list."""
        messages = []

        original, non_original = middleware._partition_by_tag(messages)

        assert len(original) == 0
        assert len(non_original) == 0

    def test_partition_false_tag_value(self, middleware):
        """Test that False tag value is treated as non-original."""
        messages = [
            HumanMessage(
                content="Not original", additional_kwargs={X2A_ORIGINAL_MESSAGE: False}
            ),
        ]

        original, non_original = middleware._partition_by_tag(messages)

        assert len(original) == 0
        assert len(non_original) == 1


class TestSelectRecentMessages:
    """Tests for _select_recent_messages method."""

    @pytest.fixture
    def middleware(self):
        """Create a middleware instance with 3 messages to keep."""
        return X2ASummarizationMiddleware(Mock(), messages_to_keep=3)

    def test_select_fewer_than_limit(self, middleware):
        """Test selection when message count is below the limit."""
        messages = [
            AIMessage(content="1"),
            AIMessage(content="2"),
        ]

        result = middleware._select_recent_messages(messages)

        assert len(result) == 2
        assert result == messages

    def test_select_exact_limit(self, middleware):
        """Test selection when message count equals the limit."""
        messages = [
            AIMessage(content="1"),
            AIMessage(content="2"),
            AIMessage(content="3"),
        ]

        result = middleware._select_recent_messages(messages)

        assert len(result) == 3
        assert result == messages

    def test_select_more_than_limit(self, middleware):
        """Test selection when message count exceeds the limit."""
        messages = [
            AIMessage(content="1"),
            AIMessage(content="2"),
            AIMessage(content="3"),
            AIMessage(content="4"),
            AIMessage(content="5"),
        ]

        result = middleware._select_recent_messages(messages)

        assert len(result) == 3
        assert result == messages[-3:]

    def test_select_adjusts_cutoff_for_tool_pairs(self, middleware):
        """Test that cutoff is adjusted to preserve AI-Tool message pairs."""
        from langchain_core.tools import tool

        @tool
        def test_tool() -> str:
            """Test tool."""
            return "result"

        ai_msg = AIMessage(
            content="AI",
            tool_calls=[
                {
                    "name": "test_tool",
                    "args": {},
                    "id": "123",
                    "type": "tool_call",
                }
            ],
        )
        tool_msg = ToolMessage(content="Tool result", tool_call_id="123")

        messages = [
            AIMessage(content="1"),
            AIMessage(content="2"),
            ai_msg,  # Should keep this...
            tool_msg,  # ...and its corresponding tool message
            AIMessage(content="5"),
        ]

        result = middleware._select_recent_messages(messages)

        # Should include the AI-Tool pair even if it means keeping more than 3
        assert ai_msg in result
        assert tool_msg in result

    def test_select_empty_list(self, middleware):
        """Test selection with empty message list."""
        messages = []

        result = middleware._select_recent_messages(messages)

        assert len(result) == 0


class TestAdjustCutoffForToolPairs:
    """Tests for _adjust_cutoff_for_tool_pairs static method."""

    def test_cutoff_beyond_messages(self):
        """Test when cutoff is beyond message list length."""
        messages: list[AnyMessage] = [AIMessage(content="1")]
        cutoff = 10

        result = X2ASummarizationMiddleware._adjust_cutoff_for_tool_pairs(
            messages, cutoff
        )

        assert result == cutoff

    def test_cutoff_not_on_tool_message(self):
        """Test when cutoff doesn't land on a ToolMessage."""
        messages: list[AnyMessage] = [
            AIMessage(content="1"),
            AIMessage(content="2"),
            AIMessage(content="3"),
        ]
        cutoff = 1

        result = X2ASummarizationMiddleware._adjust_cutoff_for_tool_pairs(
            messages, cutoff
        )

        assert result == cutoff

    def test_cutoff_on_tool_message_finds_ai_message(self):
        """Test when cutoff is on ToolMessage and finds matching AIMessage."""
        ai_msg = AIMessage(
            content="AI",
            tool_calls=[
                {
                    "name": "test_tool",
                    "args": {},
                    "id": "123",
                    "type": "tool_call",
                }
            ],
        )
        tool_msg = ToolMessage(content="Result", tool_call_id="123")

        messages: list[AnyMessage] = [
            AIMessage(content="1"),
            ai_msg,
            tool_msg,  # Cutoff here
            AIMessage(content="4"),
        ]
        cutoff = 2

        result = X2ASummarizationMiddleware._adjust_cutoff_for_tool_pairs(
            messages, cutoff
        )

        assert result == 1  # Adjusted to include the AI message

    def test_cutoff_on_tool_message_no_ai_message(self):
        """Test when cutoff is on ToolMessage but no matching AIMessage found."""
        tool_msg1 = ToolMessage(content="Result1", tool_call_id="123")
        tool_msg2 = ToolMessage(content="Result2", tool_call_id="456")

        messages: list[AnyMessage] = [
            AIMessage(content="1"),
            tool_msg1,  # Cutoff here
            tool_msg2,
            AIMessage(content="4"),
        ]
        cutoff = 1

        result = X2ASummarizationMiddleware._adjust_cutoff_for_tool_pairs(
            messages, cutoff
        )

        # Should skip past consecutive tool messages
        assert result == 3

    def test_cutoff_on_multiple_consecutive_tool_messages(self):
        """Test adjustment skips all consecutive ToolMessages."""
        messages: list[AnyMessage] = [
            AIMessage(content="1"),
            ToolMessage(content="Result1", tool_call_id="123"),  # Cutoff
            ToolMessage(content="Result2", tool_call_id="456"),
            ToolMessage(content="Result3", tool_call_id="789"),
            AIMessage(content="5"),
        ]
        cutoff = 1

        result = X2ASummarizationMiddleware._adjust_cutoff_for_tool_pairs(
            messages, cutoff
        )

        assert result == 4  # Skip all consecutive tool messages


class TestEnsureMessageIds:
    """Tests for _ensure_message_ids static method."""

    def test_ensure_ids_for_messages_without_ids(self):
        """Test that messages without IDs get assigned UUIDs."""
        messages: list[AnyMessage] = [
            AIMessage(content="1"),
            HumanMessage(content="2"),
            SystemMessage(content="3"),
        ]

        X2ASummarizationMiddleware._ensure_message_ids(messages)

        for msg in messages:
            assert msg.id is not None
            assert isinstance(msg.id, str)
            assert len(msg.id) == 36  # UUID format

    def test_ensure_ids_preserves_existing_ids(self):
        """Test that existing IDs are not overwritten."""
        existing_id = "existing-id-123"
        messages: list[AnyMessage] = [
            AIMessage(content="1", id=existing_id),
            HumanMessage(content="2"),
        ]

        X2ASummarizationMiddleware._ensure_message_ids(messages)

        assert messages[0].id == existing_id
        assert messages[1].id is not None

    def test_ensure_ids_empty_list(self):
        """Test with empty message list."""
        messages = []
        X2ASummarizationMiddleware._ensure_message_ids(messages)
        assert len(messages) == 0


class TestBeforeModelTokenThreshold:
    """Tests for before_model method token threshold behavior."""

    @pytest.fixture
    def model(self):
        """Create a mock model."""
        return Mock()

    @pytest.fixture
    def runtime(self):
        """Create a mock runtime."""
        return MockRuntime()

    def test_before_model_below_threshold_returns_none(self, model, runtime):
        """Test that middleware does nothing when below token threshold."""
        middleware = X2ASummarizationMiddleware(model, max_tokens=100_000)

        messages = [
            HumanMessage(
                content="Short message", additional_kwargs={X2A_ORIGINAL_MESSAGE: True}
            ),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is None

    def test_before_model_above_threshold_triggers_summary(self, model, runtime):
        """Test that middleware triggers summary when above threshold."""
        model.invoke.return_value = Mock(text="Summary of actions")

        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=1
        )

        original = HumanMessage(
            content="Original",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg1",
        )
        messages = [
            original,
            AIMessage(content="Long response " * 100, id="msg2"),
            ToolMessage(content="Tool result " * 100, tool_call_id="123", id="msg3"),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is not None
        assert "messages" in result
        assert model.invoke.called


class TestBeforeModelSummarization:
    """Tests for before_model summarization logic."""

    @pytest.fixture
    def model(self):
        """Create a mock model."""
        mock = Mock()
        mock.invoke.return_value = Mock(text="Summarized content")
        return mock

    @pytest.fixture
    def runtime(self):
        """Create a mock runtime."""
        return MockRuntime()

    def test_before_model_preserves_original_messages(self, model, runtime):
        """Test that original messages are preserved verbatim."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=1
        )

        original1 = SystemMessage(
            content="System prompt",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg1",
        )
        original2 = HumanMessage(
            content="User input",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg2",
        )
        non_original1 = AIMessage(content="Response " * 100, id="msg3")
        non_original2 = AIMessage(content="Another " * 100, id="msg4")

        messages = [original1, original2, non_original1, non_original2]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is not None
        result_messages = result["messages"]

        # Filter out RemoveMessage
        preserved = [
            msg for msg in result_messages if not isinstance(msg, RemoveMessage)
        ]

        assert original1 in preserved
        assert original2 in preserved

    def test_before_model_creates_summary_message(self, model, runtime):
        """Test that a summary HumanMessage is created."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=1
        )

        original = HumanMessage(
            content="Original",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg1",
        )
        messages = [
            original,
            AIMessage(content="AI response " * 100, id="msg2"),
            ToolMessage(content="Tool result " * 100, tool_call_id="123", id="msg3"),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is not None
        result_messages = result["messages"]
        human_messages = [
            msg for msg in result_messages if isinstance(msg, HumanMessage)
        ]

        # Should have original + summary
        assert len(human_messages) == 2
        summary_msg = next(msg for msg in human_messages if msg is not original)
        assert "Summary of previous actions:" in summary_msg.content

    def test_before_model_keeps_recent_messages(self, model, runtime):
        """Test that recent messages are preserved."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=2
        )

        original = HumanMessage(
            content="Original",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg1",
        )
        ai1 = AIMessage(content="AI 1 " * 100, id="msg2")
        ai2 = AIMessage(content="AI 2", id="msg3")
        ai3 = AIMessage(content="AI 3", id="msg4")

        messages = [original, ai1, ai2, ai3]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is not None
        result_messages = [
            msg for msg in result["messages"] if not isinstance(msg, RemoveMessage)
        ]

        # Should have: original, summary, ai2, ai3 (last 2 non-original)
        assert ai2 in result_messages
        assert ai3 in result_messages

    def test_before_model_removes_all_old_messages(self, model, runtime):
        """Test that RemoveMessage with REMOVE_ALL_MESSAGES is issued."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=1
        )

        messages = [
            HumanMessage(
                content="Original",
                additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
                id="msg1",
            ),
            AIMessage(content="AI1 " * 100, id="msg2"),
            AIMessage(content="AI2 " * 100, id="msg3"),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is not None
        result_messages = result["messages"]
        remove_messages = [
            msg for msg in result_messages if isinstance(msg, RemoveMessage)
        ]

        assert len(remove_messages) == 1
        assert remove_messages[0].id == REMOVE_ALL_MESSAGES

    def test_before_model_no_non_original_messages(self, model, runtime):
        """Test when all messages are original (no summarization needed)."""
        middleware = X2ASummarizationMiddleware(model, max_tokens=10)

        messages = [
            HumanMessage(
                content="Original " * 100,
                additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            ),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        # Should return None since there's nothing to summarize
        assert result is None

    def test_before_model_no_messages_to_summarize(self, model, runtime):
        """Test when all non-original messages should be kept."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=10
        )

        messages = [
            HumanMessage(
                content="Original", additional_kwargs={X2A_ORIGINAL_MESSAGE: True}
            ),
            AIMessage(content="AI " * 100),
            AIMessage(content="AI2"),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        # Should return None since we're keeping all non-original messages
        assert result is None


class TestSummaryCreation:
    """Tests for _create_summary method."""

    @pytest.fixture
    def model(self):
        """Create a mock model."""
        mock = Mock()
        mock.invoke.return_value = Mock(text="Summary text")
        return mock

    @pytest.fixture
    def middleware(self, model):
        """Create middleware instance."""
        return X2ASummarizationMiddleware(model)

    def test_create_summary_with_messages(self, middleware, model):
        """Test summary creation with valid messages."""
        messages = [
            AIMessage(content="First"),
            ToolMessage(content="Result", tool_call_id="123"),
        ]

        result = middleware._create_summary(messages)

        assert result == "Summary text"
        model.invoke.assert_called_once()

    def test_create_summary_empty_messages(self, middleware, model):
        """Test summary creation with empty message list."""
        messages = []

        result = middleware._create_summary(messages)

        assert result == "No previous actions to summarize."
        model.invoke.assert_not_called()

    def test_create_summary_model_error(self, middleware, model):
        """Test summary creation handles model errors gracefully."""
        model.invoke.side_effect = Exception("Model error")
        messages = [AIMessage(content="Message")]

        result = middleware._create_summary(messages)

        assert "Error generating summary" in result


class TestEndToEndScenarios:
    """End-to-end integration tests for the middleware."""

    @pytest.fixture
    def model(self):
        """Create a mock model."""
        mock = Mock()
        mock.invoke.return_value = Mock(text="Actions completed:\n- Read file")
        return mock

    @pytest.fixture
    def runtime(self):
        """Create a mock runtime."""
        return MockRuntime()

    def test_complete_summarization_flow(self, model, runtime):
        """Test a complete summarization flow from start to finish."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=2
        )

        # Set up realistic scenario
        system_msg = SystemMessage(
            content="You are a migration assistant",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg1",
        )
        user_msg = HumanMessage(
            content="Migrate this Chef code",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="msg2",
        )

        # Conversation that gets summarized
        ai1 = AIMessage(content="Reading file " * 50, id="msg3")
        tool1 = ToolMessage(content="File contents " * 50, tool_call_id="1", id="msg4")
        ai2 = AIMessage(content="Analyzing " * 50, id="msg5")

        # Recent messages to keep
        ai3 = AIMessage(content="Recent finding", id="msg6")
        tool2 = ToolMessage(content="Recent result", tool_call_id="2", id="msg7")

        messages = [system_msg, user_msg, ai1, tool1, ai2, ai3, tool2]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is not None
        result_messages = result["messages"]

        # Should have: RemoveMessage, system_msg, user_msg, summary, ai3, tool2
        non_remove = [
            msg for msg in result_messages if not isinstance(msg, RemoveMessage)
        ]

        # Check structure
        assert system_msg in non_remove
        assert user_msg in non_remove
        assert ai3 in non_remove
        assert tool2 in non_remove

        # Check summary was created
        summary_messages = [
            msg
            for msg in non_remove
            if isinstance(msg, HumanMessage) and msg is not user_msg
        ]
        assert len(summary_messages) == 1
        assert "Summary of previous actions:" in summary_messages[0].content

    def test_no_summarization_when_not_needed(self, model, runtime):
        """Test that no summarization occurs when conditions aren't met."""
        middleware = X2ASummarizationMiddleware(
            model, max_tokens=100_000, messages_to_keep=10
        )

        messages = [
            HumanMessage(
                content="Short message",
                additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            ),
            AIMessage(content="Short response"),
        ]
        state = {"messages": messages}

        result = middleware.before_model(state, runtime)

        assert result is None
        model.invoke.assert_not_called()
