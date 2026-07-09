"""Evaluation tests for Puppet ManifestAnalysisService.

These tests send Puppet manifest strings through the LLM via
ManifestAnalysisService and verify that the ManifestExecutionAnalysis
output correctly extracts iterations, conditionals, and class names.
"""

import pytest

from src.inputs.puppet.models import ManifestExecutionAnalysis
from src.inputs.puppet.services import ManifestAnalysisService
from src.types.file_analysis_state import FileAnalysisState

pytestmark = [pytest.mark.eval]


class TestManifestAnalysisEval:
    @pytest.fixture(scope="class")
    def manifest_service(self):
        from src.model import get_model

        return ManifestAnalysisService(model=get_model())

    def _analyze(self, service, tmp_path, content, filename="init.pp"):
        pp_file = tmp_path / filename
        pp_file.write_text(content)
        state = FileAnalysisState(user_message="", path=str(pp_file))
        result_state = service(state)
        return result_state.result

    def test_each_loop_extraction(self, manifest_service, tmp_path):
        manifest = """\
class profile_webapp::config (
  Hash $backends = {},
) {
  $backends.each |String $name, Hash $config| {
    file { "/etc/webapp/conf.d/${name}.conf":
      ensure  => file,
      content => template('profile_webapp/backend.conf.erb'),
      mode    => '0644',
    }
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest, "config.pp")

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_webapp::config"

        iteration_items = [
            item for item in result.execution_order if item.type == "iteration"
        ]
        assert len(iteration_items) >= 1, (
            f"Expected at least 1 iteration item, got {len(iteration_items)}. "
            f"Types found: {[i.type for i in result.execution_order]}"
        )

        iter_item = iteration_items[0]
        assert iter_item.iterator_type == "each"
        assert "$backends" in (iter_item.collection_variable or "")
        assert len(iter_item.execution_order) >= 1, (
            "Iteration body should contain at least 1 nested resource"
        )

        nested_resources = [
            n for n in iter_item.execution_order if n.type == "resource"
        ]
        assert len(nested_resources) >= 1
        assert nested_resources[0].resource_type == "file"

    def test_all_resources_after_conditional(self, manifest_service, tmp_path):
        manifest = """\
class profile_webapp (
  Boolean $enable_ssl = false,
) {
  if $enable_ssl {
    package { 'openssl':
      ensure => installed,
    }
  }

  package { 'webapp':
    ensure => installed,
  }

  file { '/etc/webapp/app.conf':
    ensure => file,
    mode   => '0644',
  }

  service { 'webapp':
    ensure => running,
    enable => true,
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_webapp"

        assert len(result.execution_order) >= 4, (
            f"Expected at least 4 execution items (1 conditional + 3 resources), "
            f"got {len(result.execution_order)}: "
            f"{[(i.type, getattr(i, 'resource_type', None) or getattr(i, 'condition_type', None)) for i in result.execution_order]}"
        )

        types = [item.type for item in result.execution_order]
        assert "conditional" in types, "Should extract the if-block as a conditional"

        resource_items = [
            item for item in result.execution_order if item.type == "resource"
        ]
        resource_names = [
            f"{item.resource_type}[{item.title}]" for item in resource_items
        ]
        assert any("webapp" in name and "package" in name for name in resource_names), (
            f"Missing package[webapp], found: {resource_names}"
        )
        assert any("app.conf" in name for name in resource_names), (
            f"Missing file[/etc/webapp/app.conf], found: {resource_names}"
        )
        assert any("service" in name for name in resource_names), (
            f"Missing service[webapp], found: {resource_names}"
        )

    def test_class_name_extraction(self, manifest_service, tmp_path):
        manifest = """\
class profile_webapp::install {
  package { 'webapp-server':
    ensure => present,
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest, "install.pp")

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_webapp::install"
        assert len(result.execution_order) == 1
        assert result.execution_order[0].type == "resource"
        assert result.execution_order[0].resource_type == "package"
        assert result.execution_order[0].title == "webapp-server"
