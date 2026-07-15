"""Adversarial agents package for validating migration artifacts."""

import json
from pathlib import Path
from typing import Any

from src.adversarial.adversarial_agent import AdversarialAgent
from src.adversarial.adversarial_agent_manager import AdversarialAgentManager
from src.adversarial.findings_reporter import (
    AdversarialFinding,
    AdversarialReport,
    append_to_report,
    format_markdown,
    has_findings,
)
from src.const import ADVERSARIAL_REPORT_FILENAME
from src.types.base_state import BaseState
from src.types.telemetry import Telemetry
from src.utils.logging import get_logger

_log = get_logger(__name__)


def run_adversarial(
    phase: str,
    source_dir: str = ".",
    config_path: str | None = None,
    report_path: Path | None = None,
) -> list[AdversarialReport]:
    """Run adversarial agents for a given phase and persist telemetry and summary.

    Owns the full telemetry lifecycle: create, wire into agents, stop, save.
    Writes agent-adversarial-report.json to the current directory.
    """
    _log.info(f"Starting adversarial run for phase '{phase}'")

    telemetry = Telemetry(phase=f"adversarial-{phase}")
    state = BaseState(user_message="", path=source_dir)
    manager = AdversarialAgentManager(phase=phase, config_path=config_path)

    reports = manager.run_phase(
        state=state, telemetry=telemetry, report_path=report_path
    )

    telemetry.stop().save()
    _log.info(f"Telemetry summary:\n{telemetry.to_summary()}")

    _write_summary(phase, manager.agents)

    return reports


def _write_summary(phase: str, agents: list[AdversarialAgent]) -> None:
    agent_summaries: list[dict[str, Any]] = []
    for agent in agents:
        report = agent.report
        if report is None:
            continue
        critical = sum(1 for f in report.findings if f.severity == "CRITICAL")
        agent_summaries.append(
            {
                "name": agent.agent_name,
                "findings": len(report.findings),
                "critical_findings": critical,
                "summary": report.summary,
            }
        )

    total_findings = sum(a["findings"] for a in agent_summaries)
    total_critical = sum(a["critical_findings"] for a in agent_summaries)

    payload = {
        "phase": phase,
        "agents_run": len(agent_summaries),
        "total_findings": total_findings,
        "total_critical_findings": total_critical,
        "agents": agent_summaries,
    }

    output = Path(ADVERSARIAL_REPORT_FILENAME)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _log.info("Adversarial summary written", path=str(output))


__all__ = [
    "AdversarialAgent",
    "AdversarialAgentManager",
    "AdversarialFinding",
    "AdversarialReport",
    "append_to_report",
    "format_markdown",
    "has_findings",
    "run_adversarial",
]
