"""Render deterministic Ansible-native Molecule project artifacts."""

from pathlib import Path

import yaml

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_contract import (
    COLLECTIONS_PATH_TEMPLATE,
    INVENTORY_ARGUMENT,
    LIFECYCLE_ACTIONS,
    PODMAN_COLLECTION,
    REQUIREMENTS_FILE,
    TEST_SEQUENCE,
)
from src.exporters.services.podman_test_target import PodmanTestTarget


class MoleculeScenarioTemplates:
    """Produce scenario file paths and contents without performing file I/O."""

    def __init__(self, layout: AnsibleProjectLayout) -> None:
        self.layout = layout

    def files(self) -> dict[Path, str]:
        """Return deterministic artifacts; only verification belongs to the LLM."""
        scenario = self.layout.molecule_scenario_path
        target = PodmanTestTarget.from_layout(self.layout)
        return {
            self.layout.run_playbook_path: self._deployment_playbook(),
            self.layout.molecule_requirements_path: self._requirements(),
            self.layout.molecule_readme_path: self._instructions(),
            scenario / "molecule.yml": self._molecule_config(),
            scenario / "inventory" / "hosts.yml": yaml.safe_dump(
                target.to_inventory(), sort_keys=False, explicit_start=True
            ),
            scenario / "create.yml": self._create_playbook(),
            scenario / "destroy.yml": self._destroy_playbook(),
            scenario / "prepare.yml": self._prepare_playbook(),
            scenario / "converge.yml": self._converge_playbook(),
        }

    def _deployment_playbook(self) -> str:
        module = self.layout.module
        return f"""---
- name: Run migrated role {module}
  hosts: all
  gather_facts: true
  tasks:
    - name: Apply {module} role
      ansible.builtin.include_role:
        name: {self.layout.fqcn}
"""

    @staticmethod
    def _requirements() -> str:
        return f"""---
collections:
  - name: {PODMAN_COLLECTION}
    version: ">=1.10.0"
roles: []
"""

    @staticmethod
    def _molecule_config() -> str:
        config = {
            "shared_state": False,
            "dependency": {
                "name": "galaxy",
                "options": {
                    "requirements-file": REQUIREMENTS_FILE,
                    "role-file": REQUIREMENTS_FILE,
                },
                "env": {"ANSIBLE_COLLECTIONS_PATH": COLLECTIONS_PATH_TEMPLATE},
            },
            "ansible": {
                "executor": {
                    "backend": "ansible-playbook",
                    "args": {"ansible_playbook": [INVENTORY_ARGUMENT]},
                },
                "env": {"ANSIBLE_COLLECTIONS_PATH": COLLECTIONS_PATH_TEMPLATE},
                "playbooks": {action: f"{action}.yml" for action in LIFECYCLE_ACTIONS},
            },
            "scenario": {"test_sequence": list(TEST_SEQUENCE)},
        }
        return yaml.safe_dump(config, sort_keys=False, explicit_start=True)

    @staticmethod
    def _create_playbook() -> str:
        return """---
- name: Create disposable Podman targets
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Start inventory containers
      containers.podman.podman_container:
        name: "{{ item_target }}"
        hostname: "{{ item_target }}"
        image: "{{ hostvars[item_target]['container_image'] }}"
        command: "{{ hostvars[item_target]['container_command'] }}"
        systemd: "{{ hostvars[item_target]['container_systemd'] }}"
        privileged: "{{ hostvars[item_target]['container_privileged'] }}"
        state: started
      loop: "{{ groups['molecule'] }}"
      loop_control:
        loop_var: item_target

    - name: Inspect running containers
      containers.podman.podman_container_info:
        name: "{{ item_target }}"
      register: container_info
      until:
        - container_info['containers'] | length > 0
        - container_info['containers'][0]['State']['Running']
      retries: 10
      delay: 2
      loop: "{{ groups['molecule'] }}"
      loop_control:
        loop_var: item_target
"""

    @staticmethod
    def _destroy_playbook() -> str:
        return """---
- name: Destroy disposable Podman targets
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Remove inventory containers even after a failed converge
      containers.podman.podman_container:
        name: "{{ item_target }}"
        state: absent
        force_delete: true
      loop: "{{ groups['molecule'] }}"
      loop_control:
        loop_var: item_target
"""

    @staticmethod
    def _prepare_playbook() -> str:
        return """---
- name: Prepare Linux test targets
  hosts: molecule
  gather_facts: false
  tasks:
    - name: Ensure Python is available for Ansible modules
      ansible.builtin.raw: >-
        /bin/sh -c 'if command -v python3 >/dev/null 2>&1; then exit 0;
        elif command -v dnf >/dev/null 2>&1; then dnf install -y python3;
        elif command -v apt-get >/dev/null 2>&1; then apt-get update && apt-get install -y python3;
        else echo "No supported package manager found to install Python 3" >&2; exit 1; fi
        && echo X2A_PYTHON_INSTALLED'
      register: python_bootstrap
      changed_when: "'X2A_PYTHON_INSTALLED' in python_bootstrap['stdout']"

    - name: Wait for the Ansible connection after bootstrapping Python
      ansible.builtin.wait_for_connection:
        timeout: 30
"""

    def _converge_playbook(self) -> str:
        return f"""---
- name: Converge through the project deployment entry point
  ansible.builtin.import_playbook: ../../{self.layout.run_playbook_path.name}
"""

    @staticmethod
    def _instructions() -> str:
        return """# Running generated Molecule scenarios

Install Podman on the controller and Ansible/Molecule in the same Python environment.
No Molecule driver plugins are required. For a uv-managed environment:

```bash
uv pip install --python "$(command -v python)" ansible-core 'molecule>=25.9.0'
ANSIBLE_COLLECTIONS_PATH="$PWD/collections" \\
  ansible-galaxy collection install -r molecule/requirements.yml
molecule test --scenario-name <module>
# Explicit cleanup after an interrupted run:
molecule destroy --scenario-name <module>
```

Run from the Ansible project root. The Ansible-native scenario uses standard
`inventory/hosts.yml` and the `containers.podman.podman` connection. Local lifecycle
playbooks create containers with `containers.podman.podman_container`, inspect
readiness with `containers.podman.podman_container_info`, and remove them on destroy.
There is no driver-managed inventory or external Molecule driver plugin.

Scenarios create privileged, disposable Linux containers; use a dedicated test
controller and never point them at production inventory. Names are scoped to the
project checkout and role. Do not run the same scenario concurrently in one checkout;
use separate generated projects. Destroy containers before moving/deleting a project.
Set `X2A_MOLECULE_IMAGE` to another Linux image with systemd at `/sbin/init` and a
supported `dnf` or `apt-get` package manager. Systemd mode is enabled. Python is
bootstrapped before connection checks and the actual project deployment playbook.
The test sequence destroys stale containers first and removes them after verification.

The converter generates and statically validates scenarios but does not execute
them; developer/CI results are the runtime acceptance signal. Windows hosts require
a separate future profile.

Reference: https://docs.ansible.com/projects/molecule/examples/podman/
"""
