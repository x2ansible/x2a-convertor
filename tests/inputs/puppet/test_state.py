"""Tests for Puppet analysis state management."""

from pathlib import Path

from src.inputs.puppet.state import PuppetState


class TestPuppetState:
    """Test PuppetState dataclass."""

    def _make_state(self, **overrides) -> PuppetState:
        return PuppetState(
            user_message=overrides.pop("user_message", "Migrate HAProxy module"),
            path=overrides.pop("path", "profile_haproxy"),
            specification=overrides.pop("specification", ""),
            **overrides,
        )

    def test_defaults(self):
        state = self._make_state()
        assert state.user_message == "Migrate HAProxy module"
        assert state.path == "profile_haproxy"
        assert state.specification == ""
        assert state.dependency_paths == []
        assert state.dependency_info == []
        assert state.dependencies_dir is None
        assert state.export_path is None
        assert state.structured_analysis is None
        assert state.execution_tree_summary == ""
        assert state.credentials_analysis is None
        assert state.failed is False
        assert state.failure_reason == ""

    def test_update_returns_new_instance(self):
        state = self._make_state()
        new_state = state.update(specification="# Migration Plan")
        assert new_state is not state
        assert new_state.specification == "# Migration Plan"
        assert state.specification == ""

    def test_update_preserves_other_fields(self):
        state = self._make_state(
            dependency_paths=["puppetlabs-stdlib"],
            dependency_info=[{"name": "puppetlabs-stdlib", "source": "forge"}],
        )
        new_state = state.update(specification="updated")
        assert new_state.dependency_paths == ["puppetlabs-stdlib"]
        assert new_state.dependency_info[0]["name"] == "puppetlabs-stdlib"
        assert new_state.path == "profile_haproxy"

    def test_mark_failed(self):
        state = self._make_state()
        failed = state.mark_failed("No manifests/ directory found")
        assert failed.failed is True
        assert failed.failure_reason == "No manifests/ directory found"
        assert state.failed is False

    def test_all_paths_without_deps(self):
        state = self._make_state()
        paths = state.all_paths
        assert len(paths) == 1
        assert paths[0] == Path("profile_haproxy")

    def test_all_paths_with_deps(self):
        state = self._make_state(
            dependency_paths=["stdlib", "concat"],
        )
        paths = state.all_paths
        assert len(paths) == 3
        assert Path("profile_haproxy") in paths
        assert Path("stdlib") in paths
        assert Path("concat") in paths

    def test_update_dependency_info(self):
        state = self._make_state()
        deps = [
            {"name": "stdlib", "source": "forge", "version": "9.0.0"},
            {
                "name": "custom",
                "source": "git",
                "url": "https://git.example.com/custom.git",
            },
        ]
        new_state = state.update(dependency_info=deps)
        assert len(new_state.dependency_info) == 2
        assert new_state.dependency_info[0]["source"] == "forge"
        assert new_state.dependency_info[1]["source"] == "git"
