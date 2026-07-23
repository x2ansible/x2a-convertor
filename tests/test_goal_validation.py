"""Tests for GoalValidationMiddleware."""

from copy import deepcopy
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.middleware.goal_validation import (
    GoalValidationMiddleware,
    GoalValidationResult,
)

EXPLORE_FINDINGS = "Verified: migration-plan.md exists and contains expected content."


class FakeAgent:
    def __init__(self, structured_result=None, explore_content=EXPLORE_FINDINGS):
        self._structured_result = structured_result
        self._explore_content = explore_content

    def invoke_react(self, state, messages, metrics=None):
        return {"messages": [AIMessage(content=self._explore_content)]}

    def invoke_structured(self, schema, messages, metrics=None, max_retries=3):
        return self._structured_result

    @staticmethod
    def get_last_ai_message(result):
        messages = result.get("messages", [])
        return next(
            (msg for msg in reversed(messages) if isinstance(msg, AIMessage)),
            None,
        )


@pytest.fixture
def make_middleware():
    def _factory(
        goal="Test goal", structured_result=None, explore_content=EXPLORE_FINDINGS
    ):
        agent = FakeAgent(
            structured_result=structured_result, explore_content=explore_content
        )
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


class TestRunValidation:
    def test_goal_achieved(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(
                achieved=True, feedback="File exists"
            )
        )
        achieved, feedback = mw._run_validation({"messages": []})

        assert achieved is True
        assert feedback == "File exists"

    def test_goal_not_achieved(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(
                achieved=False, feedback="File missing"
            )
        )
        achieved, feedback = mw._run_validation({"messages": []})

        assert achieved is False
        assert feedback == "File missing"

    def test_none_result_returns_false(self, make_middleware):
        mw = make_middleware(structured_result=None)
        achieved, feedback = mw._run_validation({"messages": []})

        assert achieved is False
        assert "did not respond" in feedback

    def test_explore_prompt_contains_goal(self):
        agent = MagicMock()
        agent.invoke_react.return_value = {"messages": [AIMessage(content="findings")]}
        agent.get_last_ai_message.return_value = AIMessage(content="findings")
        agent.invoke_structured.return_value = GoalValidationResult(
            achieved=True, feedback="ok"
        )
        mw = GoalValidationMiddleware("Create output.txt", agent=agent)

        mw._run_validation({"messages": []})

        explore_messages = agent.invoke_react.call_args[1]["messages"]
        assert any("Create output.txt" in m["content"] for m in explore_messages)

    def test_classify_prompt_contains_findings(self):
        findings = "Found migration-plan.md with 3 modules listed."
        agent = MagicMock()
        agent.invoke_react.return_value = {"messages": [AIMessage(content=findings)]}
        agent.get_last_ai_message.return_value = AIMessage(content=findings)
        agent.invoke_structured.return_value = GoalValidationResult(
            achieved=True, feedback="ok"
        )
        mw = GoalValidationMiddleware("goal", agent=agent)

        mw._run_validation({"messages": []})

        classify_messages = agent.invoke_structured.call_args[1]["messages"]
        assert any(findings in m["content"] for m in classify_messages)

    def test_invoke_react_called_before_invoke_structured(self):
        call_order = []
        agent = MagicMock()
        agent.invoke_react.side_effect = lambda **kw: (
            call_order.append("react"),
            {"messages": [AIMessage(content="findings")]},
        )[1]
        agent.get_last_ai_message.return_value = AIMessage(content="findings")
        agent.invoke_structured.side_effect = lambda **kw: (
            call_order.append("structured"),
            GoalValidationResult(achieved=True, feedback="ok"),
        )[1]
        mw = GoalValidationMiddleware("goal", agent=agent)

        mw._run_validation({"messages": []})

        assert call_order == ["react", "structured"]

    def test_exception_in_explore_returns_false(self, make_middleware):
        mw = make_middleware()
        mw.agent.invoke_react = MagicMock(side_effect=RuntimeError("LLM unavailable"))
        achieved, feedback = mw._run_validation({"messages": []})

        assert achieved is False
        assert "LLM unavailable" in feedback

    def test_exception_in_classify_returns_false(self, make_middleware):
        mw = make_middleware()
        mw.agent.invoke_structured = MagicMock(side_effect=RuntimeError("timeout"))
        achieved, feedback = mw._run_validation({"messages": []})

        assert achieved is False
        assert "timeout" in feedback

    def test_in_validation_flag_cleared_after_success(self, make_middleware):
        mw = make_middleware(
            structured_result=GoalValidationResult(achieved=True, feedback="ok")
        )
        mw._run_validation({"messages": []})
        assert mw._in_validation is False

    def test_in_validation_flag_cleared_after_exception(self, make_middleware):
        mw = make_middleware()
        mw.agent.invoke_react = MagicMock(side_effect=RuntimeError("fail"))
        mw._run_validation({"messages": []})
        assert mw._in_validation is False


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

    def test_skips_validation_when_in_validation(self, make_middleware):
        mw = make_middleware()
        mw._in_validation = True
        state = {"messages": [HumanMessage(content="msg")]}

        result = mw.after_agent(state, runtime=None)

        assert result is state
