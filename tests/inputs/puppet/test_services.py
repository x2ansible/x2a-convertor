"""Tests for Puppet analysis services — retry logic, message format, fallbacks."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.inputs.puppet.models import (
    ClassInclude,
    CredentialAnalysis,
    HieraDataAnalysis,
    ManifestExecutionAnalysis,
    PuppetTemplateAnalysis,
)
from src.inputs.puppet.services import (
    MAX_STRUCTURED_RETRIES,
    CredentialDetectionService,
    CustomTypeAnalysisService,
    HieraDataAnalysisService,
    ManifestAnalysisService,
    TemplateAnalysisService,
)


@pytest.fixture
def mock_model():
    model = MagicMock()
    structured = MagicMock()
    model.with_structured_output.return_value = structured
    return model, structured


@pytest.fixture
def manifest_file(tmp_path):
    f = tmp_path / "init.pp"
    f.write_text("class profile_haproxy { }")
    return f


@pytest.fixture
def hiera_file(tmp_path):
    f = tmp_path / "common.yaml"
    f.write_text("profile_haproxy::package_name: haproxy")
    return f


@pytest.fixture
def template_file(tmp_path):
    f = tmp_path / "haproxy.cfg.erb"
    f.write_text("<%= @haproxy_user %>")
    return f


@pytest.fixture
def custom_type_file(tmp_path):
    f = tmp_path / "haproxy_version.rb"
    f.write_text("Facter.add(:haproxy_version) { }")
    return f


class TestManifestAnalysisService:
    def test_file_not_found_returns_empty(self, mock_model):
        model, _ = mock_model
        svc = ManifestAnalysisService(model)
        result = svc.analyze(Path("/nonexistent/init.pp"))
        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.resources == []
        model.with_structured_output.assert_not_called()

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_successful_analysis(
        self, mock_prompt, mock_config, mock_model, manifest_file
    ):
        model, structured = mock_model
        expected = ManifestExecutionAnalysis(
            resources=[],
            class_includes=[
                ClassInclude(class_name="install", relationship="include"),
                ClassInclude(class_name="config", relationship="include"),
            ],
        )
        structured.invoke.return_value = expected
        mock_prompt.return_value.format.return_value = "prompt text"

        svc = ManifestAnalysisService(model)
        result = svc.analyze(manifest_file)
        assert result == expected
        structured.invoke.assert_called_once()

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_uses_system_and_human_messages(
        self, mock_prompt, mock_config, mock_model, manifest_file
    ):
        model, structured = mock_model
        structured.invoke.return_value = ManifestExecutionAnalysis()
        mock_prompt.return_value.format.return_value = "prompt"

        svc = ManifestAnalysisService(model)
        svc.analyze(manifest_file)

        messages = structured.invoke.call_args[0][0]
        assert len(messages) == 2
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], HumanMessage)

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_retry_on_none(self, mock_prompt, mock_config, mock_model, manifest_file):
        model, structured = mock_model
        expected = ManifestExecutionAnalysis(
            class_includes=[ClassInclude(class_name="install", relationship="include")]
        )
        structured.invoke.side_effect = [None, expected]
        mock_prompt.return_value.format.return_value = "prompt"

        svc = ManifestAnalysisService(model)
        result = svc.analyze(manifest_file)
        assert result == expected
        assert structured.invoke.call_count == 2

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_all_retries_exhausted_returns_empty(
        self, mock_prompt, mock_config, mock_model, manifest_file
    ):
        model, structured = mock_model
        structured.invoke.return_value = None
        mock_prompt.return_value.format.return_value = "prompt"

        svc = ManifestAnalysisService(model)
        result = svc.analyze(manifest_file)
        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.resources == []
        assert structured.invoke.call_count == MAX_STRUCTURED_RETRIES

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_exception_returns_empty(
        self, mock_prompt, mock_config, mock_model, manifest_file
    ):
        model, structured = mock_model
        structured.invoke.side_effect = RuntimeError("LLM error")
        mock_prompt.return_value.format.return_value = "prompt"

        svc = ManifestAnalysisService(model)
        result = svc.analyze(manifest_file)
        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.resources == []


class TestHieraDataAnalysisService:
    def test_file_not_found_returns_empty(self, mock_model):
        model, _ = mock_model
        svc = HieraDataAnalysisService(model)
        result = svc.analyze(Path("/nonexistent/common.yaml"))
        assert isinstance(result, HieraDataAnalysis)
        assert result.variables == []

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_retry_on_none_then_succeeds(
        self, mock_prompt, mock_config, mock_model, hiera_file
    ):
        model, structured = mock_model
        expected = HieraDataAnalysis(variables=[])
        structured.invoke.side_effect = [None, None, expected]
        mock_prompt.return_value.format.return_value = "prompt"

        svc = HieraDataAnalysisService(model)
        result = svc.analyze(hiera_file, hierarchy_level="Common")
        assert result == expected
        assert structured.invoke.call_count == 3

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_uses_split_messages(
        self, mock_prompt, mock_config, mock_model, hiera_file
    ):
        model, structured = mock_model
        structured.invoke.return_value = HieraDataAnalysis()
        mock_prompt.return_value.format.return_value = "prompt"

        svc = HieraDataAnalysisService(model)
        svc.analyze(hiera_file, hierarchy_level="Common", full_hierarchy="common.yaml")

        messages = structured.invoke.call_args[0][0]
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], HumanMessage)


class TestTemplateAnalysisService:
    def test_file_not_found_returns_empty(self, mock_model):
        model, _ = mock_model
        svc = TemplateAnalysisService(model)
        result = svc.analyze(Path("/nonexistent/template.erb"))
        assert isinstance(result, PuppetTemplateAnalysis)
        assert result.template_type == "unknown"

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_erb_template_type(
        self, mock_prompt, mock_config, mock_model, template_file
    ):
        model, structured = mock_model
        structured.invoke.return_value = PuppetTemplateAnalysis(template_type="erb")
        mock_prompt.return_value.format.return_value = "prompt"

        svc = TemplateAnalysisService(model)
        result = svc.analyze(template_file)
        assert result.template_type == "erb"

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_epp_template_type(self, mock_prompt, mock_config, mock_model, tmp_path):
        model, structured = mock_model
        epp_file = tmp_path / "backend.conf.epp"
        epp_file.write_text("<%= $port %>")
        structured.invoke.return_value = PuppetTemplateAnalysis(template_type="epp")
        mock_prompt.return_value.format.return_value = "prompt"

        svc = TemplateAnalysisService(model)
        result = svc.analyze(epp_file)
        assert result.template_type == "epp"

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_retry_exhausted_returns_correct_template_type(
        self, mock_prompt, mock_config, mock_model, template_file
    ):
        model, structured = mock_model
        structured.invoke.return_value = None
        mock_prompt.return_value.format.return_value = "prompt"

        svc = TemplateAnalysisService(model)
        result = svc.analyze(template_file)
        assert result.template_type == "erb"
        assert structured.invoke.call_count == MAX_STRUCTURED_RETRIES


class TestCustomTypeAnalysisService:
    def test_file_not_found_returns_unknown(self, mock_model):
        model, _ = mock_model
        svc = CustomTypeAnalysisService(model)
        result = svc.analyze(Path("/nonexistent/custom.rb"))
        assert result.component_type == "unknown"
        assert result.name == "unknown"

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_retry_exhausted_uses_file_stem(
        self, mock_prompt, mock_config, mock_model, custom_type_file
    ):
        model, structured = mock_model
        structured.invoke.return_value = None
        mock_prompt.return_value.format.return_value = "prompt"

        svc = CustomTypeAnalysisService(model)
        result = svc.analyze(custom_type_file)
        assert result.component_type == "unknown"
        assert result.name == "haproxy_version"


class TestCredentialDetectionService:
    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_successful_detection(self, mock_prompt, mock_config, mock_model):
        model, structured = mock_model
        expected = CredentialAnalysis(total_detected=2)
        structured.invoke.return_value = expected
        mock_prompt.return_value.format.return_value = "prompt"

        svc = CredentialDetectionService(model)
        result = svc.analyze("vars", "params")
        assert result.total_detected == 2

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_retry_on_none(self, mock_prompt, mock_config, mock_model):
        model, structured = mock_model
        expected = CredentialAnalysis(total_detected=1)
        structured.invoke.side_effect = [None, expected]
        mock_prompt.return_value.format.return_value = "prompt"

        svc = CredentialDetectionService(model)
        result = svc.analyze("vars", "params")
        assert result.total_detected == 1
        assert structured.invoke.call_count == 2

    @patch("src.inputs.puppet.services.get_runnable_config", return_value={})
    @patch("src.inputs.puppet.services.get_prompt")
    def test_all_retries_exhausted(self, mock_prompt, mock_config, mock_model):
        model, structured = mock_model
        structured.invoke.return_value = None
        mock_prompt.return_value.format.return_value = "prompt"

        svc = CredentialDetectionService(model)
        result = svc.analyze("vars", "params")
        assert isinstance(result, CredentialAnalysis)
        assert result.total_detected == 0
        assert structured.invoke.call_count == MAX_STRUCTURED_RETRIES
