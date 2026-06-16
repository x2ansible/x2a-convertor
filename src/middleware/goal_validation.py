"""Goal validation middleware with retry logic."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any, ClassVar

from langchain.agents.middleware.types import AgentMiddleware, hook_config
from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

VALIDATION_PROMPT_TEMPLATE = """You are a read-only goal validation agent. Your ONLY job is to CHECK whether the following goal was achieved. You must NEVER create, write, or modify any files.

GOAL: {goal}

CONVERSATION CONTEXT:
{context}

Use ONLY the read-only tools (read_file, list_directory, file_search) to inspect existing files and verify the goal was met. Do NOT attempt to fix, create, or write anything.

Provide:
- achieved: true if the goal is fully met, false otherwise
- feedback: Specific details about what was verified or what is missing/incorrect
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

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: FileSearchTool(),
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
    ]

    def __init__(self, goal_description: str, agent: Any):
        self._log = get_logger(__name__)
        self.goal_description = goal_description
        self.agent = agent
        self.retry_count = 0

    def _extract_context_messages(self, messages: list) -> list:
        max_passthrough = self.CONTEXT_HEAD + self.CONTEXT_TAIL
        if len(messages) <= max_passthrough:
            return messages
        return messages[: self.CONTEXT_HEAD] + messages[-self.CONTEXT_TAIL :]

    def _build_validation_prompt(self, context_messages: list) -> str:
        context_text = "\n\n".join(
            f"[{msg.__class__.__name__}] {msg.content}"
            for msg in context_messages
            if hasattr(msg, "content")
        )
        return VALIDATION_PROMPT_TEMPLATE.format(
            goal=self.goal_description, context=context_text
        )

    def _run_validation(self, state: dict) -> tuple[bool, str]:
        self._log.info("Running goal validation", retry_count=self.retry_count)

        messages = state.get("messages", [])
        context_messages = self._extract_context_messages(messages)
        validation_prompt = self._build_validation_prompt(context_messages)

        try:
            validation_tools = [factory() for factory in self.BASE_TOOLS]
            validation_result = self.agent.invoke_structured(
                schema=GoalValidationResult,
                messages=[{"role": "user", "content": validation_prompt}],
                metrics=None,
                tools=validation_tools,
            )

            if not validation_result:
                self._log.warning("No response from validation")
                return False, "Validation did not respond"

            self._log.debug(
                "Validation result",
                achieved=validation_result.achieved,
                feedback=validation_result.feedback,
            )
            return validation_result.achieved, validation_result.feedback

        except Exception as e:
            self._log.error("Validation failed", error=str(e))
            return False, f"Validation error: {e!s}"

    @hook_config(can_jump_to=["model"])
    def after_agent(self, state, runtime):
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
