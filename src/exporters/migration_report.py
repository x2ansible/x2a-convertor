"""Render human-readable migration summaries from export state."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.exporters.types import MoleculeStatus
from src.types.checklist import ChecklistStats

if TYPE_CHECKING:
    from src.exporters.state import ExportState


@dataclass(frozen=True)
class MigrationReport:
    """Immutable report data and rendering behavior for one migration result."""

    module: str
    failed: bool
    failure_reason: str
    stats: ChecklistStats
    write_attempts: int
    validation_attempts: int
    validation_report: str
    review_report: str
    molecule_status: MoleculeStatus
    molecule_report: str
    checklist_markdown: str
    telemetry_summary: str | None

    @classmethod
    def from_state(cls, state: "ExportState") -> "MigrationReport":
        """Build report data from the owning export state."""
        assert state.checklist is not None, (
            "Checklist must be initialized before reporting"
        )
        return cls(
            module=str(state.module),
            failed=state.failed,
            failure_reason=state.failure_reason,
            stats=state.checklist.get_stats(),
            write_attempts=state.write_attempt_counter,
            validation_attempts=state.validation_attempt_counter,
            validation_report=state.validation_report,
            review_report=state.review_report,
            molecule_status=MoleculeStatus(state.molecule_status),
            molecule_report=state.molecule_report,
            checklist_markdown=state.checklist.to_markdown(),
            telemetry_summary=(
                state.telemetry.to_summary() if state.telemetry else None
            ),
        )

    def render(self) -> str:
        """Render the complete report as Markdown."""
        lines = self._heading_lines()
        report_kind = "Partial" if self.failed else "Final"
        lines.extend(
            [
                self.stats.to_markdown(),
                f"- **Write attempts:** {self.write_attempts}",
                f"- **Validation attempts:** {self.validation_attempts}",
                "",
                f"## {report_kind} Validation Report",
                "",
                self.validation_report or ("_Not run_" if self.failed else ""),
            ]
        )
        if self.review_report:
            lines.extend(["", "### Review Report", "", self.review_report])
        lines.extend(self._molecule_lines())
        lines.extend(["", f"### {report_kind} Checklist", "", self.checklist_markdown])
        if self.telemetry_summary:
            lines.extend(["", "## Telemetry", "", "```", self.telemetry_summary, "```"])
        return "\n".join(lines)

    def _heading_lines(self) -> list[str]:
        if not self.failed:
            return [f"# Migration Summary for {self.module}", ""]
        return [
            f"# MIGRATION FAILED for {self.module}",
            "",
            f"**Failure Reason:** {self.failure_reason}",
            "",
            "## Migration Summary",
            "",
        ]

    def _molecule_lines(self) -> list[str]:
        """Report generated test status without implying runtime execution."""
        if self.molecule_status == MoleculeStatus.NOT_GENERATED:
            return []
        return [
            "",
            "### Molecule Test Generation",
            "",
            f"**Status:** {self.molecule_status.value}",
            "",
            self.molecule_report
            or "Molecule tests were not executed by the converter.",
        ]
