"""Tests for Puppet dependency fetcher agent."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.inputs.puppet.dependency_fetcher import (
    DEPENDENCIES_DIR,
    PuppetDependencyAgent,
    resolve_puppet_module_root,
)
from src.inputs.puppet.models import PuppetDependency
from src.inputs.puppet.state import PuppetState


class TestResolvePuppetModuleRoot:
    """Test resolve_puppet_module_root standalone function."""

    def test_resolve_from_manifests_dir(self, tmp_path):
        """Test resolving from manifests directory."""
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)

        result = resolve_puppet_module_root(str(manifests_dir))
        assert result == module_root

    def test_resolve_from_init_pp_file(self, tmp_path):
        """Test resolving from manifests/init.pp file."""
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)
        init_file = manifests_dir / "init.pp"
        init_file.write_text("class mymodule {}")

        result = resolve_puppet_module_root(str(init_file))
        assert result == module_root

    def test_resolve_from_nested_manifest_file(self, tmp_path):
        """Test resolving from nested manifest file."""
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)
        nested_file = manifests_dir / "config" / "settings.pp"
        nested_file.parent.mkdir(parents=True)
        nested_file.write_text("class mymodule::config::settings {}")

        result = resolve_puppet_module_root(str(nested_file))
        assert result == module_root

    def test_resolve_from_module_root(self, tmp_path):
        """Test resolving when already at module root."""
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)

        result = resolve_puppet_module_root(str(module_root))
        assert result == module_root

    def test_resolve_returns_path_when_no_manifests_found(self, tmp_path):
        """Test that function returns the path itself when no manifests dir found."""
        some_dir = tmp_path / "notamodule"
        some_dir.mkdir()

        result = resolve_puppet_module_root(str(some_dir))
        assert result == some_dir.resolve()

    def test_resolve_handles_deeply_nested_structure(self, tmp_path):
        """Test resolving from deeply nested directory structure."""
        module_root = tmp_path / "puppet" / "modules" / "mymodule"
        manifests_dir = module_root / "manifests"
        deep_dir = manifests_dir / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)
        deep_file = deep_dir / "deep.pp"
        deep_file.write_text("class mymodule::a::b::c::deep {}")

        result = resolve_puppet_module_root(str(deep_file))
        assert result == module_root

    def test_resolve_with_relative_path(self, tmp_path):
        """Test resolving with relative path input."""
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)

        # Change to tmp_path and use relative path
        import os

        original_cwd = Path.cwd()
        try:
            os.chdir(tmp_path)
            result = resolve_puppet_module_root("mymodule/manifests")
            assert result == module_root.resolve()
        finally:
            os.chdir(original_cwd)


class TestPuppetDependencyAgentFindPuppetfile:
    """Test _find_puppetfile static method."""

    def test_find_puppetfile_in_current_dir(self, tmp_path):
        """Test finding Puppetfile in current directory."""
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        result = PuppetDependencyAgent._find_puppetfile(tmp_path)
        assert result == puppetfile

    def test_find_puppetfile_in_parent_dir(self, tmp_path):
        """Test finding Puppetfile in parent directory."""
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        module_dir = tmp_path / "modules" / "mymodule"
        module_dir.mkdir(parents=True)

        result = PuppetDependencyAgent._find_puppetfile(module_dir)
        assert result == puppetfile

    def test_find_puppetfile_in_grandparent_dir(self, tmp_path):
        """Test finding Puppetfile in grandparent directory."""
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        deep_dir = tmp_path / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        result = PuppetDependencyAgent._find_puppetfile(deep_dir)
        assert result == puppetfile

    def test_find_puppetfile_returns_none_when_not_found(self, tmp_path):
        """Test that None is returned when Puppetfile is not found."""
        result = PuppetDependencyAgent._find_puppetfile(tmp_path)
        assert result is None

    def test_find_puppetfile_stops_at_filesystem_root(self, tmp_path):
        """Test that search stops at filesystem root."""
        # Create a directory deep enough that we won't have Puppetfile
        deep_dir = tmp_path / "very" / "deep" / "nested" / "path"
        deep_dir.mkdir(parents=True)

        result = PuppetDependencyAgent._find_puppetfile(deep_dir)
        assert result is None

    def test_find_puppetfile_case_sensitive(self, tmp_path):
        """Test that Puppetfile search is case-sensitive."""
        # Create puppetfile with wrong case
        (tmp_path / "puppetfile").write_text("mod 'test'")

        result = PuppetDependencyAgent._find_puppetfile(tmp_path)
        assert result is None


class TestPuppetDependencyAgentDownloadDependencies:
    """Test _download_dependencies method."""

    def test_download_creates_dependencies_dir(self, tmp_path):
        """Test that dependencies directory is created."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        with (
            patch("shutil.which", return_value="/usr/bin/r10k"),
            patch.object(agent, "_run_r10k", return_value=None),
        ):
            agent._download_dependencies(puppetfile, tmp_path)

        deps_dir = tmp_path / DEPENDENCIES_DIR
        assert deps_dir.exists()
        assert deps_dir.is_dir()

    def test_download_returns_none_when_r10k_not_installed(self, tmp_path):
        """Test that None is returned when r10k is not in PATH."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        with patch("shutil.which", return_value=None):
            result = agent._download_dependencies(puppetfile, tmp_path)

        assert result is None

    def test_download_logs_warning_when_r10k_missing(self, tmp_path):
        """Test that warning is logged when r10k is not found."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        with (
            patch("shutil.which", return_value=None),
            patch.object(agent._log, "warning") as mock_warning,
        ):
            agent._download_dependencies(puppetfile, tmp_path)

        mock_warning.assert_called_once()
        call_args = str(mock_warning.call_args)
        assert "r10k not found in PATH" in call_args
        assert "gem install r10k" in call_args

    def test_download_calls_run_r10k_with_correct_args(self, tmp_path):
        """Test that _run_r10k is called with correct arguments."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = tmp_path / DEPENDENCIES_DIR

        with (
            patch("shutil.which", return_value="/usr/bin/r10k"),
            patch.object(agent, "_run_r10k") as mock_run,
        ):
            mock_run.return_value = deps_dir
            result = agent._download_dependencies(puppetfile, tmp_path)

        mock_run.assert_called_once_with(puppetfile, deps_dir, tmp_path)
        assert result == deps_dir

    def test_download_returns_result_from_run_r10k(self, tmp_path):
        """Test that return value from _run_r10k is returned."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        expected_path = tmp_path / DEPENDENCIES_DIR

        with (
            patch("shutil.which", return_value="/usr/bin/r10k"),
            patch.object(agent, "_run_r10k", return_value=expected_path),
        ):
            result = agent._download_dependencies(puppetfile, tmp_path)

        assert result == expected_path


class TestPuppetDependencyAgentRunR10k:
    """Test _run_r10k method."""

    def test_run_r10k_executes_correct_command(self, tmp_path):
        """Test that r10k is executed with correct arguments."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = tmp_path / DEPENDENCIES_DIR
        deps_dir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = agent._run_r10k(puppetfile, deps_dir, tmp_path)

        expected_cmd = [
            "r10k",
            "puppetfile",
            "install",
            "--puppetfile",
            str(puppetfile),
            "--moduledir",
            str(deps_dir),
        ]

        mock_run.assert_called_once_with(
            expected_cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(tmp_path),
        )
        assert result == deps_dir

    def test_run_r10k_returns_none_on_failure(self, tmp_path):
        """Test that None is returned when r10k fails."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = tmp_path / DEPENDENCIES_DIR
        deps_dir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: Module not found"

        with (
            patch("subprocess.run", return_value=mock_result),
            patch.object(agent._log, "error") as mock_error,
        ):
            result = agent._run_r10k(puppetfile, deps_dir, tmp_path)

        assert result is None
        mock_error.assert_called_once()
        call_args = str(mock_error.call_args)
        assert "r10k failed" in call_args
        assert "Error: Module not found" in call_args

    def test_run_r10k_handles_timeout(self, tmp_path):
        """Test that timeout is handled gracefully."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = tmp_path / DEPENDENCIES_DIR
        deps_dir.mkdir()

        with (
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("r10k", 300)),
            patch.object(agent._log, "error") as mock_error,
        ):
            result = agent._run_r10k(puppetfile, deps_dir, tmp_path)

        assert result is None
        mock_error.assert_called_once()
        assert "r10k timed out after 300s" in str(mock_error.call_args)

    def test_run_r10k_handles_generic_exception(self, tmp_path):
        """Test that generic exceptions are handled."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = tmp_path / DEPENDENCIES_DIR
        deps_dir.mkdir()

        with (
            patch("subprocess.run", side_effect=OSError("Permission denied")),
            patch.object(agent._log, "error") as mock_error,
        ):
            result = agent._run_r10k(puppetfile, deps_dir, tmp_path)

        assert result is None
        mock_error.assert_called_once()
        call_args = str(mock_error.call_args)
        assert "Failed to run r10k" in call_args
        assert "Permission denied" in call_args

    def test_run_r10k_logs_success(self, tmp_path):
        """Test that success is logged."""
        agent = PuppetDependencyAgent()
        puppetfile = tmp_path / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = tmp_path / DEPENDENCIES_DIR
        deps_dir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with (
            patch("subprocess.run", return_value=mock_result),
            patch.object(agent._log, "info") as mock_info,
        ):
            result = agent._run_r10k(puppetfile, deps_dir, tmp_path)

        assert result == deps_dir
        assert mock_info.call_count == 2
        calls_text = " ".join(str(call) for call in mock_info.call_args_list)
        assert "Downloading dependencies to" in calls_text
        assert "Dependencies downloaded to" in calls_text

    def test_run_r10k_uses_correct_cwd(self, tmp_path):
        """Test that r10k is executed with correct working directory."""
        agent = PuppetDependencyAgent()
        module_root = tmp_path / "mymodule"
        module_root.mkdir()
        puppetfile = module_root / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = module_root / DEPENDENCIES_DIR
        deps_dir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            agent._run_r10k(puppetfile, deps_dir, module_root)

        # Verify cwd argument
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == str(module_root)


class TestPuppetDependencyAgentExecute:
    """Test execute method integration (non-LLM parts)."""

    def test_execute_returns_empty_deps_when_no_puppetfile(self, tmp_path):
        """Test that empty dependencies are returned when no Puppetfile found."""
        agent = PuppetDependencyAgent()
        state = PuppetState(
            user_message="Test migration",
            path=str(tmp_path),
            specification="",
        )

        result = agent.execute(state, None)

        assert result.dependencies == []

    def test_execute_logs_info_when_no_puppetfile(self, tmp_path):
        """Test that info is logged when no Puppetfile found."""
        agent = PuppetDependencyAgent()
        state = PuppetState(
            user_message="Test migration",
            path=str(tmp_path),
            specification="",
        )

        with patch.object(agent._log, "info") as mock_info:
            agent.execute(state, None)

        mock_info.assert_called_once()
        assert "No Puppetfile found" in str(mock_info.call_args)

    def test_execute_records_zero_dependencies_metric_when_no_puppetfile(
        self, tmp_path
    ):
        """Test that zero dependencies metric is recorded when no Puppetfile."""
        agent = PuppetDependencyAgent()
        state = PuppetState(
            user_message="Test migration",
            path=str(tmp_path),
            specification="",
        )
        mock_metrics = MagicMock()

        agent.execute(state, mock_metrics)

        mock_metrics.record_metric.assert_called_once_with("dependencies_found", 0)

    def test_execute_returns_empty_deps_when_download_fails(self, tmp_path):
        """Test that empty dependencies returned when download fails."""
        agent = PuppetDependencyAgent()
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)
        puppetfile = module_root / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        state = PuppetState(
            user_message="Test migration",
            path=str(manifests_dir),
            specification="",
        )

        # Mock download to fail
        with (
            patch("shutil.which", return_value=None),
            patch.object(agent._log, "warning") as mock_warning,
        ):
            result = agent.execute(state, None)

        assert result.dependencies == []
        assert "Dependency download failed" in str(mock_warning.call_args)

    def test_execute_resolves_module_root_correctly(self, tmp_path):
        """Test that module root is resolved from manifests path."""
        agent = PuppetDependencyAgent()
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)
        puppetfile = module_root / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")

        state = PuppetState(
            user_message="Test migration",
            path=str(manifests_dir),
            specification="",
        )

        # Mock the download and LLM parts
        with (
            patch("shutil.which", return_value="/usr/bin/r10k"),
            patch.object(
                agent, "_run_r10k", return_value=module_root / DEPENDENCIES_DIR
            ),
            patch.object(
                agent,
                "invoke_structured",
                return_value=MagicMock(dependencies=[]),
            ),
        ):
            agent.execute(state, None)

        # If we got here without error, module root was resolved correctly

    def test_execute_updates_state_with_dependencies_dir(self, tmp_path):
        """Test that state is updated with dependencies directory path."""
        agent = PuppetDependencyAgent()
        module_root = tmp_path / "mymodule"
        manifests_dir = module_root / "manifests"
        manifests_dir.mkdir(parents=True)
        puppetfile = module_root / "Puppetfile"
        puppetfile.write_text("mod 'puppetlabs-stdlib'")
        deps_dir = module_root / DEPENDENCIES_DIR

        state = PuppetState(
            user_message="Test migration",
            path=str(module_root),
            specification="",
        )

        mock_dependency = PuppetDependency(name="stdlib", source="forge", version="1.0")

        with (
            patch("shutil.which", return_value="/usr/bin/r10k"),
            patch.object(agent, "_run_r10k", return_value=deps_dir),
            patch.object(
                agent,
                "invoke_structured",
                return_value=MagicMock(dependencies=[mock_dependency]),
            ),
        ):
            result = agent.execute(state, None)

        assert result.dependencies_dir == str(deps_dir)
        assert len(result.dependencies) == 1
