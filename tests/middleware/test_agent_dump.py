"""Tests for SnapshotWriter, AgentDumpMiddleware, and AgentDumpCallbackHandler."""

import asyncio
import json
from unittest.mock import Mock

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, LLMResult
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages

from src.const import X2A_ORIGINAL_MESSAGE
from src.middleware.agent_dump import (
    AgentDumpCallbackHandler,
    AgentDumpMiddleware,
    SnapshotWriter,
)
from src.middleware.x2a_summarize import X2ASummarizationMiddleware

AGENT_NAME = "TestAgent"
AGENT_ID = "test-agent-123"


def _make_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("JSON_LINES", str(tmp_path))
    return SnapshotWriter(AGENT_NAME, AGENT_ID)


def _read_snapshots(tmp_path, writer):
    path = tmp_path / writer.file_name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


class TestSnapshotWriterConversion:
    def test_converts_human_message(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        result = writer._convert_message(HumanMessage(content="hello"))

        assert result["role"] == "user"
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "hello"

    def test_converts_ai_message_with_text(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        result = writer._convert_message(AIMessage(content="response"))

        assert result["role"] == "assistant"
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "response"

    def test_converts_ai_message_with_tool_calls(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        msg = AIMessage(
            content="",
            tool_calls=[
                {"id": "call_1", "name": "search", "args": {"q": "test"}},
            ],
        )
        result = writer._convert_message(msg)

        assert result["role"] == "assistant"
        tool_part = result["content"][0]
        assert tool_part["type"] == "tool_use"
        assert tool_part["id"] == "call_1"
        assert tool_part["name"] == "search"
        assert tool_part["input"] == {"q": "test"}

    def test_converts_tool_message(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        msg = ToolMessage(content="result data", tool_call_id="call_1")
        result = writer._convert_message(msg)

        assert result["role"] == "user"
        assert result["content"][0]["type"] == "tool_result"
        assert result["content"][0]["tool_use_id"] == "call_1"
        assert result["content"][0]["content"] == "result data"

    def test_converts_system_message_as_user(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        result = writer._convert_message(SystemMessage(content="system prompt"))

        assert result["role"] == "user"
        assert result["content"][0]["text"] == "system prompt"


class TestSnapshotWriterWrite:
    def test_writes_jsonl_file(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        messages: list[BaseMessage] = [
            HumanMessage(content="hi"),
            AIMessage(content="hello"),
        ]

        writer.write_snapshot(messages)

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert entries[0]["type"] == "snapshot"
        assert entries[0]["isSnapshotUpdate"] is True
        assert len(entries[0]["snapshot"]) == 2

    def test_increments_message_counter(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)

        writer.write_snapshot([HumanMessage(content="first")])
        writer.write_snapshot([HumanMessage(content="second")])

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 2
        assert entries[0]["messageId"] == f"msg_{AGENT_ID}_1"
        assert entries[1]["messageId"] == f"msg_{AGENT_ID}_2"

    def test_skips_empty_messages(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        writer.write_snapshot([])

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 0

    def test_skips_when_json_lines_not_set(self, tmp_path, monkeypatch):
        monkeypatch.delenv("JSON_LINES", raising=False)
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)

        writer.write_snapshot([HumanMessage(content="ignored")])

        assert not list(tmp_path.iterdir())

    def test_creates_output_directory(self, tmp_path, monkeypatch):
        nested = tmp_path / "deep" / "nested"
        monkeypatch.setenv("JSON_LINES", str(nested))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)

        writer.write_snapshot([HumanMessage(content="creates dir")])

        assert nested.exists()
        entries = [
            json.loads(line)
            for line in (nested / writer.file_name).read_text().splitlines()
        ]
        assert len(entries) == 1

    def test_file_name_includes_agent_name_and_id(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)

        assert writer.file_name == f"{AGENT_NAME}-{AGENT_ID}.jsonl"


class TestAgentDumpMiddleware:
    def test_after_agent_writes_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        state = {
            "messages": [HumanMessage(content="user msg"), AIMessage(content="ai msg")]
        }
        result = middleware.after_agent(state, runtime=None)

        assert result is None
        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert len(entries[0]["snapshot"]) == 2

    def test_after_agent_no_op_on_empty_messages(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        result = middleware.after_agent({"messages": []}, runtime=None)

        assert result is None
        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 0

    def test_aafter_agent_writes_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        state = {"messages": [HumanMessage(content="async test")]}
        result = asyncio.run(middleware.aafter_agent(state, runtime=None))

        assert result is None
        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1

    def test_file_name_delegates_to_writer(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        assert middleware.file_name == writer.file_name

    def test_shares_counter_with_writer(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        writer.write_snapshot([HumanMessage(content="direct")])
        middleware.after_agent(
            {"messages": [HumanMessage(content="via middleware")]}, runtime=None
        )

        entries = _read_snapshots(tmp_path, writer)
        assert entries[0]["messageId"] == f"msg_{AGENT_ID}_1"
        assert entries[1]["messageId"] == f"msg_{AGENT_ID}_2"


class TestAgentDumpMiddlewareIncremental:
    """Tests for the before_model accumulation / after_agent write-once split.

    before_model accumulates messages in memory on every turn (so
    AgentDumpMiddleware survives X2ASummarizationMiddleware evicting messages
    from live graph state via RemoveMessage(REMOVE_ALL_MESSAGES)), but never
    writes to disk. Only after_agent (once, at the end of the run) writes the
    full accumulated history.
    """

    def test_before_model_does_not_write_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        state = {"messages": [HumanMessage(content="hi", id="m1")]}
        result = middleware.before_model(state, runtime=None)

        assert result is None
        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 0

    def test_multiple_before_model_calls_do_not_write_to_disk(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        middleware.before_model(
            {"messages": [HumanMessage(content="first", id="m1")]}, runtime=None
        )
        middleware.before_model(
            {
                "messages": [
                    HumanMessage(content="first", id="m1"),
                    AIMessage(content="second", id="m2"),
                ]
            },
            runtime=None,
        )

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 0

    def test_after_agent_writes_once_with_full_accumulated_history(
        self, tmp_path, monkeypatch
    ):
        """Simulates X2ASummarizationMiddleware's RemoveMessage(REMOVE_ALL_MESSAGES):
        messages captured via before_model on earlier turns must still be
        present in the single write that after_agent performs, even though
        the final state passed to after_agent is truncated.
        """
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        middleware.before_model(
            {
                "messages": [
                    HumanMessage(content="original", id="m1"),
                    AIMessage(content="call tool", id="m2"),
                    ToolMessage(content="tool result", tool_call_id="tc1", id="m3"),
                ]
            },
            runtime=None,
        )

        # Final state: summarization evicted m1-m3, replacing them with a
        # summary message. Only the summary is visible in the final state.
        result = middleware.after_agent(
            {
                "messages": [
                    RemoveMessage(id=REMOVE_ALL_MESSAGES),
                    HumanMessage(content="summary of previous actions", id="m4"),
                ]
            },
            runtime=None,
        )

        assert result is None
        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        # The single write still contains everything ever accumulated.
        assert len(entries[0]["snapshot"]) == 4

    def test_after_agent_ignores_remove_message_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        state = {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                HumanMessage(content="kept", id="m1"),
            ]
        }
        middleware.after_agent(state, runtime=None)

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries[0]["snapshot"]) == 1

    def test_abefore_model_does_not_write_to_disk(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        state = {"messages": [HumanMessage(content="async", id="m1")]}
        result = asyncio.run(middleware.abefore_model(state, runtime=None))

        assert result is None
        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 0

    def test_before_agent_resets_cumulative_state(self, tmp_path, monkeypatch):
        """AgentMiddleware instances are cached on BaseAgent across multiple
        invoke_react() calls, so before_agent must clear history from any
        previous run to avoid pooling unrelated messages together.
        """
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        middleware.before_model(
            {"messages": [HumanMessage(content="run one", id="m1")]}, runtime=None
        )
        middleware.after_agent(
            {"messages": [HumanMessage(content="run one", id="m1")]}, runtime=None
        )

        middleware.before_agent({"messages": []}, runtime=None)

        middleware.before_model(
            {"messages": [HumanMessage(content="run two", id="m2")]}, runtime=None
        )
        middleware.after_agent(
            {"messages": [HumanMessage(content="run two", id="m2")]}, runtime=None
        )

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 2
        # Second run's snapshot only contains its own message, not run one's.
        assert len(entries[1]["snapshot"]) == 1
        assert entries[1]["snapshot"][0]["content"][0]["text"] == "run two"

    def test_abefore_agent_resets_cumulative_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        middleware.before_model(
            {"messages": [HumanMessage(content="run one", id="m1")]}, runtime=None
        )

        result = asyncio.run(middleware.abefore_agent({"messages": []}, runtime=None))

        assert result is None
        middleware.before_model(
            {"messages": [HumanMessage(content="run two", id="m2")]}, runtime=None
        )
        middleware.after_agent(
            {"messages": [HumanMessage(content="run two", id="m2")]}, runtime=None
        )

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert len(entries[0]["snapshot"]) == 1

    def test_after_agent_dedupes_messages_already_seen_via_before_model(
        self, tmp_path, monkeypatch
    ):
        """Messages accumulated via before_model must not be double-counted
        when after_agent's final accumulate+write runs.
        """
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        middleware = AgentDumpMiddleware(writer)

        middleware.before_model(
            {"messages": [HumanMessage(content="hi", id="m1")]}, runtime=None
        )
        middleware.after_agent(
            {
                "messages": [
                    HumanMessage(content="hi", id="m1"),
                    AIMessage(content="final answer", id="m2"),
                ]
            },
            runtime=None,
        )

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert len(entries[0]["snapshot"]) == 2


class TestAgentDumpBeforeSummarization:
    """Composed tests that actually run AgentDumpMiddleware.before_model
    followed by X2ASummarizationMiddleware.before_model on the same state,
    in the same order BaseAgent.middleware() registers them.

    Unlike TestAgentDumpMiddlewareIncremental (which calls the dump hooks in
    isolation and hand-crafts a pre-evicted final state), this locks the
    actual registration-order contract: dump must see each turn's messages
    strictly before summarization's before_model can evict them via
    RemoveMessage(REMOVE_ALL_MESSAGES). If that order were ever reversed, the
    dump would accumulate an already-summarized state and lose history.
    """

    def _apply_update(self, state, update):
        messages = add_messages(state["messages"], update["messages"])
        return {"messages": messages}

    def test_dump_before_model_precedes_summarization_eviction(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("JSON_LINES", str(tmp_path))
        writer = SnapshotWriter(AGENT_NAME, AGENT_ID)
        dump_middleware = AgentDumpMiddleware(writer)

        model = Mock()
        model.invoke.return_value = Mock(text="Summary of previous actions")
        summarization_middleware = X2ASummarizationMiddleware(
            model, max_tokens=10, messages_to_keep=1
        )

        original = HumanMessage(
            content="Migrate this Chef code",
            additional_kwargs={X2A_ORIGINAL_MESSAGE: True},
            id="m1",
        )
        ai_msg = AIMessage(content="call tool " * 50, id="m2")
        tool_msg = ToolMessage(content="tool result " * 50, tool_call_id="tc1", id="m3")
        state = {"messages": [original, ai_msg, tool_msg]}

        dump_middleware.before_agent(state, runtime=None)

        # Registration order: dump runs before summarization on the same turn.
        dump_result = dump_middleware.before_model(state, runtime=None)
        assert dump_result is None

        summarize_result = summarization_middleware.before_model(state, runtime=Mock())
        assert summarize_result is not None

        # Apply summarization's update the way LangGraph's reducer would,
        # simulating the eviction that the live graph state undergoes.
        evicted_state = self._apply_update(state, summarize_result)
        non_remove = [
            msg
            for msg in evicted_state["messages"]
            if not isinstance(msg, RemoveMessage)
        ]
        assert ai_msg not in non_remove
        assert tool_msg not in non_remove

        dump_middleware.after_agent(evicted_state, runtime=None)

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        snapshot = entries[0]["snapshot"]

        # The dump's before_model already captured m1-m3 before eviction, so
        # the final write still contains them despite the live state above
        # no longer doing so, plus whatever summarization kept/added.
        assert snapshot[0]["content"][0]["text"] == "Migrate this Chef code"
        assert snapshot[1]["role"] == "assistant"
        assert snapshot[1]["content"][0]["text"] == "call tool " * 50
        assert snapshot[2]["role"] == "user"
        assert snapshot[2]["content"][0]["type"] == "tool_result"
        assert snapshot[2]["content"][0]["content"] == "tool result " * 50
        summary_texts = [
            entry["content"][0]["text"]
            for entry in snapshot[3:]
            if entry["role"] == "user"
        ]
        assert any("Summary of previous actions" in text for text in summary_texts)


class TestAgentDumpCallbackHandler:
    def _make_llm_result(self, ai_message):
        generation = ChatGeneration(message=ai_message)
        return LLMResult(generations=[[generation]])

    def test_captures_chat_model_start_and_llm_end(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        input_messages: list[list[BaseMessage]] = [
            [HumanMessage(content="what is 2+2?")]
        ]
        handler.on_chat_model_start(serialized={}, messages=input_messages)

        ai_msg = AIMessage(content="4")
        handler.on_llm_end(self._make_llm_result(ai_msg))

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        snapshot = entries[0]["snapshot"]
        assert len(snapshot) == 2
        assert snapshot[0]["role"] == "user"
        assert snapshot[0]["content"][0]["text"] == "what is 2+2?"
        assert snapshot[1]["role"] == "assistant"
        assert snapshot[1]["content"][0]["text"] == "4"

    def test_clears_pending_after_write(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="first")]]
        )
        handler.on_llm_end(self._make_llm_result(AIMessage(content="reply")))

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="second")]]
        )
        handler.on_llm_end(self._make_llm_result(AIMessage(content="reply2")))

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 2
        assert entries[1]["snapshot"][0]["content"][0]["text"] == "second"

    def test_writes_snapshot_even_without_generation(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="orphan")]]
        )
        handler.on_llm_end(LLMResult(generations=[[]]))

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert len(entries[0]["snapshot"]) == 1

    def test_handles_empty_messages_list(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        handler.on_chat_model_start(serialized={}, messages=[])
        handler.on_llm_end(self._make_llm_result(AIMessage(content="solo")))

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert len(entries[0]["snapshot"]) == 1

    def test_on_llm_error_clears_pending(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="will fail")]]
        )
        handler.on_llm_error(error=RuntimeError("boom"))

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="fresh")]]
        )
        handler.on_llm_end(self._make_llm_result(AIMessage(content="ok")))

        entries = _read_snapshots(tmp_path, writer)
        assert len(entries) == 1
        assert entries[0]["snapshot"][0]["content"][0]["text"] == "fresh"

    def test_captures_tool_calls_in_ai_message(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="search for X")]]
        )
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"id": "tc_1", "name": "web_search", "args": {"query": "X"}}],
        )
        handler.on_llm_end(self._make_llm_result(ai_msg))

        entries = _read_snapshots(tmp_path, writer)
        ai_snapshot = entries[0]["snapshot"][1]
        assert ai_snapshot["content"][0]["type"] == "tool_use"
        assert ai_snapshot["content"][0]["name"] == "web_search"

    def test_shares_counter_with_writer(self, tmp_path, monkeypatch):
        writer = _make_writer(tmp_path, monkeypatch)
        handler = AgentDumpCallbackHandler(writer)

        writer.write_snapshot([HumanMessage(content="direct write")])

        handler.on_chat_model_start(
            serialized={}, messages=[[HumanMessage(content="via callback")]]
        )
        handler.on_llm_end(self._make_llm_result(AIMessage(content="reply")))

        entries = _read_snapshots(tmp_path, writer)
        assert entries[0]["messageId"] == f"msg_{AGENT_ID}_1"
        assert entries[1]["messageId"] == f"msg_{AGENT_ID}_2"
