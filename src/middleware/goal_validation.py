"""Goal validation middleware with retry logic."""

from copy import deepcopy
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_core.messages import HumanMessage
from langchain_core.messages.utils import get_buffer_string
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

EXPLORE_PROMPT_TEMPLATE = """You are a read-only verification agent. Use the available tools to check whether the following goal was achieved. Do NOT create, write, or modify any files.

<goal>
{goal}
</goal>

CONVERSATION CONTEXT:
<messages>
{context}
</messages>

Use the tools to inspect the relevant files and report exactly what you found.
"""

CLASSIFY_PROMPT_TEMPLATE = """Based on the following verification findings, determine whether the goal was achieved.

<goal>
{goal}
</goal>

<findings>
{findings}
</findings>
"""

RETRY_MESSAGE_TEMPLATE = """The goal was not achieved. Please address the following issues:

{feedback}

Remember the goal: {goal}

Please try again."""


class GoalValidationResult(BaseModel):
    achieved: bool = Field(
        description="Whether the goal was achieved (true) or not (false)"
    )
    feedback: str = Field(
        description="Specific feedback about what was verified or what is missing/incorrect"
    )


class GoalValidationMiddleware(AgentMiddleware):
    """Validates goal achievement after agent execution, retrying up to MAX_RETRIES times."""

    name = "GoalValidation"
    MAX_RETRIES = 3
    CONTEXT_HEAD = 3
    CONTEXT_TAIL = 2

    def __init__(self, goal_description: str, agent: Any):
        self._log = get_logger(__name__)
        self.goal_description = goal_description
        self.agent = agent
        self.retry_count = 0
        # Guards against re-entrant validation: invoke_react runs through the
        # agent's cached middleware stack, which includes this same instance.
        # Without this flag, after_agent would fire again after the explore
        # phase completes, causing infinite recursion.
        self._in_validation = False

    def _extract_context_messages(self, messages: list) -> list:
        max_passthrough = self.CONTEXT_HEAD + self.CONTEXT_TAIL
        if len(messages) <= max_passthrough:
            return messages
        return messages[: self.CONTEXT_HEAD] + messages[-self.CONTEXT_TAIL :]

    def _run_validation(self, state: dict) -> tuple[bool, str]:
        self._log.info("Running goal validation", retry_count=self.retry_count)

        messages = state.get("messages", [])
        context_messages = self._extract_context_messages(messages)
        context_text = get_buffer_string(context_messages)

        explore_prompt = EXPLORE_PROMPT_TEMPLATE.format(
            goal=self.goal_description,
            context=context_text,
        )

        try:
            self._in_validation = True
            explore_result = self.agent.invoke_react(
                state=state,
                messages=[{"role": "user", "content": explore_prompt}],
            )

            last_ai = self.agent.get_last_ai_message(explore_result)
            findings = last_ai.text if last_ai else "No findings available"

            classify_prompt = CLASSIFY_PROMPT_TEMPLATE.format(
                goal=self.goal_description,
                findings=findings,
            )
            result = self.agent.invoke_structured(
                schema=GoalValidationResult,
                messages=[{"role": "user", "content": classify_prompt}],
            )

            if not result:
                self._log.warning("No response from validation")
                return False, "Validation did not respond"

            self._log.debug(
                "Validation result",
                achieved=result.achieved,
                feedback=result.feedback,
            )
            return result.achieved, result.feedback

        except Exception as e:
            self._log.error("Validation failed", error=str(e))
            return False, f"Validation error: {e!s}"
        finally:
            self._in_validation = False

    @hook_config(can_jump_to=["model"])
    def after_agent(self, state, runtime):
        if self._in_validation:
            return state

        original_state = deepcopy(state)

        self._log.info(
            "Goal validation after_agent",
            retry_count=self.retry_count,
            max_retries=self.MAX_RETRIES,
            messages_count=len(state.get("messages", [])),
        )

        goal_achieved, feedback = self._run_validation(state)

        if goal_achieved:
            self._log.info("Goal achieved", feedback=feedback)
            return original_state

        self._log.warning(
            "Goal not achieved",
            retry_count=self.retry_count,
            feedback=feedback,
        )

        if self.retry_count >= self.MAX_RETRIES:
            self._log.error("Max retries reached", feedback=feedback)
            return state

        self.retry_count += 1
        messages = list(original_state.get("messages", []))
        messages.append(
            HumanMessage(
                content=RETRY_MESSAGE_TEMPLATE.format(
                    feedback=feedback, goal=self.goal_description
                )
            )
        )

        self._log.info(
            "Retrying with feedback",
            retry_count=self.retry_count,
            feedback=feedback[:100],
        )

        return {
            "messages": messages,
            "jump_to": "model",
        }
