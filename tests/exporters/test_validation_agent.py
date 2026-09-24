"""Tests for validation exception handling in ValidationAgent."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.exporters.agent_state import ValidationAgentState
from src.exporters.state import ExportState
from src.exporters.tools.apme import CheckReport, CheckViolation
from src.exporters.validation_agent import SkipValidationDecision, ValidationAgent
from src.types import AnsibleModule, DocumentFile
from src.types.telemetry import AgentMetrics


@pytest.fixture()
def export_state(tmp_path: Path) -> ExportState:
    """Build the smallest ExportState accepted by the validation node."""
    return ExportState(
        user_message="migrate this",
        path=str(tmp_path),
        module=AnsibleModule("example"),
        module_migration_plan=DocumentFile(path=Path("plan.md"), content="plan"),
        high_level_migration_plan=DocumentFile(
            path=Path("high-level.md"), content="plan"
        ),
        directory_listing=[],
        current_phase="validating",
        write_attempt_counter=0,
        validation_attempt_counter=0,
        validation_report="",
        last_output="",
    )


def validation_agent(apme_result) -> ValidationAgent:
    """Create a validation agent without constructing an LLM."""
    agent = object.__new__(ValidationAgent)
    agent._apme = MagicMock()
    if isinstance(apme_result, Exception):
        agent._apme.check.side_effect = apme_result
    else:
        agent._apme.check.return_value = apme_result
    return agent


def violation_report() -> CheckReport:
    return CheckReport(
        violations=[
            CheckViolation(
                rule_id="R401",
                severity="error",
                message="inbound sources are not listed",
                file="molecule/default/converge.yml",
            )
        ]
    )


def test_validation_still_fails_when_previous_report_rejects_exception(export_state):
    agent = validation_agent(violation_report())
    agent.invoke_structured = MagicMock(return_value=SkipValidationDecision(skip=False))
    state = ValidationAgentState(
        export_state=export_state.update(
            validation_report="The issue must still be fixed."
        )
    )

    result = agent._validate_node(state)

    assert result.has_errors is True
    assert result.complete is False
    agent.invoke_structured.assert_called_once()


def test_validation_accepts_explicit_exception_from_previous_report(export_state):
    agent = validation_agent(violation_report())
    agent.invoke_structured = MagicMock(return_value=SkipValidationDecision(skip=True))
    metrics = AgentMetrics(name="validator")
    state = ValidationAgentState(
        export_state=export_state.update(
            validation_report=(
                "R401 is acceptable in Molecule converge.yml files; "
                "do not modify the fixture."
            )
        ),
        metrics=metrics,
    )

    result = agent._validate_node(state)

    assert result.complete is True
    assert result.has_errors is False
    assert "R401 is acceptable" in result.export_state.validation_report
    assert agent.invoke_structured.call_args.args[2] is metrics


def test_apme_failure_can_use_an_accepted_previous_report(export_state):
    agent = validation_agent(RuntimeError("APME unavailable"))
    agent.invoke_structured = MagicMock(return_value=SkipValidationDecision(skip=True))
    state = ValidationAgentState(
        export_state=export_state.update(
            validation_report="The remaining R401 violation is intentional."
        )
    )

    result = agent._validate_node(state)

    assert result.complete is True
    assert result.export_state.failed is False
    assert "The remaining R401 violation is intentional" in (
        result.export_state.validation_report
    )


def test_empty_previous_report_is_not_sent_to_the_model(export_state):
    agent = validation_agent(violation_report())
    agent.invoke_structured = MagicMock()
    state = ValidationAgentState(export_state=export_state)

    result = agent._validate_node(state)

    assert result.has_errors is True
    agent.invoke_structured.assert_not_called()
