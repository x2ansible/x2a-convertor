"""Tests for SnapshotWriter, AgentDumpMiddleware, and AgentDumpCallbackHandler."""

import asyncio
import json

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, LLMResult

from src.middleware.agent_dump import (
    AgentDumpCallbackHandler,
    AgentDumpMiddleware,
    SnapshotWriter,
)

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
