"""Inventory representation of an isolated, disposable Podman test target."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Self

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_contract import (
    DEFAULT_LINUX_IMAGE,
    PODMAN_COLLECTION,
    SYSTEMD_COMMAND,
    SYSTEMD_MODE,
)


@dataclass(frozen=True)
class PodmanTestTarget:
    """Container identity and settings, independent of Molecule driver plugins."""

    name: str
    image: str = DEFAULT_LINUX_IMAGE
    command: str = SYSTEMD_COMMAND
    systemd: str = SYSTEMD_MODE
    privileged: bool = True

    @classmethod
    def from_layout(cls, layout: AnsibleProjectLayout) -> Self:
        """Scope names to the checkout and role so destroy cannot cross projects."""
        identity = f"{layout.project_path.resolve()}:{layout.fqcn}"
        suffix = sha256(identity.encode()).hexdigest()[:12]
        return cls(name=f"x2a_{layout.module}_{suffix}")

    def to_inventory(self) -> dict[str, Any]:
        """Return standard Ansible inventory; image overrides resolve at runtime."""
        variables = {
            "ansible_connection": f"{PODMAN_COLLECTION}.podman",
            "ansible_user": "root",
            "ansible_python_interpreter": "/usr/bin/python3",
            "container_image": (
                "{{ lookup('ansible.builtin.env', 'X2A_MOLECULE_IMAGE') "
                f"| default('{self.image}', true) }}}}"
            ),
            "container_command": self.command,
            "container_systemd": self.systemd,
            "container_privileged": self.privileged,
        }
        return {"all": {"children": {"molecule": {"hosts": {self.name: variables}}}}}
