"""Formats adversarial findings as markdown and appends them to phase reports."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AdversarialFinding(BaseModel):
    """A single finding produced by an adversarial agent."""

    severity: Literal["CRITICAL", "WARNING"] = Field(
        description="Severity level of the finding"
    )
    location: str = Field(description="File path or resource where the issue was found")
    description: str = Field(description="What the issue is")
    evidence: str = Field(
        description="Supporting evidence from the source code or configuration"
    )


class AdversarialReport(BaseModel):
    """Structured output from an adversarial agent run."""

    findings: list[AdversarialFinding] = Field(
        default_factory=list, description="List of findings from the analysis"
    )
    summary: str = Field(
        default="", description="Brief summary of the analysis results"
    )


def has_findings(findings: list[AdversarialFinding]) -> bool:
    return len(findings) > 0


def format_markdown(agent_name: str, report: AdversarialReport) -> str:
    lines = [
        "\n\n## Adversarial Review Findings",
        f"\n**Agent:** {agent_name}",
    ]

    if report.summary:
        lines.append(f"\n**Summary:** {report.summary}")

    if not report.findings:
        lines.append("\nNo findings detected.")
        lines.append("\n---")
        return "\n".join(lines)

    for finding in report.findings:
        lines.append(f"\n### [{finding.severity}] {finding.location}")
        lines.append(f"\n{finding.description}")
        lines.append(f"\n**Evidence:**\n```\n{finding.evidence}\n```")

    lines.append("\n---")
    return "\n".join(lines)


def append_to_report(
    report_path: Path, agent_name: str, report: AdversarialReport
) -> None:
    content = format_markdown(agent_name, report)
    with report_path.open("a", encoding="utf-8") as f:
        f.write(content)
