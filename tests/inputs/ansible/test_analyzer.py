"""Tests for Ansible analyzer file scanning and parsing."""

import yaml

from src.inputs.ansible.analyzer import AnsibleSubagent
from src.inputs.ansible.state import AnsibleAnalysisState


class TestScanFiles:
    """Test _scan_files node of the analyzer workflow."""

    def _make_state(self, path, **overrides) -> AnsibleAnalysisState:
        return AnsibleAnalysisState(
            user_message=overrides.pop("user_message", "Modernize this role"),
            path=str(path),
            specification=overrides.pop("specification", ""),
            **overrides,
        )

    def test_scan_fails_without_tasks_dir(self, tmp_path):
        """Role without tasks/ directory should fail."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert result.failed is True
        assert "tasks/" in result.failure_reason

    def test_scan_succeeds_with_tasks_dir(self, tmp_path):
        """Role with tasks/ directory should succeed."""
        (tmp_path / "tasks").mkdir()
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert result.failed is False
        assert result.collection_dependencies == []

    def test_scan_parses_requirements_yml(self, tmp_path):
        """Should parse collection dependencies from requirements.yml."""
        (tmp_path / "tasks").mkdir()
        requirements = {
            "collections": [
                {"name": "community.general", "version": "5.0.0"},
                {"name": "ansible.utils"},
            ]
        }
        (tmp_path / "requirements.yml").write_text(yaml.dump(requirements))

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert result.failed is False
        assert "community.general" in result.collection_dependencies
        assert "ansible.utils" in result.collection_dependencies
        assert len(result.collection_dependencies) == 2

    def test_scan_parses_string_requirements(self, tmp_path):
        """Should handle string-format collection entries."""
        (tmp_path / "tasks").mkdir()
        requirements = {"collections": ["community.docker"]}
        (tmp_path / "requirements.yml").write_text(yaml.dump(requirements))

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert "community.docker" in result.collection_dependencies

    def test_scan_parses_collections_subdir_requirements(self, tmp_path):
        """Should find requirements.yml in collections/ subdirectory."""
        (tmp_path / "tasks").mkdir()
        (tmp_path / "collections").mkdir()
        requirements = {"collections": [{"name": "ansible.posix"}]}
        (tmp_path / "collections" / "requirements.yml").write_text(
            yaml.dump(requirements)
        )

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert "ansible.posix" in result.collection_dependencies

    def test_scan_handles_empty_requirements(self, tmp_path):
        """Should handle empty or malformed requirements.yml."""
        (tmp_path / "tasks").mkdir()
        (tmp_path / "requirements.yml").write_text("---\n")

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert result.failed is False
        assert result.collection_dependencies == []

    def test_scan_handles_invalid_yaml_requirements(self, tmp_path):
        """Should not crash on invalid YAML in requirements.yml."""
        (tmp_path / "tasks").mkdir()
        (tmp_path / "requirements.yml").write_text("not: [valid: yaml: {{{")

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(tmp_path)
        result = subagent._scan_files(state)
        assert result.failed is False


class TestAnalyzeStructureHelpers:
    """Test helper methods of _analyze_structure without LLM calls."""

    def test_collect_static_files(self, tmp_path):
        """Should collect file paths from files/ directory."""
        files_dir = tmp_path / "files"
        files_dir.mkdir()
        (files_dir / "index.html").write_text("<h1>Hello</h1>")
        (files_dir / "config.txt").write_text("key=value")

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._collect_static_files(files_dir, slog)
        assert len(result) == 2
        assert any("index.html" in f for f in result)
        assert any("config.txt" in f for f in result)

    def test_collect_static_files_empty_dir(self, tmp_path):
        """Should return empty list for missing directory."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._collect_static_files(tmp_path / "nonexistent", slog)
        assert result == []

    def test_collect_static_files_nested(self, tmp_path):
        """Should recursively collect files from subdirectories."""
        files_dir = tmp_path / "files"
        (files_dir / "sub").mkdir(parents=True)
        (files_dir / "top.txt").write_text("top")
        (files_dir / "sub" / "nested.txt").write_text("nested")

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._collect_static_files(files_dir, slog)
        assert len(result) == 2

    def test_analyze_yaml_files_missing_dir(self, tmp_path):
        """Should return empty list when directory doesn't exist."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._analyze_yaml_files(tmp_path / "nonexistent", "tasks", slog)
        assert result == []

    def test_analyze_vars_files_missing_dir(self, tmp_path):
        """Should return empty list when directory doesn't exist."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._analyze_vars_files(
            tmp_path / "nonexistent", "defaults", slog
        )
        assert result == []

    def test_analyze_meta_missing_dir(self, tmp_path):
        """Should return None when meta directory doesn't exist."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._analyze_meta(tmp_path / "nonexistent", slog)
        assert result is None

    def test_analyze_meta_missing_main_yml(self, tmp_path):
        """Should return None when meta/main.yml doesn't exist."""
        meta_dir = tmp_path / "meta"
        meta_dir.mkdir()

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._analyze_meta(meta_dir, slog)
        assert result is None

    def test_analyze_templates_missing_dir(self, tmp_path):
        """Should return empty list when templates dir doesn't exist."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.utils.logging import get_logger

        slog = get_logger(__name__)
        result = subagent._analyze_templates(tmp_path / "nonexistent", slog)
        assert result == []


class TestBuildExecutionSummary:
    """Test execution summary generation."""

    def test_empty_analysis(self):
        """Summary of empty analysis should still produce output."""
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        from src.inputs.ansible.models import AnsibleStructuredAnalysis

        analysis = AnsibleStructuredAnalysis()
        summary = subagent._build_execution_summary(analysis)
        assert "Total files analyzed: 0" in summary
        assert "ANSIBLE ROLE ANALYSIS SUMMARY" in summary

    def test_summary_includes_task_info(self):
        """Summary should include task module and name."""
        from src.inputs.ansible.models import (
            AnsibleStructuredAnalysis,
            TaskExecution,
            TaskFileAnalysisResult,
            TaskFileExecutionAnalysis,
        )

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        analysis = AnsibleStructuredAnalysis(
            tasks_files=[
                TaskFileAnalysisResult(
                    file_path="tasks/main.yml",
                    file_type="tasks",
                    analysis=TaskFileExecutionAnalysis(
                        tasks=[
                            TaskExecution(
                                name="Install nginx",
                                module="yum",
                                note="uses short module name",
                            )
                        ]
                    ),
                )
            ]
        )
        summary = subagent._build_execution_summary(analysis)
        assert "TASKS:" in summary
        assert "Install nginx" in summary
        assert "[yum]" in summary
        assert "NOTE: uses short module name" in summary

    def test_summary_includes_handler_info(self):
        """Summary should include handler section."""
        from src.inputs.ansible.models import (
            AnsibleStructuredAnalysis,
            TaskExecution,
            TaskFileAnalysisResult,
            TaskFileExecutionAnalysis,
        )

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        analysis = AnsibleStructuredAnalysis(
            handlers_files=[
                TaskFileAnalysisResult(
                    file_path="handlers/main.yml",
                    file_type="handlers",
                    analysis=TaskFileExecutionAnalysis(
                        tasks=[TaskExecution(name="Restart nginx", module="service")]
                    ),
                )
            ]
        )
        summary = subagent._build_execution_summary(analysis)
        assert "HANDLERS:" in summary
        assert "Restart nginx" in summary

    def test_summary_includes_vars_info(self):
        """Summary should include defaults/vars variables."""
        from src.inputs.ansible.models import (
            AnsibleStructuredAnalysis,
            VariablesAnalysis,
            VariablesAnalysisResult,
        )

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        analysis = AnsibleStructuredAnalysis(
            defaults_files=[
                VariablesAnalysisResult(
                    file_path="defaults/main.yml",
                    file_type="defaults",
                    analysis=VariablesAnalysis(
                        variables={"nginx_port": 80},
                        notes=["port should be integer"],
                    ),
                )
            ]
        )
        summary = subagent._build_execution_summary(analysis)
        assert "DEFAULTS:" in summary
        assert "nginx_port" in summary
        assert "port should be integer" in summary

    def test_summary_includes_meta_info(self):
        """Summary should include meta section."""
        from src.inputs.ansible.models import (
            AnsibleStructuredAnalysis,
            MetaAnalysis,
            MetaAnalysisResult,
        )

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        analysis = AnsibleStructuredAnalysis(
            meta=MetaAnalysisResult(
                file_path="meta/main.yml",
                analysis=MetaAnalysis(
                    role_name="webserver",
                    dependencies=[{"role": "common"}],
                ),
            )
        )
        summary = subagent._build_execution_summary(analysis)
        assert "META:" in summary
        assert "webserver" in summary

    def test_summary_includes_templates(self):
        """Summary should include template section."""
        from src.inputs.ansible.models import (
            AnsibleStructuredAnalysis,
            TemplateAnalysis,
            TemplateAnalysisResult,
        )

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        analysis = AnsibleStructuredAnalysis(
            templates=[
                TemplateAnalysisResult(
                    file_path="templates/nginx.conf.j2",
                    analysis=TemplateAnalysis(
                        variables_used=["server_name"],
                        bare_variables=["hostname"],
                    ),
                )
            ]
        )
        summary = subagent._build_execution_summary(analysis)
        assert "TEMPLATES:" in summary
        assert "nginx.conf.j2" in summary
        assert "Bare variables: hostname" in summary

    def test_summary_includes_static_files(self):
        """Summary should include static files section."""
        from src.inputs.ansible.models import AnsibleStructuredAnalysis

        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        analysis = AnsibleStructuredAnalysis(static_files=["files/index.html"])
        summary = subagent._build_execution_summary(analysis)
        assert "STATIC FILES:" in summary
        assert "files/index.html" in summary


class TestCheckFailure:
    """Test conditional edge for failure checking."""

    def _make_state(self, **overrides) -> AnsibleAnalysisState:
        return AnsibleAnalysisState(
            user_message=overrides.pop("user_message", "test"),
            path=overrides.pop("path", "/tmp/test"),
            specification=overrides.pop("specification", ""),
            **overrides,
        )

    def test_continue_when_not_failed(self):
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state()
        assert subagent._check_failure_after_agent(state) == "continue"

    def test_failed_when_marked_failed(self):
        subagent = AnsibleSubagent.__new__(AnsibleSubagent)
        state = self._make_state(failed=True, failure_reason="error")
        assert subagent._check_failure_after_agent(state) == "failed"
