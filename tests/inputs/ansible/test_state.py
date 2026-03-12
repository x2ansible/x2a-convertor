"""Tests for Ansible analysis state management."""

from src.inputs.ansible.models import AnsibleStructuredAnalysis
from src.inputs.ansible.state import AnsibleAnalysisState


class TestAnsibleAnalysisState:
    """Test AnsibleAnalysisState dataclass."""

    def _make_state(self, **overrides):
        defaults = {
            "user_message": "Modernize this role",
            "path": "/tmp/legacy-role",
            "specification": "",
        }
        defaults.update(overrides)
        return AnsibleAnalysisState(**defaults)

    def test_defaults(self):
        state = self._make_state()
        assert state.user_message == "Modernize this role"
        assert state.path == "/tmp/legacy-role"
        assert state.specification == ""
        assert state.collection_dependencies == []
        assert state.structured_analysis is None
        assert state.execution_summary == ""
        assert state.failed is False

    def test_update_returns_new_instance(self):
        state = self._make_state()
        new_state = state.update(specification="# Migration Plan")
        assert new_state is not state
        assert new_state.specification == "# Migration Plan"
        assert state.specification == ""

    def test_update_preserves_other_fields(self):
        state = self._make_state(
            collection_dependencies=["community.general"],
        )
        new_state = state.update(specification="updated")
        assert new_state.collection_dependencies == ["community.general"]
        assert new_state.path == "/tmp/legacy-role"

    def test_mark_failed(self):
        state = self._make_state()
        failed = state.mark_failed("No tasks/ directory found")
        assert failed.failed is True
        assert failed.failure_reason == "No tasks/ directory found"
        assert state.failed is False

    def test_update_structured_analysis(self):
        state = self._make_state()
        analysis = AnsibleStructuredAnalysis()
        new_state = state.update(structured_analysis=analysis)
        assert new_state.structured_analysis is analysis
        assert state.structured_analysis is None

    def test_update_collection_dependencies(self):
        state = self._make_state()
        new_state = state.update(
            collection_dependencies=["community.general", "ansible.utils"]
        )
        assert len(new_state.collection_dependencies) == 2
        assert "community.general" in new_state.collection_dependencies
