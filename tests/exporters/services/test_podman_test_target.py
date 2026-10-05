"""Value-object contracts for isolated Podman inventory."""

from dataclasses import FrozenInstanceError, replace

import pytest
from jinja2 import Environment

from src.exporters.services.ansible_project_layout import AnsibleProjectLayout
from src.exporters.services.podman_test_target import PodmanTestTarget
from src.types import AnsibleModule


class TestPodmanTestTarget:
    @pytest.fixture
    def layout(self, tmp_path):
        return AnsibleProjectLayout.from_module(
            AnsibleModule("web_server"), project_path=tmp_path / "ansible"
        )

    def test_identity_is_stable_and_immutable(self, layout):
        target = PodmanTestTarget.from_layout(layout)

        assert target == PodmanTestTarget.from_layout(layout)
        assert target.name.startswith("x2a_web_server_")
        with pytest.raises(FrozenInstanceError):
            setattr(target, "name", "replacement")  # noqa: B010 - test runtime immutability

    @pytest.mark.parametrize(
        "change",
        [
            {"namespace": "acme"},
            {"project_name": "other"},
            {"module": AnsibleModule("database")},
        ],
    )
    def test_collection_and_role_identities_are_isolated(self, layout, change):
        assert (
            PodmanTestTarget.from_layout(layout).name
            != PodmanTestTarget.from_layout(replace(layout, **change)).name
        )

    def test_checkouts_are_isolated(self, layout):
        other = replace(layout, project_path=layout.project_path.parent / "other")

        assert (
            PodmanTestTarget.from_layout(layout).name
            != PodmanTestTarget.from_layout(other).name
        )

    def test_relative_and_absolute_paths_have_same_identity(self, layout, monkeypatch):
        monkeypatch.chdir(layout.project_path.parent)
        relative = replace(
            layout,
            project_path=layout.project_path.relative_to(layout.project_path.parent),
        )

        assert PodmanTestTarget.from_layout(layout) == PodmanTestTarget.from_layout(
            relative
        )

    @pytest.mark.parametrize("override", ["", "quay.io/example/systemd:latest"])
    def test_image_override_is_an_ansible_expression_not_molecule_interpolation(
        self, layout, override
    ):
        target = PodmanTestTarget.from_layout(layout)
        inventory = target.to_inventory()
        hosts = inventory["all"]["children"]["molecule"]["hosts"]
        variables = hosts[target.name]
        expression = Environment().from_string(variables["container_image"])

        assert expression.render(lookup=lambda *args: override) == (
            override or target.image
        )
        assert variables["ansible_connection"] == "containers.podman.podman"
        assert variables["ansible_python_interpreter"] == "/usr/bin/python3"
        assert variables["container_systemd"] == "always"
        assert variables["container_privileged"] is True
        assert list(hosts) == [target.name]

    def test_inventory_mutation_does_not_change_value(self, layout):
        target = PodmanTestTarget.from_layout(layout)
        inventory = target.to_inventory()
        inventory["all"].clear()

        assert target.to_inventory()["all"]["children"]
