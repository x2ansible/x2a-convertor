"""Tests for Ansible analysis services."""

from pathlib import Path

from src.inputs.ansible.services import (
    MetaAnalysisService,
    TaskFileAnalysisService,
    TemplateAnalysisService,
    VariablesAnalysisService,
)


class TestTaskFileAnalysisService:
    """Test TaskFileAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = TaskFileAnalysisService(model=None)
        result = service.analyze(tmp_path / "nonexistent.yml")
        assert result.tasks == []

    def test_returns_empty_for_missing_file_path(self):
        """Should return empty analysis for non-existent path."""
        service = TaskFileAnalysisService(model=None)
        result = service.analyze(Path("/nonexistent/tasks/main.yml"))
        assert result.tasks == []


class TestVariablesAnalysisService:
    """Test VariablesAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = VariablesAnalysisService(model=None)
        result = service.analyze(tmp_path / "nonexistent.yml")
        assert result.variables == {}
        assert result.notes == []


class TestMetaAnalysisService:
    """Test MetaAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = MetaAnalysisService(model=None)
        result = service.analyze(tmp_path / "nonexistent.yml")
        assert result.role_name == ""
        assert result.dependencies == []


class TestTemplateAnalysisService:
    """Test TemplateAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = TemplateAnalysisService(model=None)
        result = service.analyze(tmp_path / "nonexistent.j2")
        assert result.variables_used == []
        assert result.bare_variables == []
        assert result.deprecated_tests == []
