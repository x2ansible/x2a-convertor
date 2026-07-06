"""Tests for GoalValidationMiddleware."""

from copy import deepcopy
from typing import ClassVar
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.middleware.goal_validation import (
    GoalValidationMiddleware,
    GoalValidationResult,
)


class FakeAgent:
    BASE_TOOLS: ClassVar[list] = [lambda: MagicMock()]

    def __init__(self, structured_result=None):
        self._structured_result = structured_result

    def invoke_structured(self, **kwargs):
        return self._structured_result


@pytest.fixture
def make_middleware():
    def _factory(goal="Test goal", structured_result=None):
        agent = FakeAgent(structured_result=structured_result)
        return GoalValidationMiddleware(goal, agent=agent)

    return _factory


class TestGoalValidationResult:
    def test_schema_fields(self):
        result = GoalValidationResult(achieved=True, feedback="All good")
        assert result.achieved is True
        assert result.feedback == "All good"

    def test_schema_requires_fields(self):
        with pytest.raises(ValueError):
            GoalValidationResult.model_validate({})


class TestExtractContextMessages:
    def test_short_list_returned_unchanged(self, make_middleware):
        mw = make_middleware()
        messages = [HumanMessage(content=f"msg{i}") for i in range(4)]
        assert mw._extract_context_messages(messages) == messages

    def test_exact_boundary_returned_unchanged(self, make_middleware):
        mw = make_middleware()
        messages = [HumanMessage(content=f"msg{i}") for i in range(5)]
        assert mw._extract_context_messages(messages) == messages

    def test_long_list_keeps_head_and_tail(self, make_middleware):
        mw = make_middleware()
        messages = [HumanMessage(content=f"msg{i}") for i in range(10)]

        result = mw._extract_context_messages(messages)

        assert len(result) == 5
        assert result[:3] == messages[:3]
        assert result[3:] == messages[-2:]

    def test_empty_list(self, make_middleware):
        mw = make_middleware()
        assert mw._extract_context_messages([]) == []


class TestBuildValidationPrompt:
    def test_includes_goal_and_context(self, make_middleware):
        mw = make_middleware(goal="Create output.txt")
        messages = [HumanMessage(content="Hello"), AIMessage(content="Done")]

        prompt = mw._build_validation_prompt(messages)

        assert "Create output.txt" in prompt
        assert "Human: Hello" in prompt
        assert "AI: Done" in prompt

    def test_formats_messages_correctly(self, make_middleware):
        mw = make_middleware()
        msg_with_content = HumanMessage(content="visible")

        prompt = mw._build_validation_prompt([msg_with_content])

        assert "visible" in prompt
        assert "Human: visible" in prompt


class TestRunValidation:
    def test_goal_achieved(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(
                achieved=True, feedback="File exists"
            )
        )
        state = {"messages": [HumanMessage(content="create file")]}

        achieved, feedback = mw._run_validation(state)

        assert achieved is True
        assert feedback == "File exists"

    def test_goal_not_achieved(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(
                achieved=False, feedback="File missing"
            )
        )
        state = {"messages": [HumanMessage(content="create file")]}

        achieved, feedback = mw._run_validation(state)

        assert achieved is False
        assert feedback == "File missing"

    def test_none_result_returns_false(self, make_middleware):
        mw = make_middleware(structured_result=None)
        state = {"messages": []}

        achieved, feedback = mw._run_validation(state)

        assert achieved is False
        assert "did not respond" in feedback

    def test_exception_returns_false(self, make_middleware):
        mw = make_middleware()
        mw.agent.invoke_structured = MagicMock(
            side_effect=RuntimeError("LLM unavailable")
        )
        state = {"messages": []}

        achieved, feedback = mw._run_validation(state)

        assert achieved is False
        assert "LLM unavailable" in feedback

    def test_passes_middleware_tools_not_agent_tools(self):
        agent = MagicMock()
        agent.invoke_structured.return_value = GoalValidationResult(
            achieved=True, feedback="ok"
        )
        mw = GoalValidationMiddleware("goal", agent=agent)

        mw._run_validation({"messages": []})

        call_kwargs = agent.invoke_structured.call_args[1]
        tool_types = {type(t).__name__ for t in call_kwargs["tools"]}
        assert "FileSearchTool" in tool_types
        assert "ListDirectoryTool" in tool_types
        assert "ReadFileTool" in tool_types
        assert "WriteFileTool" not in tool_types


class TestAfterAgent:
    def test_goal_achieved_returns_original_state(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(achieved=True, feedback="All good")
        )
        state = {"messages": [HumanMessage(content="do thing")]}
        original_messages = deepcopy(state["messages"])

        result = mw.after_agent(state, runtime=None)

        assert len(result["messages"]) == len(original_messages)
        assert mw.retry_count == 0

    def test_goal_not_achieved_adds_feedback_and_jumps(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(
                achieved=False, feedback="Missing file"
            )
        )
        state = {"messages": [HumanMessage(content="do thing")]}

        result = mw.after_agent(state, runtime=None)

        assert result["jump_to"] == "model"
        assert mw.retry_count == 1
        last_msg = result["messages"][-1]
        assert "Missing file" in last_msg.content
        assert isinstance(last_msg, HumanMessage)

    def test_max_retries_returns_state_without_jump(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(
                achieved=False, feedback="Still failing"
            )
        )
        mw.retry_count = 3
        state = {"messages": [HumanMessage(content="do thing")]}

        result = mw.after_agent(state, runtime=None)

        assert "jump_to" not in result
        assert mw.retry_count == 3

    def test_retry_increments_count(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(achieved=False, feedback="nope")
        )

        mw.after_agent({"messages": []}, runtime=None)
        assert mw.retry_count == 1

        mw.after_agent({"messages": []}, runtime=None)
        assert mw.retry_count == 2

        mw.after_agent({"messages": []}, runtime=None)
        assert mw.retry_count == 3

        result = mw.after_agent({"messages": []}, runtime=None)
        assert mw.retry_count == 3
        assert "jump_to" not in result

    def test_feedback_message_contains_goal(self, make_middleware):
        mw = make_middleware(
            goal="Create output.txt",
            structured_result=GoalValidationResult(
                achieved=False, feedback="file not found"
            ),
        )
        result = mw.after_agent({"messages": []}, runtime=None)

        feedback_msg = result["messages"][-1]
        assert "Create output.txt" in feedback_msg.content

    def test_preserves_original_messages_on_retry(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(achieved=False, feedback="retry")
        )
        original_msg = HumanMessage(content="original")
        state = {"messages": [original_msg]}

        result = mw.after_agent(state, runtime=None)

        assert result["messages"][0].content == "original"
        assert len(result["messages"]) == 2
        assert len(state["messages"]) == 1
