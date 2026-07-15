"""Orchestrates adversarial agent execution for a given workflow phase."""

import json
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel

from src.adversarial.adversarial_agent import AdversarialAgent
from src.adversarial.findings_reporter import AdversarialReport, append_to_report
from src.model import get_model
from src.types.base_state import BaseState
from src.types.telemetry import Telemetry, telemetry_context
from src.utils.logging import get_logger

_log = get_logger(__name__)


class AdversarialAgentManager:
    """Loads agent definitions from a JSON config and runs them for a given phase."""

    def __init__(
        self,
        phase: str,
        config_path: str | None = None,
        model: BaseChatModel | None = None,
    ):
        self._model = model or get_model()
        self.agents = self._load_agents(phase, config_path) if config_path else []

    def _load_agents(self, phase: str, path: str) -> list[AdversarialAgent]:
        config_file = Path(path)
        if not config_file.exists():
            _log.warning("Adversarial agents config not found", path=path)
            return []
        raw = json.loads(config_file.read_text(encoding="utf-8"))
        agents = [
            AdversarialAgent.from_dict(item, model=self._model)
            for item in raw
            if phase in item.get("phases", [])
        ]
        _log.info(
            f"Loaded {len(agents)} adversarial agent(s) for phase '{phase}'", path=path
        )
        return agents

    def run_phase(
        self,
        state: BaseState,
        telemetry: Telemetry | None = None,
        report_path: Path | None = None,
    ) -> list[AdversarialReport]:
        """Run all loaded agents and return their reports."""
        if not self.agents:
            _log.info("No adversarial agents loaded")
            return []

        _log.info(f"Running {len(self.agents)} adversarial agent(s)")
        reports = []

        for agent in self.agents:
            with telemetry_context(telemetry, agent.agent_name) as metrics:
                agent.execute(state, metrics)
            report = agent.report
            if report is None:
                continue
            reports.append(report)
            if report_path:
                append_to_report(report_path, agent.agent_name, report)

        return reports
