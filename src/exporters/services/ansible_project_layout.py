"""Filesystem layout for the generated Ansible project and collection role."""

from dataclasses import dataclass
from pathlib import Path
from typing import Self

from src.types import AnsibleModule

DEFAULT_NAMESPACE = "x2a"
DEFAULT_PROJECT = "project"
ANSIBLE_PROJECT_PATH = Path("ansible")
CHECKLIST_FILENAME = ".checklist.json"


@dataclass(frozen=True)
class AnsibleProjectLayout:
    """Project identity with derived paths that cannot drift apart."""

    module: AnsibleModule
    namespace: str
    project_name: str
    project_path: Path

    @classmethod
    def from_module(
        cls,
        module: AnsibleModule,
        project_path: str | Path = ANSIBLE_PROJECT_PATH,
        namespace: str = DEFAULT_NAMESPACE,
        project_name: str = DEFAULT_PROJECT,
    ) -> Self:
        return cls(module, namespace, project_name, Path(project_path))

    @property
    def collection_path(self) -> Path:
        return (
            self.project_path
            / "collections"
            / "ansible_collections"
            / self.namespace
            / self.project_name
        )

    @property
    def role_path(self) -> Path:
        return self.collection_path / "roles" / str(self.module)

    @property
    def fqcn(self) -> str:
        return f"{self.namespace}.{self.project_name}.{self.module}"

    @property
    def run_playbook_path(self) -> Path:
        return self.project_path / f"run_{self.module}.yml"

    @property
    def checklist_path(self) -> Path:
        return self.role_path / CHECKLIST_FILENAME

    @property
    def migration_report_path(self) -> Path:
        return self.role_path / "export-output.md"

    @property
    def requirements_search_paths(self) -> tuple[Path, ...]:
        return (
            self.role_path / "requirements.yml",
            self.collection_path / "requirements.yml",
            self.project_path / "collections" / "requirements.yml",
            self.project_path / "requirements.yml",
        )

    @property
    def molecule_scenario_path(self) -> Path:
        return self.project_path / "molecule" / str(self.module)

    @property
    def molecule_requirements_path(self) -> Path:
        return self.project_path / "molecule" / "requirements.yml"

    @property
    def molecule_readme_path(self) -> Path:
        return self.project_path / "molecule" / "README.md"

    @property
    def molecule_verify_path(self) -> Path:
        return self.molecule_scenario_path / "verify.yml"

    def molecule_checklist_targets(self) -> dict[str, str]:
        scenario = self.molecule_scenario_path
        targets = {
            self.run_playbook_path: "Deployment entry point for the migrated role",
            self.molecule_requirements_path: "Test-only Podman collection dependency",
            self.molecule_readme_path: "Developer instructions for running Molecule",
            scenario / "molecule.yml": "Ansible-native Molecule scenario configuration",
            scenario / "inventory" / "hosts.yml": "Disposable Podman target inventory",
            scenario / "create.yml": "Create and inspect disposable Podman targets",
            scenario / "destroy.yml": "Remove disposable Podman targets",
            scenario / "prepare.yml": "Bootstrap Python on the disposable Linux target",
            scenario / "converge.yml": "Run the deployment playbook under test",
            self.molecule_verify_path: "Verify migrated behavior against the source plan",
        }
        return {str(path): description for path, description in targets.items()}
