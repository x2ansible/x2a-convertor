"""Generate self-contained, module-owned AAP Config-as-Code files."""

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from src.publishers.models import (
    AAPConfigFileResult,
    AAPConfigGenerationResult,
    AAPConfigRequest,
)


class AAPConfigAsCodeGenerator:
    """Write deterministic AAP Project and Job Template documents."""

    def __init__(self, request: AAPConfigRequest) -> None:
        self.request = request
        self.project_dir = request.project_dir.resolve()
        self.module_directory = request.module_directory.resolve()

    def generate(self) -> AAPConfigGenerationResult:
        """Validate inputs and atomically write both generated documents."""
        self._validate_inputs()
        documents = self._documents()
        files = [self._write_yaml_if_changed(path, data) for path, data in documents]
        return AAPConfigGenerationResult(
            changed=any(item.status != "unchanged" for item in files),
            module_name=self.request.normalized_module_name,
            module_directory=self.module_directory,
            project_name=self.request.project_name,
            job_template_name=self.request.job_template_name,
            files=files,
        )

    def _validate_inputs(self) -> None:
        if not self.project_dir.is_dir():
            raise ValueError(f"Project directory does not exist: {self.project_dir}")
        playbook = (self.project_dir / self.request.local_playbook).resolve()
        if not playbook.is_relative_to(self.project_dir):
            raise ValueError("Generated playbook path escapes the project directory")
        if not playbook.is_file():
            raise ValueError(f"Ansible playbook does not exist: {playbook}")
        if not self.module_directory.is_relative_to(self.project_dir):
            raise ValueError("AAP configuration path escapes the project directory")

    def _documents(self) -> list[tuple[Path, dict[str, Any]]]:
        project_entry: dict[str, Any] = {
            "name": self.request.project_name,
            "organization": self.request.organization,
            "scm_type": "git",
            "scm_url": self.request.target_repository_url,
            "scm_branch": self.request.target_branch,
            "scm_update_on_launch": True,
            "scm_clean": True,
            "scm_delete_on_update": True,
            "update_project": True,
            "wait": True,
        }
        if self.request.scm_credential_name is not None:
            project_entry["scm_credential"] = self.request.scm_credential_name

        job_template_entry: dict[str, Any] = {
            "name": self.request.job_template_name,
            "organization": self.request.organization,
            "project": self.request.project_name,
            "job_type": "run",
            "playbook": self.request.playbook,
            "inventory": self.request.inventory,
            "prevent_instance_group_fallback": False,
        }
        if self.request.job_credential_names:
            job_template_entry["credentials"] = self.request.job_credential_names
        if self.request.execution_environment_name is not None:
            job_template_entry["execution_environment"] = (
                self.request.execution_environment_name
            )

        module_name = self.request.normalized_module_name
        project = {f"controller_projects_x2a_{module_name}": [project_entry]}
        job_template = {
            f"controller_templates_x2a_{module_name}": [job_template_entry]
        }
        return [
            (self.module_directory / "controller_projects.yml", project),
            (self.module_directory / "controller_job_templates.yml", job_template),
        ]

    @staticmethod
    def _serialize(document: dict[str, Any]) -> str:
        return yaml.safe_dump(document, sort_keys=False, explicit_start=True)

    def _write_yaml_if_changed(
        self, path: Path, document: dict[str, Any]
    ) -> AAPConfigFileResult:
        content = self._serialize(document)
        return self._write_content_if_changed(path, content)

    def _write_content_if_changed(
        self, path: Path, content: str
    ) -> AAPConfigFileResult:
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            return AAPConfigFileResult(path=path, status="unchanged")
        status = "updated" if path.exists() else "created"
        self._atomic_write(path, content)
        return AAPConfigFileResult(path=path, status=status)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        old_mode = path.stat().st_mode if path.exists() else None
        descriptor, temporary_name = tempfile.mkstemp(dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if old_mode is not None:
                temporary_path.chmod(old_mode)
            temporary_path.replace(path)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
