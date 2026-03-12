"""Tests for Ansible analysis domain models."""

from src.inputs.ansible.models import (
    AnsibleStructuredAnalysis,
    MetaAnalysis,
    MetaAnalysisResult,
    TaskExecution,
    TaskFileAnalysisResult,
    TaskFileExecutionAnalysis,
    TemplateAnalysis,
    TemplateAnalysisResult,
    VariablesAnalysis,
    VariablesAnalysisResult,
)


class TestTaskExecution:
    """Test TaskExecution model."""

    def test_defaults(self):
        task = TaskExecution()
        assert task.name == ""
        assert task.module == ""
        assert task.parameters == {}
        assert task.loop is None
        assert task.condition is None
        assert task.notify == []
        assert task.privilege_escalation == {}
        assert task.note is None

    def test_with_all_fields(self):
        task = TaskExecution(
            name="Install nginx",
            module="yum",
            parameters={"name": "nginx", "state": "present"},
            loop="with_items",
            condition='ansible_os_family == "RedHat"',
            notify=["restart nginx"],
            privilege_escalation={"sudo": True},
            note="uses short module name 'yum'",
        )
        assert task.name == "Install nginx"
        assert task.module == "yum"
        assert task.parameters["name"] == "nginx"
        assert task.loop == "with_items"
        assert task.condition == 'ansible_os_family == "RedHat"'
        assert task.notify == ["restart nginx"]
        assert task.privilege_escalation == {"sudo": True}
        assert task.note == "uses short module name 'yum'"


class TestTaskFileExecutionAnalysis:
    """Test TaskFileExecutionAnalysis model."""

    def test_empty_tasks(self):
        analysis = TaskFileExecutionAnalysis()
        assert analysis.tasks == []

    def test_with_tasks(self):
        analysis = TaskFileExecutionAnalysis(
            tasks=[
                TaskExecution(name="Install", module="yum"),
                TaskExecution(name="Start", module="service"),
            ]
        )
        assert len(analysis.tasks) == 2
        assert analysis.tasks[0].name == "Install"


class TestVariablesAnalysis:
    """Test VariablesAnalysis model."""

    def test_defaults(self):
        analysis = VariablesAnalysis()
        assert analysis.variables == {}
        assert analysis.notes == []

    def test_with_variables_and_notes(self):
        analysis = VariablesAnalysis(
            variables={"nginx_port": 80, "nginx_ssl_enabled": "yes"},
            notes=["nginx_ssl_enabled uses 'yes' instead of true"],
        )
        assert analysis.variables["nginx_port"] == 80
        assert len(analysis.notes) == 1


class TestMetaAnalysis:
    """Test MetaAnalysis model."""

    def test_defaults(self):
        meta = MetaAnalysis()
        assert meta.role_name == ""
        assert meta.dependencies == []
        assert meta.platforms == []
        assert meta.galaxy_info == {}

    def test_with_data(self):
        meta = MetaAnalysis(
            role_name="webserver",
            dependencies=[{"role": "common"}],
            platforms=[{"name": "Ubuntu", "versions": ["focal"]}],
            galaxy_info={"author": "devops", "license": "Apache-2.0"},
        )
        assert meta.role_name == "webserver"
        assert len(meta.dependencies) == 1
        assert meta.dependencies[0]["role"] == "common"


class TestTemplateAnalysis:
    """Test TemplateAnalysis model."""

    def test_defaults(self):
        tmpl = TemplateAnalysis()
        assert tmpl.variables_used == []
        assert tmpl.bare_variables == []
        assert tmpl.deprecated_tests == []
        assert tmpl.notes == []

    def test_with_issues(self):
        tmpl = TemplateAnalysis(
            variables_used=["server_name", "listen_port"],
            bare_variables=["hostname"],
            deprecated_tests=["is undefined"],
            notes=["Uses legacy fact access"],
        )
        assert len(tmpl.variables_used) == 2
        assert "hostname" in tmpl.bare_variables


class TestAnsibleStructuredAnalysis:
    """Test AnsibleStructuredAnalysis aggregate model."""

    def _make_analysis(self):
        """Build a sample structured analysis."""
        return AnsibleStructuredAnalysis(
            tasks_files=[
                TaskFileAnalysisResult(
                    file_path="tasks/main.yml",
                    file_type="tasks",
                    analysis=TaskFileExecutionAnalysis(
                        tasks=[TaskExecution(name="Install", module="yum")]
                    ),
                ),
                TaskFileAnalysisResult(
                    file_path="tasks/configure.yml",
                    file_type="tasks",
                    analysis=TaskFileExecutionAnalysis(tasks=[]),
                ),
            ],
            handlers_files=[
                TaskFileAnalysisResult(
                    file_path="handlers/main.yml",
                    file_type="handlers",
                    analysis=TaskFileExecutionAnalysis(
                        tasks=[TaskExecution(name="Restart nginx", module="service")]
                    ),
                ),
            ],
            defaults_files=[
                VariablesAnalysisResult(
                    file_path="defaults/main.yml",
                    file_type="defaults",
                    analysis=VariablesAnalysis(variables={"nginx_port": 80}),
                ),
            ],
            vars_files=[],
            meta=MetaAnalysisResult(
                file_path="meta/main.yml",
                analysis=MetaAnalysis(role_name="webserver"),
            ),
            templates=[
                TemplateAnalysisResult(
                    file_path="templates/nginx.conf.j2",
                    analysis=TemplateAnalysis(variables_used=["server_name"]),
                ),
            ],
            static_files=["files/index.html"],
        )

    def test_get_total_files_analyzed(self):
        analysis = self._make_analysis()
        # 2 tasks + 1 handler + 1 defaults + 0 vars + 1 meta + 1 template = 6
        assert analysis.get_total_files_analyzed() == 6

    def test_get_total_files_analyzed_no_meta(self):
        analysis = AnsibleStructuredAnalysis()
        assert analysis.get_total_files_analyzed() == 0

    def test_analyzed_file_paths(self):
        analysis = self._make_analysis()
        paths = analysis.analyzed_file_paths
        assert "tasks/main.yml" in paths
        assert "tasks/configure.yml" in paths
        assert "handlers/main.yml" in paths
        assert "defaults/main.yml" in paths
        assert "meta/main.yml" in paths
        assert "templates/nginx.conf.j2" in paths
        assert "files/index.html" in paths
        assert len(paths) == 7

    def test_analyzed_file_paths_deduplication(self):
        analysis = AnsibleStructuredAnalysis(
            static_files=["files/a.txt", "files/a.txt"],
        )
        paths = analysis.analyzed_file_paths
        assert len(paths) == 1

    def test_analyzed_file_paths_sorted(self):
        analysis = self._make_analysis()
        paths = analysis.analyzed_file_paths
        assert paths == sorted(paths)
