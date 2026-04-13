"""Review agent for semantic correctness of generated Ansible roles.

Identifies and fixes runtime issues that static linters cannot detect:
missing prerequisites, missing package dependencies, idempotency failures,
and task ordering problems.
"""

from collections.abc import Callable
from typing import ClassVar

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.exporters.state import ExportState
from src.types.telemetry import AgentMetrics
from tools.ansible_write import AnsibleWriteTool
from tools.validated_write import ValidatedWriteTool


class ReviewAgent(BaseAgent[ExportState]):
    """Agent that reviews generated Ansible roles for semantic correctness.

    Detects and fixes runtime issues that ansible-lint cannot catch:
    - Missing prerequisites (user/group not created before ownership reference)
    - Missing package dependencies (config files for uninstalled packages)
    - Idempotency failures (commands without creates/removes guards)
    - Ordering issues (service config before package install)

    Uses read-only tools to scan the role, then write tools to apply
    minimal fixes directly. Single ReAct pass -- no internal graph.
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ListDirectoryTool(),
        lambda: ReadFileTool(),
        lambda: FileSearchTool(),
        lambda: ValidatedWriteTool(),
        lambda: AnsibleWriteTool(),
    ]

    SYSTEM_PROMPT_NAME = "export_ansible_review_system"
    USER_PROMPT_NAME = "export_ansible_review_task"

    def execute(self, state: ExportState, metrics: AgentMetrics | None) -> ExportState:
        """Execute semantic review and apply minimal fixes.

        The agent reads all task files in the generated role, identifies
        semantic issues, and writes corrected files directly. The review
        report is stored in validation_report for downstream visibility.
        """
        self._log.info("Reviewing generated role for semantic correctness")

        ansible_path = state.get_ansible_path()

        system_message = get_prompt(self.SYSTEM_PROMPT_NAME).format()
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            module=state.module,
            ansible_path=ansible_path,
            source_path=state.path,
            source_technology=state.source_technology.value,
            checklist=state.checklist.to_markdown() if state.checklist else "",
        )

        result = self.invoke_react(
            state,
            [
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_prompt},
            ],
            metrics,
        )

        message = self.get_last_ai_message(result)
        review_report = message.content if message else ""

        self._log.info(f"Review complete. Report length: {len(review_report)} chars")

        return state.update(review_report=review_report)
