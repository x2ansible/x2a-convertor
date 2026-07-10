"""Tests for Puppet analysis services."""

from pathlib import Path

from src.inputs.puppet.models import (
    CredentialAnalysis,
    CustomTypeAnalysis,
    HieraDataAnalysis,
    PuppetTemplateAnalysis,
)
from src.inputs.puppet.services import (
    CredentialDetectionService,
    CustomTypeAnalysisService,
    HieraDataAnalysisService,
    ManifestAnalysisService,
    TemplateAnalysisService,
)
from src.types.file_analysis_state import FileAnalysisState


def _make_file_state(path: str, **kwargs) -> FileAnalysisState:
    return FileAnalysisState(user_message="", path=path, **kwargs)


class TestManifestAnalysisService:
    """Test ManifestAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should raise FileNotFoundError when file doesn't exist."""
        import pytest

        service = ManifestAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.pp"))
        with pytest.raises(FileNotFoundError, match="Manifest file not found"):
            service(state)

    def test_returns_empty_for_nonexistent_path(self):
        """Should raise FileNotFoundError for non-existent path."""
        import pytest

        service = ManifestAnalysisService(model=None)
        state = _make_file_state(str(Path("/nonexistent/init.pp")))
        with pytest.raises(FileNotFoundError, match="Manifest file not found"):
            service(state)


class TestHieraDataAnalysisService:
    """Test HieraDataAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = HieraDataAnalysisService(model=None)
        state = _make_file_state(
            str(tmp_path / "nonexistent.yaml"),
            metadata={"hierarchy_level": "common", "full_hierarchy": ""},
        )
        result = service(state).result
        assert isinstance(result, HieraDataAnalysis)
        assert result.variables == []

    def test_returns_empty_for_nonexistent_path(self):
        """Should return empty analysis for non-existent path."""
        service = HieraDataAnalysisService(model=None)
        state = _make_file_state(
            str(Path("/nonexistent/common.yaml")),
            metadata={"hierarchy_level": "common", "full_hierarchy": ""},
        )
        result = service(state).result
        assert isinstance(result, HieraDataAnalysis)
        assert result.variables == []


class TestTemplateAnalysisService:
    """Test TemplateAnalysisService."""

    def test_returns_empty_for_missing_file(self, tmp_path):
        """Should return empty analysis when file doesn't exist."""
        service = TemplateAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.erb"))
        result = service(state).result
        assert isinstance(result, PuppetTemplateAnalysis)
        assert result.template_type == "unknown"

    def test_returns_empty_for_nonexistent_path(self):
        """Should return empty analysis for non-existent path."""
        service = TemplateAnalysisService(model=None)
        state = _make_file_state(str(Path("/nonexistent/template.erb")))
        result = service(state).result
        assert isinstance(result, PuppetTemplateAnalysis)
        assert result.template_type == "unknown"


class TestCustomTypeAnalysisService:
    """Test CustomTypeAnalysisService."""

    def test_returns_unknown_for_missing_file(self, tmp_path):
        """Should return unknown analysis when file doesn't exist."""
        service = CustomTypeAnalysisService(model=None)
        state = _make_file_state(str(tmp_path / "nonexistent.rb"))
        result = service(state).result
        assert isinstance(result, CustomTypeAnalysis)
        assert result.component_type == "unknown"
        assert result.name == "unknown"

    def test_returns_unknown_for_nonexistent_path(self):
        """Should return unknown analysis for non-existent path."""
        service = CustomTypeAnalysisService(model=None)
        state = _make_file_state(str(Path("/nonexistent/custom.rb")))
        result = service(state).result
        assert isinstance(result, CustomTypeAnalysis)
        assert result.component_type == "unknown"
        assert result.name == "unknown"


class TestCredentialDetectionService:
    """Test CredentialDetectionService."""

    def test_returns_empty_for_no_credentials(self):
        """Should return empty analysis when no credentials detected."""
        service = CredentialDetectionService(model=None)
        state = _make_file_state(
            "",
            metadata={
                "hiera_variables": "None",
                "manifest_params": "None",
            },
        )
        result = service(state).result
        assert isinstance(result, CredentialAnalysis)
        assert result.total_detected == 0
        assert result.credentials == []
