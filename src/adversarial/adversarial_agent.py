"""Adversarial agent that checks migration artifacts for issues.

Each adversarial agent is instantiated from a JSON config entry (loaded from
ConfigMap) and runs with read-only tools to explore source/target code,
producing structured findings without modifying any files.
"""

from collections.abc import Callable
from typing import ClassVar, Literal

from langchain_community.tools.file_management.file_search import FileSearchTool
from langchain_community.tools.file_management.list_dir import ListDirectoryTool
from langchain_community.tools.file_management.read import ReadFileTool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool

from prompts.get_prompt import get_prompt
from src.adversarial.findings_reporter import AdversarialReport
from src.base_agent import BaseAgent
from src.types.base_state import BaseState
from src.types.telemetry import AgentMetrics
from tools.diff_file import DiffFileTool
from tools.grep_file import GrepFileTool

Phase = Literal["analyze", "migrate"]


class AdversarialAgent(BaseAgent[BaseState]):
    """Agent that validates migration artifacts using a configurable prompt.

    Instantiated directly from JSON config. Uses read-only tools to explore
    the codebase, then extracts structured findings via LLM.
    """

    BASE_TOOLS: ClassVar[list[Callable[[], BaseTool]]] = [
        lambda: ReadFileTool(),
        lambda: ListDirectoryTool(),
        lambda: FileSearchTool(),
        lambda: GrepFileTool(),
        lambda: DiffFileTool(),
    ]

    SYSTEM_PROMPT_NAME = "adversarial_system"
    USER_PROMPT_NAME = "adversarial_task"

    def __init__(
        self,
        name: str,
        prompt: str,
        phases: list[Phase],
        critical: bool = False,
        model: BaseChatModel | None = None,
    ):
        self._agent_name = name
        self.prompt = prompt
        self.phases = phases
        self.critical = critical
        self._report: AdversarialReport | None = None
        super().__init__(model)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        model: BaseChatModel | None = None,
    ) -> "AdversarialAgent":
        return cls(
            name=data["name"],
            prompt=data["prompt"],
            phases=data["phases"],
            critical=data.get("critical", False),
            model=model,
        )

    @property
    def agent_name(self) -> str:
        return self._agent_name

    @property
    def report(self) -> AdversarialReport | None:
        return self._report

    def execute(self, state: BaseState, metrics: AgentMetrics | None) -> BaseState:
        """Run adversarial analysis and store findings.

        The state is returned unchanged -- findings are accessible via
        the ``report`` property after execution.
        """
        evidence = self._collect_evidence(state, metrics)
        self._report = self._extract_findings(evidence, metrics)

        if metrics:
            finding_count = len(self._report.findings)
            critical_count = sum(
                1 for f in self._report.findings if f.severity == "CRITICAL"
            )
            metrics.record_metric("findings", finding_count)
            metrics.record_metric("critical_findings", critical_count)

        self._log.info(
            f"Analysis complete: {len(self._report.findings)} finding(s)",
        )
        return state

    def _collect_evidence(self, state: BaseState, metrics: AgentMetrics | None) -> str:
        """Investigate the workspace with read-only tools and return the agent's analysis."""
        default_severity = "CRITICAL" if self.critical else "WARNING"
        system_prompt = get_prompt(self.SYSTEM_PROMPT_NAME).format(
            default_severity=default_severity,
        )
        user_prompt = get_prompt(self.USER_PROMPT_NAME).format(
            agent_prompt=self.prompt,
            source_path=state.path,
        )

        result = self.invoke_react(
            state,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            metrics,
        )

        message = self.get_last_ai_message(result)
        if message is None:
            return ""
        return str(message.text)

    def _extract_findings(
        self, content: str, metrics: AgentMetrics | None
    ) -> AdversarialReport:
        """Extract structured findings from the exploration output."""
        if not content.strip():
            return AdversarialReport(findings=[], summary="No analysis output produced")

        extraction_messages = [
            {
                "role": "user",
                "content": (
                    "Extract all findings from the following adversarial analysis "
                    "into structured output.\n\n"
                    f"Analysis output:\n{content}"
                ),
            },
        ]

        result = self.invoke_structured(AdversarialReport, extraction_messages, metrics)

        if isinstance(result, AdversarialReport):
            return result

        self._log.warning("Structured extraction failed, returning empty report")
        return AdversarialReport(
            findings=[], summary="Failed to extract structured findings"
        )
