"""Tests for Ansible analysis services."""

from pathlib import Path

from src.inputs.ansible.services import (
    MetaAnalysisService,
    TaskFileAnalysisService,
    TemplateAnalysisService,
    VariablesAnalysisService,
)
from src.types.file_analysis_state import FileAnalysisState


def _make_file_state(path: str) -> FileAnalysisState:
    return FileAnalysisState(path=path, user_message="")


class TestTaskFileAnalysisService:
    """Test TaskFileAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = TaskFileAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.yml"))
        result = service(state).result
        assert result.tasks == []

    def test_returns_empty_for_missing_file_path(self):
        """Should return empty analysis for non-existent path."""
        service = TaskFileAnalysisService(model=None)
        state = _make_file_state(str(Path("/nonexistent/tasks/main.yml")))
        result = service(state).result
        assert result.tasks == []


class TestVariablesAnalysisService:
    """Test VariablesAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = VariablesAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.yml"))
        result = service(state).result
        assert result.variables == {}
        assert result.notes == []


class TestMetaAnalysisService:
    """Test MetaAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = MetaAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.yml"))
        result = service(state).result
        assert result.role_name == ""
        assert result.dependencies == []


class TestTemplateAnalysisService:
    """Test TemplateAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = TemplateAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.j2"))
        result = service(state).result
        assert result.variables_used == []
        assert result.bare_variables == []
        assert result.deprecated_tests == []
