"""Evaluation tests for complex case/switch statements in Puppet manifests.

These tests verify that ManifestAnalysisService correctly extracts
execution order from manifests with complex case statements, including
nested cases, multiple branches, and resources after the case block.
"""

import pytest

from src.inputs.puppet.models import ManifestExecutionAnalysis
from src.inputs.puppet.services import ManifestAnalysisService
from src.types.file_analysis_state import FileAnalysisState

pytestmark = [pytest.mark.eval]


class TestManifestCaseStatementEval:
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

    def test_simple_case_statement(self, manifest_service, tmp_path):
        """Test basic case statement with OS family detection."""
        manifest = """\
class profile_packages (
  String $package_manager = 'auto',
) {
  case $facts['os']['family'] {
    'RedHat': {
      package { 'httpd':
        ensure => installed,
      }
    }
    'Debian': {
      package { 'apache2':
        ensure => installed,
      }
    }
    default: {
      fail('Unsupported OS family')
    }
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_packages"

        case_items = [
            item for item in result.execution_order if item.type == "conditional"
        ]
        assert len(case_items) >= 1, (
            f"Expected at least 1 case conditional, got {len(case_items)}. "
            f"Types found: {[i.type for i in result.execution_order]}"
        )

        case_item = case_items[0]
        assert case_item.condition_type == "case"
        assert "$facts['os']['family']" in (case_item.condition or "")

    def test_case_with_resources_after(self, manifest_service, tmp_path):
        """Test that resources AFTER a case block are extracted."""
        manifest = """\
class profile_webserver (
  Integer $port = 80,
) {
  case $::osfamily {
    'RedHat': {
      package { 'httpd':
        ensure => installed,
      }
      service { 'httpd':
        ensure => running,
      }
    }
    'Debian': {
      package { 'apache2':
        ensure => installed,
      }
      service { 'apache2':
        ensure => running,
      }
    }
    default: {
      fail('Unsupported OS')
    }
  }

  file { '/etc/webserver/custom.conf':
    ensure  => file,
    content => template('profile_webserver/custom.conf.erb'),
    mode    => '0644',
  }

  exec { 'reload-webserver':
    command => '/usr/bin/systemctl reload httpd',
    onlyif  => '/usr/bin/test -f /etc/webserver/custom.conf',
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_webserver"

        assert len(result.execution_order) >= 3, (
            f"Expected at least 3 execution items (1 case + 2 resources after), "
            f"got {len(result.execution_order)}: "
            f"{[(i.type, getattr(i, 'resource_type', None) or getattr(i, 'condition_type', None)) for i in result.execution_order]}"
        )

        resource_items = [
            item for item in result.execution_order if item.type == "resource"
        ]
        resource_names = [
            f"{item.resource_type}[{item.title}]" for item in resource_items
        ]

        assert any("custom.conf" in name for name in resource_names), (
            f"Missing file[/etc/webserver/custom.conf] after case block, found: {resource_names}"
        )
        assert any("reload-webserver" in name for name in resource_names), (
            f"Missing exec[reload-webserver] after case block, found: {resource_names}"
        )

    def test_nested_case_statements(self, manifest_service, tmp_path):
        """Test nested case statements within case branches."""
        manifest = """\
class profile_advanced (
  String $environment = 'production',
) {
  case $facts['os']['family'] {
    'RedHat': {
      case $environment {
        'production': {
          package { 'httpd':
            ensure => '2.4.6',
          }
        }
        'development': {
          package { 'httpd':
            ensure => 'latest',
          }
        }
        default: {
          package { 'httpd':
            ensure => 'present',
          }
        }
      }
    }
    'Debian': {
      package { 'apache2':
        ensure => installed,
      }
    }
  }

  service { 'webserver':
    ensure => running,
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_advanced"

        assert len(result.execution_order) >= 2, (
            f"Expected at least 2 execution items (outer case + service), "
            f"got {len(result.execution_order)}"
        )

        resource_items = [
            item for item in result.execution_order if item.type == "resource"
        ]
        resource_names = [
            f"{item.resource_type}[{item.title}]" for item in resource_items
        ]

        assert any("webserver" in name for name in resource_names), (
            f"Missing service[webserver] after nested case blocks, found: {resource_names}"
        )

    def test_case_with_multiple_resources_per_branch(self, manifest_service, tmp_path):
        """Test case statement where each branch has multiple resources."""
        manifest = """\
class profile_database (
  String $db_type = 'postgresql',
) {
  case $db_type {
    'postgresql': {
      package { 'postgresql-server':
        ensure => installed,
      }
      file { '/var/lib/pgsql/data/postgresql.conf':
        ensure => file,
        mode   => '0600',
      }
      service { 'postgresql':
        ensure => running,
        enable => true,
      }
    }
    'mysql': {
      package { 'mysql-server':
        ensure => installed,
      }
      file { '/etc/my.cnf':
        ensure => file,
        mode   => '0644',
      }
      service { 'mysqld':
        ensure => running,
        enable => true,
      }
    }
    default: {
      fail("Unsupported database type: ${db_type}")
    }
  }

  file { '/var/log/database/custom.log':
    ensure => file,
    owner  => 'root',
    mode   => '0644',
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_database"

        case_items = [
            item for item in result.execution_order if item.type == "conditional"
        ]
        assert len(case_items) >= 1, "Should have at least one case statement"

        case_item = case_items[0]
        assert case_item.condition_type == "case"

        assert len(case_item.case_branches) >= 2, (
            f"Case should have at least 2 branches (postgresql, mysql, default), "
            f"got {len(case_item.case_branches)}"
        )

        postgresql_branch = [
            b for b in case_item.case_branches if "postgresql" in b.pattern
        ]
        assert len(postgresql_branch) >= 1, "Should have postgresql branch"
        assert len(postgresql_branch[0].items) >= 3, (
            f"PostgreSQL branch should have 3 resources (package, file, service), "
            f"got {len(postgresql_branch[0].items)}"
        )

        resource_items = [
            item for item in result.execution_order if item.type == "resource"
        ]
        resource_names = [
            f"{item.resource_type}[{item.title}]" for item in resource_items
        ]

        assert any("custom.log" in name for name in resource_names), (
            f"Missing file[/var/log/database/custom.log] after case, found: {resource_names}"
        )

    def test_case_with_regex_patterns(self, manifest_service, tmp_path):
        """Test case statement with regex pattern matching."""
        manifest = """\
class profile_hostname_config {
  case $facts['networking']['hostname'] {
    /^web\\d+/: {
      file { '/etc/role':
        ensure  => file,
        content => 'webserver',
      }
    }
    /^db\\d+/: {
      file { '/etc/role':
        ensure  => file,
        content => 'database',
      }
    }
    /^lb\\d+/: {
      file { '/etc/role':
        ensure  => file,
        content => 'loadbalancer',
      }
    }
    default: {
      file { '/etc/role':
        ensure  => file,
        content => 'unknown',
      }
    }
  }

  exec { 'configure-hostname':
    command => '/usr/bin/hostnamectl set-hostname $(cat /etc/role)',
    unless  => '/usr/bin/test -f /etc/role',
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_hostname_config"

        case_items = [
            item for item in result.execution_order if item.type == "conditional"
        ]
        assert len(case_items) >= 1, "Should extract case statement with regex patterns"

        resource_items = [
            item for item in result.execution_order if item.type == "resource"
        ]
        resource_names = [
            f"{item.resource_type}[{item.title}]" for item in resource_items
        ]

        assert any("configure-hostname" in name for name in resource_names), (
            f"Missing exec[configure-hostname] after case, found: {resource_names}"
        )

    def test_case_inside_iteration(self, manifest_service, tmp_path):
        """Test case statement inside an iteration block."""
        manifest = """\
class profile_multi_service (
  Hash $services = {},
) {
  $services.each |String $name, Hash $config| {
    case $config['type'] {
      'systemd': {
        service { $name:
          ensure => running,
          enable => true,
        }
      }
      'docker': {
        exec { "start-${name}":
          command => "/usr/bin/docker start ${name}",
        }
      }
      default: {
        notify { "unknown-service-${name}":
          message => "Unknown service type for ${name}",
        }
      }
    }
  }

  file { '/etc/services.conf':
    ensure => file,
    mode   => '0644',
  }
}
"""
        result = self._analyze(manifest_service, tmp_path, manifest)

        assert isinstance(result, ManifestExecutionAnalysis)
        assert result.class_name == "profile_multi_service"

        iteration_items = [
            item for item in result.execution_order if item.type == "iteration"
        ]
        assert len(iteration_items) >= 1, "Should extract the .each iteration"

        resource_items = [
            item for item in result.execution_order if item.type == "resource"
        ]
        resource_names = [
            f"{item.resource_type}[{item.title}]" for item in resource_items
        ]

        assert any("services.conf" in name for name in resource_names), (
            f"Missing file[/etc/services.conf] after iteration, found: {resource_names}"
        )
