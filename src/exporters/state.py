"""State shared by the infrastructure-to-Ansible migration agents."""

from dataclasses import dataclass, field, replace
from functools import cached_property
from pathlib import Path
from typing import Self

from src.exporters.migration_report import MigrationReport
from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.types import MoleculeStatus
from src.types import (
    AAPDiscoveryResult,
    AnsibleModule,
    BaseState,
    Checklist,
    CredentialConfig,
    DocumentFile,
    MigrationStateInterface,
)
from src.types.technology import Technology


@dataclass
class ExportState(BaseState, MigrationStateInterface):
    """Migration progress and context; use update() to transition between phases."""

    module: AnsibleModule = field(kw_only=True)
    module_migration_plan: DocumentFile = field(kw_only=True)
    high_level_migration_plan: DocumentFile = field(kw_only=True)
    directory_listing: list[str] = field(kw_only=True)
    current_phase: str = field(kw_only=True)
    write_attempt_counter: int = field(kw_only=True)
    validation_attempt_counter: int = field(kw_only=True)
    validation_report: str = field(kw_only=True)
    last_output: str = field(kw_only=True)
    checklist: Checklist | None = field(default=None, kw_only=True)
    aap_discovery: AAPDiscoveryResult | None = field(default=None, kw_only=True)
    credential_config: CredentialConfig | None = field(default=None, kw_only=True)
    source_technology: Technology = field(default=Technology.CHEF, kw_only=True)
    review_report: str = field(default="", kw_only=True)
    molecule_status: MoleculeStatus = field(
        default=MoleculeStatus.NOT_GENERATED, kw_only=True
    )
    molecule_report: str = field(default="", kw_only=True)

    @cached_property
    def layout(self) -> AnsibleProjectLayout:
        return AnsibleProjectLayout.from_module(self.module)

    @property
    def role_path(self) -> Path:
        return self.layout.role_path

    @property
    def project_path(self) -> Path:
        return self.layout.project_path

    @property
    def checklist_path(self) -> Path:
        return self.layout.checklist_path

    @property
    def molecule_verify_path(self) -> Path:
        return self.layout.molecule_verify_path

    def molecule_checklist_targets(self) -> dict[str, str]:
        return self.layout.molecule_checklist_targets()

    def update(self, **kwargs) -> Self:
        return replace(self, **kwargs)

    def mark_failed(self, reason: str) -> Self:
        return self.update(failed=True, failure_reason=reason)

    def get_output(self) -> str:
        return self.last_output

    def report_status(self) -> str:
        return MigrationReport.from_state(self).render()
