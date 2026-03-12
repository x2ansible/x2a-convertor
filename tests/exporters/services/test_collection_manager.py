"""Tests for collection manager's ansible.builtin filtering."""

import yaml

from src.exporters.services.collection_manager import (
    CollectionManager,
    CollectionSpec,
    InstallResultSummary,
)


class TestCollectionSpec:
    """Test CollectionSpec value object."""

    def test_from_dict_requirement(self):
        spec = CollectionSpec.from_requirement(
            {"name": "community.general", "version": "5.0.0"}
        )
        assert spec is not None
        assert spec.fqcn == "community.general"
        assert spec.version == "5.0.0"

    def test_from_string_requirement(self):
        spec = CollectionSpec.from_requirement("ansible.utils")
        assert spec is not None
        assert spec.fqcn == "ansible.utils"
        assert spec.version is None

    def test_invalid_requirement_no_dot(self):
        spec = CollectionSpec.from_requirement("nocolon")
        assert spec is None

    def test_spec_string_with_version(self):
        spec = CollectionSpec(namespace="community", name="general", version="5.0.0")
        assert spec.spec_string == "community.general:5.0.0"

    def test_spec_string_without_version(self):
        spec = CollectionSpec(namespace="community", name="general")
        assert spec.spec_string == "community.general"


class TestParseRequirements:
    """Test requirements.yml parsing with ansible.builtin filtering."""

    def _make_manager(self):
        return CollectionManager()

    def test_filters_ansible_builtin(self, tmp_path):
        """ansible.builtin should be filtered from parsed requirements."""
        requirements = {
            "collections": [
                {"name": "ansible.builtin", "version": "2.13.0"},
                {"name": "community.general", "version": "5.0.0"},
            ]
        }
        req_file = tmp_path / "requirements.yml"
        req_file.write_text(yaml.dump(requirements))

        manager = self._make_manager()
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        collections = manager._parse_requirements(req_file, slog)

        fqcns = [c.fqcn for c in collections]
        assert "ansible.builtin" not in fqcns
        assert "community.general" in fqcns
        assert len(collections) == 1

    def test_empty_requirements(self, tmp_path):
        """Empty requirements.yml should return empty list."""
        req_file = tmp_path / "requirements.yml"
        req_file.write_text("---\n")

        manager = self._make_manager()
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        collections = manager._parse_requirements(req_file, slog)
        assert collections == []

    def test_no_collections_key(self, tmp_path):
        """requirements.yml without collections key should return empty list."""
        req_file = tmp_path / "requirements.yml"
        req_file.write_text("roles:\n  - name: some_role\n")

        manager = self._make_manager()
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        collections = manager._parse_requirements(req_file, slog)
        assert collections == []

    def test_missing_file(self, tmp_path):
        """Missing requirements file should return empty results."""
        manager = self._make_manager()
        results = manager.install_from_requirements(tmp_path / "nonexistent.yml")
        assert results == []


class TestInstallResultSummary:
    """Test InstallResultSummary value object."""

    def test_all_succeeded(self):
        from src.exporters.services.collection_manager import InstallResult

        results = [
            InstallResult.public_galaxy_success(
                CollectionSpec(namespace="community", name="general")
            ),
        ]
        summary = InstallResultSummary.from_results(results)
        assert summary.all_succeeded is True
        assert summary.success_count == 1
        assert summary.fail_count == 0

    def test_with_failures(self):
        from src.exporters.services.collection_manager import InstallResult

        results = [
            InstallResult.public_galaxy_success(
                CollectionSpec(namespace="community", name="general")
            ),
            InstallResult.failed(
                CollectionSpec(namespace="custom", name="missing"),
                "not_found",
            ),
        ]
        summary = InstallResultSummary.from_results(results)
        assert summary.all_succeeded is False
        assert summary.success_count == 1
        assert summary.fail_count == 1
        assert len(summary.failures) == 1
