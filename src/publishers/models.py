"""Validated inputs and results for AAP Config-as-Code generation."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.publishers.tools import AAPSyncResult
from src.types import AnsibleModule

AAP_CONFIG_DIRECTORY = "aap-config"
REQUIRED_INVENTORY_MARKER = "__X2A_REQUIRED_INVENTORY__"


class AAPRequestModel(BaseModel):
    """Strict base model for the local generation contract."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AAPConfigRequest(AAPRequestModel):
    """Generation settings and the target repository details."""

    project_dir: Path
    repository_root: Path
    project_id: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    inventory: str = Field(default=REQUIRED_INVENTORY_MARKER, min_length=1)
    target_repository_url: str = Field(min_length=1)
    target_branch: str = Field(min_length=1)
    scm_credential_name: str | None = Field(default=None, min_length=1)
    job_credential_names: list[str] = Field(default_factory=list)
    execution_environment_name: str | None = Field(default=None, min_length=1)

    @classmethod
    def from_project(
        cls,
        project_root: str | Path,
        *,
        project_id: str,
        project_name: str,
        module_name: str,
        organization: str,
        target_repository_url: str,
        target_branch: str,
        inventory: str | None = None,
        scm_credential_name: str | None = None,
        job_credential_names: list[str] | None = None,
        execution_environment_name: str | None = None,
    ) -> "AAPConfigRequest":
        """Build generation settings by inspecting one migrated project."""
        project_root = Path(project_root).resolve()
        project_dir = project_root / "ansible"
        if not project_dir.is_dir():
            raise ValueError(f"Ansible project directory does not exist: {project_dir}")
        if inventory == REQUIRED_INVENTORY_MARKER:
            raise ValueError(
                "inventory override must not use the required inventory marker"
            )
        return cls(
            project_dir=project_dir,
            repository_root=cls._find_repository_root(project_root),
            project_id=project_id,
            project_name=project_name,
            module_name=module_name,
            organization=organization,
            inventory=inventory or REQUIRED_INVENTORY_MARKER,
            target_repository_url=target_repository_url,
            target_branch=target_branch,
            scm_credential_name=scm_credential_name,
            job_credential_names=job_credential_names or [],
            execution_environment_name=execution_environment_name,
        )

    @staticmethod
    def _find_repository_root(project_root: Path) -> Path:
        for path in (project_root, *project_root.parents):
            if (path / ".git").exists():
                return path
        return project_root

    @field_validator("module_name")
    @classmethod
    def validate_module_name(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                "module name must not contain an absolute path or traversal"
            )
        if not str(AnsibleModule(value)):
            raise ValueError(f"Cannot derive a module name from {value!r}")
        return value

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or len(path.parts) != 1 or path.name in {".", ".."}:
            raise ValueError("project id must be a single safe path segment")
        return value

    @field_validator("job_credential_names")
    @classmethod
    def validate_credentials(cls, values: list[str]) -> list[str]:
        values = [value.strip() for value in values]
        if any(not value for value in values):
            raise ValueError("job credentials must not contain empty names")
        if len(values) != len(set(values)):
            raise ValueError("job credentials must not contain duplicate names")
        return values

    @field_validator("target_repository_url")
    @classmethod
    def validate_repository_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("repository URL must not contain credentials")
        return value

    @property
    def normalized_module_name(self) -> str:
        return str(AnsibleModule(self.module_name))

    @property
    def module_directory(self) -> Path:
        return self.project_dir / AAP_CONFIG_DIRECTORY / self.normalized_module_name

    @property
    def job_template_name(self) -> str:
        return f"{self.project_id}_{self.normalized_module_name}"

    @property
    def playbook(self) -> str:
        """Return the playbook path relative to the target repository root."""
        return self.layout.run_playbook_path.resolve().relative_to(
            self.repository_root.resolve()
        ).as_posix()

    @property
    def local_playbook(self) -> str:
        """Return the playbook path relative to the local Ansible directory."""
        return self.layout.run_playbook_path.relative_to(self.project_dir).as_posix()

    @property
    def layout(self) -> AnsibleProjectLayout:
        return AnsibleProjectLayout.from_module(
            AnsibleModule(self.module_name), project_path=self.project_dir
        )


class AAPConfigFileResult(BaseModel):
    """Result for one generated file."""

    path: Path
    status: Literal["created", "updated", "unchanged"]


class AAPConfigGenerationResult(BaseModel):
    """Structured generation result returned by the publish operation."""

    changed: bool
    module_name: str
    module_directory: Path
    project_name: str
    job_template_name: str
    files: list[AAPConfigFileResult]


class PublishResult(BaseModel):
    """Structured result containing both generation and AAP synchronization."""

    generation: AAPConfigGenerationResult
    sync: AAPSyncResult
