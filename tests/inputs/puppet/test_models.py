"""Tests for Puppet analysis domain models."""

from src.inputs.puppet.models import (
    ClassInheritance,
    CredentialAnalysis,
    CredentialAnalysisResult,
    CredentialEntry,
    CustomTypeAnalysis,
    CustomTypeAnalysisResult,
    ExecutionItem,
    HieraDataAnalysis,
    HieraDataAnalysisResult,
    HieraHierarchy,
    HieraLevel,
    HieraVariableMapping,
    ManifestAnalysisResult,
    ManifestExecutionAnalysis,
    PuppetStructuredAnalysis,
    PuppetTemplateAnalysis,
    TemplateAnalysisResult,
)


class TestExecutionItem:
    def test_resource_defaults(self):
        res = ExecutionItem(type="resource", resource_type="package", title="haproxy")
        assert res.type == "resource"
        assert res.resource_type == "package"
        assert res.title == "haproxy"
        assert res.attributes == {}

    def test_resource_with_attributes(self):
        res = ExecutionItem(
            type="resource",
            resource_type="file",
            title="/etc/haproxy/haproxy.cfg",
            attributes={"ensure": "file", "owner": "root", "mode": "0640"},
        )
        assert res.attributes["ensure"] == "file"
        assert res.attributes["mode"] == "0640"

    def test_exported_resource(self):
        res = ExecutionItem(
            type="exported_resource",
            resource_type="file",
            title="/tmp/exported",
            attributes={"tag": "exported"},
        )
        assert res.type == "exported_resource"
        assert res.format_label() == "[exported] file[/tmp/exported]"

    def test_collector(self):
        collector = ExecutionItem(
            type="collector", resource_type="File", query="tag == 'exported'"
        )
        assert collector.type == "collector"
        assert "collector" in collector.format_label()


class TestManifestExecutionAnalysis:
    def test_defaults(self):
        analysis = ManifestExecutionAnalysis()
        assert analysis.class_name == ""
        assert analysis.class_parameters == {}
        assert analysis.execution_order == []
        assert analysis.puppetdb_queries == []
        assert analysis.relationship_chains == []

    def test_with_full_manifest(self):
        analysis = ManifestExecutionAnalysis(
            class_name="profile_haproxy",
            class_parameters={"package_name": "String", "config_dir": "String"},
            execution_order=[
                ExecutionItem(
                    type="resource", resource_type="package", title="haproxy"
                ),
                ExecutionItem(
                    type="class_include",
                    class_name="profile_haproxy::config",
                    relationship="include",
                ),
                ExecutionItem(
                    type="class_include",
                    class_name="profile_haproxy::service",
                    relationship="contain",
                ),
                ExecutionItem(
                    type="conditional",
                    condition="$ssl_enabled",
                    condition_type="if",
                    execution_order=[],
                ),
                ExecutionItem(
                    type="iteration",
                    iterator_type="each",
                    collection_variable="$backends",
                    item_variable="$name, $config",
                    execution_order=[],
                ),
            ],
            relationship_chains=[
                "Package[haproxy] -> File[haproxy.cfg] ~> Service[haproxy]"
            ],
        )
        assert analysis.class_name == "profile_haproxy"
        assert len(analysis.class_parameters) == 2
        assert len(analysis.execution_order) == 5

        resources = [i for i in analysis.execution_order if i.type == "resource"]
        assert len(resources) == 1

        class_includes = [
            i for i in analysis.execution_order if i.type == "class_include"
        ]
        assert len(class_includes) == 2
        assert class_includes[0].relationship == "include"
        assert class_includes[1].relationship == "contain"

        conditionals = [i for i in analysis.execution_order if i.type == "conditional"]
        assert len(conditionals) == 1
        assert conditionals[0].condition_type == "if"

        iterations = [i for i in analysis.execution_order if i.type == "iteration"]
        assert len(iterations) == 1
        assert iterations[0].iterator_type == "each"

        assert len(analysis.relationship_chains) == 1


class TestClassInheritance:
    def test_basic(self):
        inh = ClassInheritance(
            parent_class="profile_haproxy::params",
            child_class="profile_haproxy",
        )
        assert inh.parent_class == "profile_haproxy::params"
        assert inh.overridden_params == []

    def test_with_overrides(self):
        inh = ClassInheritance(
            parent_class="base",
            child_class="derived",
            overridden_params=["package_name", "service_name"],
        )
        assert len(inh.overridden_params) == 2


class TestHieraVariableMapping:
    def test_defaults(self):
        var = HieraVariableMapping(
            puppet_key="profile_haproxy::package_name", value_type="string"
        )
        assert var.puppet_key == "profile_haproxy::package_name"
        assert var.is_encrypted is False
        assert var.ansible_target == ""
        assert var.ansible_variable_name == ""

    def test_encrypted(self):
        var = HieraVariableMapping(
            puppet_key="profile_haproxy::stats_password",
            value_type="string",
            is_encrypted=True,
            ansible_target="defaults/main.yml",
            ansible_variable_name="haproxy_stats_password",
        )
        assert var.is_encrypted is True
        assert var.ansible_variable_name == "haproxy_stats_password"


class TestHieraHierarchy:
    def test_empty(self):
        h = HieraHierarchy()
        assert h.version == 5
        assert h.levels == []
        assert h.total_data_files == 0

    def test_with_levels(self):
        h = HieraHierarchy(
            version=5,
            levels=[
                HieraLevel(
                    name="Per-node", path_pattern="nodes/%{trusted.certname}.yaml"
                ),
                HieraLevel(
                    name="Common",
                    path_pattern="common.yaml",
                    resolved_files=["/tmp/data/common.yaml"],
                ),
            ],
            total_data_files=1,
        )
        assert len(h.levels) == 2
        assert h.levels[0].resolved_files == []
        assert h.levels[1].resolved_files == ["/tmp/data/common.yaml"]


class TestPuppetStructuredAnalysis:
    def _make_analysis(self):
        return PuppetStructuredAnalysis(
            manifests=[
                ManifestAnalysisResult(
                    file_path="manifests/init.pp",
                    analysis=ManifestExecutionAnalysis(class_name="profile_haproxy"),
                ),
                ManifestAnalysisResult(
                    file_path="manifests/config.pp",
                    analysis=ManifestExecutionAnalysis(
                        class_name="profile_haproxy::config"
                    ),
                ),
            ],
            hiera_data=[
                HieraDataAnalysisResult(
                    file_path="data/common.yaml",
                    hierarchy_level="Common defaults",
                    raw_content="---\nprofile_haproxy::package_name: haproxy\n",
                    analysis=HieraDataAnalysis(
                        variables=[
                            HieraVariableMapping(
                                puppet_key="profile_haproxy::package_name",
                                value_type="string",
                            )
                        ]
                    ),
                ),
            ],
            templates=[
                TemplateAnalysisResult(
                    file_path="templates/haproxy.cfg.erb",
                    analysis=PuppetTemplateAnalysis(
                        template_type="erb",
                        variables_used=["@log_server", "@maxconn"],
                    ),
                ),
            ],
            custom_types=[
                CustomTypeAnalysisResult(
                    file_path="lib/facter/haproxy_version.rb",
                    component_type="fact",
                    analysis=CustomTypeAnalysis(
                        component_type="fact",
                        name="haproxy_version",
                        ansible_equivalent="ansible.builtin.command: haproxy -v",
                    ),
                ),
            ],
        )

    def test_total_files(self):
        analysis = self._make_analysis()
        assert analysis.get_total_files_analyzed() == 5

    def test_total_files_empty(self):
        analysis = PuppetStructuredAnalysis()
        assert analysis.get_total_files_analyzed() == 0

    def test_analyzed_file_paths(self):
        analysis = self._make_analysis()
        paths = analysis.analyzed_file_paths
        assert "manifests/init.pp" in paths
        assert "manifests/config.pp" in paths
        assert "data/common.yaml" in paths
        assert "templates/haproxy.cfg.erb" in paths
        assert "lib/facter/haproxy_version.rb" in paths
        assert len(paths) == 5

    def test_analyzed_file_paths_sorted(self):
        analysis = self._make_analysis()
        paths = analysis.analyzed_file_paths
        assert paths == sorted(paths)

    def test_analyzed_file_paths_deduplication(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                ManifestAnalysisResult(
                    file_path="manifests/init.pp",
                    analysis=ManifestExecutionAnalysis(),
                ),
                ManifestAnalysisResult(
                    file_path="manifests/init.pp",
                    analysis=ManifestExecutionAnalysis(),
                ),
            ],
        )
        paths = analysis.analyzed_file_paths
        assert len(paths) == 1


class TestCredentialModels:
    def test_credential_entry(self):
        entry = CredentialEntry(
            purpose="HAProxy stats page authentication",
            variable_names=["profile_haproxy::stats_password"],
            source_files=["data/common.yaml"],
            storage_method="eyaml",
            usage_context="HAProxy stats listen section",
            ansible_recommendation="ansible-vault",
        )
        assert entry.storage_method == "eyaml"
        assert len(entry.variable_names) == 1

    def test_credential_analysis(self):
        analysis = CredentialAnalysis(
            credentials=[
                CredentialEntry(
                    purpose="Stats password",
                    variable_names=["stats_password"],
                    source_files=["common.yaml"],
                    storage_method="eyaml",
                    usage_context="stats",
                    ansible_recommendation="vault",
                )
            ],
            total_detected=1,
        )
        assert analysis.total_detected == 1
        assert len(analysis.credentials) == 1

    def test_credential_analysis_result(self):
        result = CredentialAnalysisResult(
            analysis=CredentialAnalysis(total_detected=0),
        )
        assert result.analysis.total_detected == 0
        assert result.analysis.credentials == []
