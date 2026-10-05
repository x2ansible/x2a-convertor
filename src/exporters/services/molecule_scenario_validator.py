"""Static YAML and contract validation for generated Molecule scenarios."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.molecule_contract import (
    COLLECTIONS_PATH_TEMPLATE,
    INVENTORY_ARGUMENT,
    LIFECYCLE_ACTIONS,
    PODMAN_COLLECTION,
    REQUIREMENTS_FILE,
    SYSTEMD_COMMAND,
    SYSTEMD_MODE,
    TEST_SEQUENCE,
)


class MoleculeScenarioValidator:
    """Validate file structure without claiming runtime or behavioral correctness."""

    def __init__(self, layout: AnsibleProjectLayout) -> None:
        self.layout = layout

    def validate(
        self, paths: Iterable[Path], *, include_verification: bool = True
    ) -> list[str]:
        documents, errors = self._load_yaml_documents(paths)
        if errors:
            return errors
        return [
            *self._validate_deployment_playbook(documents),
            *self._validate_scenario_configuration(documents),
            *self._validate_inventory(documents),
            *self._validate_lifecycle_playbooks(documents),
            *(self._validate_verification(documents) if include_verification else []),
        ]

    @staticmethod
    def _load_yaml_documents(
        paths: Iterable[Path],
    ) -> tuple[dict[Path, Any], list[str]]:
        documents: dict[Path, Any] = {}
        errors: list[str] = []
        for path in paths:
            if path.suffix not in {".yml", ".yaml"}:
                continue
            try:
                with path.open(encoding="utf-8") as stream:
                    documents[path] = yaml.safe_load(stream)
            except (OSError, UnicodeError, yaml.YAMLError) as error:
                errors.append(f"Invalid YAML in {path}: {error}")
        return documents, errors

    def _validate_deployment_playbook(self, documents: dict[Path, Any]) -> list[str]:
        path = self.layout.run_playbook_path
        plays = self._mapping_list(documents.get(path))
        role_names = [
            self._mapping(task.get("ansible.builtin.include_role")).get("name")
            for play in plays
            for task in self._mapping_list(play.get("tasks"))
        ]
        if self.layout.fqcn not in role_names:
            return [f"Deployment playbook does not include {self.layout.fqcn}: {path}"]
        converge = self._mapping_list(
            documents.get(self.layout.molecule_scenario_path / "converge.yml")
        )
        expected = f"../../{self.layout.run_playbook_path.name}"
        if not any(
            play.get("ansible.builtin.import_playbook") == expected for play in converge
        ):
            return [
                "Molecule converge does not import this module's deployment playbook"
            ]
        return []

    def _validate_scenario_configuration(self, documents: dict[Path, Any]) -> list[str]:
        config = documents.get(self.layout.molecule_scenario_path / "molecule.yml")
        if not isinstance(config, dict):
            return ["Molecule configuration must contain one YAML mapping"]
        if "driver" in config and config["driver"] != {"name": "default"}:
            return ["Molecule must use Ansible-native playbooks, not a driver plugin"]
        if any(
            section in config for section in ("platforms", "provisioner", "verifier")
        ):
            return [
                "Molecule must not define legacy platforms, provisioner, or verifier"
            ]
        return [
            *self._validate_ansible_configuration(self._mapping(config.get("ansible"))),
            *self._validate_dependencies(config, documents),
            *self._validate_test_sequence(self._mapping(config.get("scenario"))),
        ]

    @staticmethod
    def _validate_test_sequence(scenario: dict[str, Any]) -> list[str]:
        sequence = scenario.get("test_sequence")
        if sequence != list(TEST_SEQUENCE):
            return [
                "Molecule test sequence must run dependency, destroy, create, prepare, "
                "converge, idempotence, verify, destroy in order"
            ]
        return []

    @classmethod
    def _validate_ansible_configuration(cls, ansible: dict[str, Any]) -> list[str]:
        executor = cls._mapping(ansible.get("executor"))
        playbooks = cls._mapping(ansible.get("playbooks"))
        if executor.get("backend") != "ansible-playbook" or not playbooks:
            return [
                "Molecule configuration must define the Ansible executor and playbooks"
            ]
        if any(
            playbooks.get(action) != f"{action}.yml" for action in LIFECYCLE_ACTIONS
        ):
            return ["Molecule configuration must map all lifecycle playbooks"]
        arguments = cls._mapping(executor.get("args")).get("ansible_playbook")
        if arguments != [INVENTORY_ARGUMENT]:
            return ["Molecule executor must use only the scenario inventory"]
        if (
            cls._mapping(ansible.get("env")).get("ANSIBLE_COLLECTIONS_PATH")
            != COLLECTIONS_PATH_TEMPLATE
        ):
            return ["Molecule executor must use the project collections path"]
        return []

    def _validate_dependencies(
        self, config: dict[str, Any], documents: dict[Path, Any]
    ) -> list[str]:
        dependency = self._mapping(config.get("dependency"))
        options = self._mapping(dependency.get("options"))
        if options.get("requirements-file") != REQUIREMENTS_FILE:
            return ["Molecule dependency must reference molecule/requirements.yml"]
        environment = self._mapping(dependency.get("env"))
        if environment.get("ANSIBLE_COLLECTIONS_PATH") != COLLECTIONS_PATH_TEMPLATE:
            return [
                "Molecule dependency must install into the project collections path"
            ]
        requirements = self._mapping(
            documents.get(self.layout.molecule_requirements_path)
        )
        collections = self._mapping_list(requirements.get("collections"))
        if not any(item.get("name") == PODMAN_COLLECTION for item in collections):
            return [f"Molecule test requirements must install {PODMAN_COLLECTION}"]
        return []

    def _validate_inventory(self, documents: dict[Path, Any]) -> list[str]:
        path = self.layout.molecule_scenario_path / "inventory" / "hosts.yml"
        inventory = self._mapping(documents.get(path))
        root = self._mapping(inventory.get("all"))
        children = self._mapping(root.get("children"))
        group = self._mapping(children.get("molecule"))
        hosts = self._mapping(group.get("hosts"))
        if (
            set(inventory) != {"all"}
            or set(root) != {"children"}
            or set(children) != {"molecule"}
            or set(group) != {"hosts"}
            or not hosts
        ):
            return ["Molecule inventory must contain only disposable molecule hosts"]
        if not all(self._valid_target(self._mapping(host)) for host in hosts.values()):
            return [
                "Molecule inventory must use Podman connections and configurable systemd targets"
            ]
        return []

    @staticmethod
    def _valid_target(target: dict[str, Any]) -> bool:
        return (
            target.get("ansible_connection") == f"{PODMAN_COLLECTION}.podman"
            and target.get("ansible_user") == "root"
            and target.get("ansible_python_interpreter") == "/usr/bin/python3"
            and target.get("container_command") == SYSTEMD_COMMAND
            and target.get("container_systemd") == SYSTEMD_MODE
            and target.get("container_privileged") is True
            and "X2A_MOLECULE_IMAGE" in str(target.get("container_image", ""))
        )

    def _validate_lifecycle_playbooks(self, documents: dict[Path, Any]) -> list[str]:
        errors = []
        for action, state in (("create", "started"), ("destroy", "absent")):
            path = self.layout.molecule_scenario_path / f"{action}.yml"
            plays = self._mapping_list(documents.get(path))
            if len(plays) != 1 or any(
                play.get("hosts") != "localhost"
                or play.get("connection") != "local"
                or play.get("gather_facts") is not False
                for play in plays
            ):
                errors.append(
                    f"{action}.yml must manage containers locally without facts"
                )
                continue
            tasks = self._mapping_list(plays[0].get("tasks"))
            container_tasks = self._container_tasks(tasks, "podman_container")
            if not any(task.get("state") == state for task in container_tasks):
                errors.append(f"{action}.yml must set inventory containers to {state}")
            if action == "create" and not self._container_tasks(
                tasks, "podman_container_info"
            ):
                errors.append(
                    "create.yml must inspect inventory containers with podman_container_info"
                )
        return errors

    @classmethod
    def _container_tasks(
        cls, tasks: list[dict[str, Any]], module: str
    ) -> list[dict[str, Any]]:
        return [
            arguments
            for task in tasks
            if (arguments := cls._mapping(task.get(f"{PODMAN_COLLECTION}.{module}")))
            and arguments.get("name") == "{{ item_target }}"
            and task.get("loop") == "{{ groups['molecule'] }}"
            and cls._mapping(task.get("loop_control")).get("loop_var") == "item_target"
        ]

    def _validate_verification(self, documents: dict[Path, Any]) -> list[str]:
        plays = self._mapping_list(documents.get(self.layout.molecule_verify_path))
        if not plays or any(play.get("hosts") != "all" for play in plays):
            return ["verify.yml must target all inventory-defined Molecule instances"]
        return [
            error for play in plays for error in self._validate_verification_play(play)
        ]

    @classmethod
    def _validate_verification_play(cls, play: dict[str, Any]) -> list[str]:
        tasks = play.get("tasks")
        if tasks == []:
            return []
        task_mappings = cls._mapping_list(tasks)
        if not task_mappings:
            return [
                "verify.yml tasks must be a list of task mappings (or an explicit empty list)"
            ]
        assertions = [
            cls._mapping(task["ansible.builtin.assert"])
            for task in task_mappings
            if "ansible.builtin.assert" in task
        ]
        if not assertions:
            return ["verify.yml must contain at least one behavior assertion"]
        if not all(
            cls._has_concrete_condition(item.get("that")) for item in assertions
        ):
            return ["verify.yml assertions must check concrete expected behavior"]
        return []

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _mapping_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            return []
        return value

    @classmethod
    def _has_concrete_condition(cls, conditions: Any) -> bool:
        if isinstance(conditions, list):
            return bool(conditions) and all(
                cls._has_concrete_condition(item) for item in conditions
            )
        if isinstance(conditions, str):
            return conditions.strip().lower() not in {"", "true", "false"}
        return False
