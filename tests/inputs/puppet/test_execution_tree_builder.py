"""Tests for Puppet execution tree builder."""

from src.inputs.puppet.execution_tree_builder import (
    CaseBranchNode,
    ClassNode,
    CollectorNode,
    ConditionalNode,
    ExecutionTreeNode,
    ExportedResourceNode,
    IterationNode,
    PuppetExecutionTreeBuilder,
    RelationshipNode,
    ResourceNode,
    VirtualResourceNode,
)
from src.inputs.puppet.models import (
    CaseBranch,
    ClassInheritance,
    ExecutionItem,
    ManifestAnalysisResult,
    ManifestExecutionAnalysis,
    NestedExecutionItem,
    PuppetStructuredAnalysis,
)


def _make_manifest(class_name, file_path, **kwargs) -> ManifestAnalysisResult:
    return ManifestAnalysisResult(
        file_path=file_path,
        analysis=ManifestExecutionAnalysis(class_name=class_name, **kwargs),
    )


class TestExecutionTreeNodes:
    def test_class_format(self):
        node = ClassNode(
            name="profile_webapp",
            file_path="manifests/init.pp",
        )
        label = node.format_label()
        assert "[class] profile_webapp" in label
        assert "manifests/init.pp" in label
        assert node.node_type == "class"

    def test_class_with_details(self):
        node = ClassNode(
            name="profile_webapp",
            file_path="manifests/init.pp",
            details="entry point",
        )
        label = node.format_label()
        assert "(entry point)" in label

    def test_resource_format(self):
        node = ResourceNode(name="package[webapp]")
        assert node.format_label() == "[resource] package[webapp]"
        assert node.node_type == "resource"

    def test_iteration_format(self):
        node = IterationNode(name="$backends.each |$name|")
        assert "LOOP" in node.format_label()
        assert node.node_type == "iteration"

    def test_conditional_format(self):
        node = ConditionalNode(name="if $ssl_enabled")
        assert "[conditional]" in node.format_label()
        assert node.node_type == "conditional"

    def test_exported_format(self):
        node = ExportedResourceNode(name="nagios_host[web01]")
        assert "@@" in node.format_label()
        assert node.node_type == "exported"

    def test_virtual_format(self):
        node = VirtualResourceNode(name="user[deploy]")
        assert "@" in node.format_label()
        assert node.node_type == "virtual"

    def test_collector_format(self):
        node = CollectorNode(name="Nagios_host <| tag == production |>")
        assert "<<| |>>" in node.format_label()
        assert node.node_type == "collector"

    def test_relationship_format(self):
        node = RelationshipNode(name="Package[nginx] -> Service[nginx]")
        assert "[ordering]" in node.format_label()
        assert node.node_type == "relationship"

    def test_base_class_is_abstract(self):
        import pytest

        with pytest.raises(TypeError):
            ExecutionTreeNode(name="test")  # pyrefly: ignore[bad-instantiation]


class TestPuppetExecutionTreeBuilder:
    def test_simple_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "profile_webapp",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="class_include",
                            class_name="profile_webapp::install",
                            relationship="include",
                        ),
                    ],
                ),
                _make_manifest(
                    "profile_webapp::install",
                    "manifests/install.pp",
                    execution_order=[
                        ExecutionItem(
                            type="resource",
                            resource_type="package",
                            title="webapp",
                            attributes={"ensure": "installed"},
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        assert root.name == "profile_webapp"
        assert root.node_type == "class"
        assert isinstance(root, ClassNode)
        assert len(root.children) == 1
        child = root.children[0]
        assert child.name == "profile_webapp::install"
        assert isinstance(child, ClassNode)
        assert len(child.children) == 1
        assert isinstance(child.children[0], ResourceNode)
        assert "package" in child.children[0].name

    def test_entry_class_detection_via_init_pp(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest("profile_webapp::config", "manifests/config.pp"),
                _make_manifest("profile_webapp", "manifests/init.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        assert root.name == "profile_webapp"

    def test_entry_class_fallback_to_first(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest("profile_webapp::config", "manifests/config.pp"),
                _make_manifest("profile_webapp::install", "manifests/install.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        assert root.name == "profile_webapp::config"

    def test_no_manifests(self):
        analysis = PuppetStructuredAnalysis()
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        assert "(no entry class found)" in root.name

    def test_circular_reference_detection(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "a",
                    "manifests/a.pp",
                    execution_order=[
                        ExecutionItem(
                            type="class_include", class_name="b", relationship="include"
                        ),
                    ],
                ),
                _make_manifest(
                    "b",
                    "manifests/b.pp",
                    execution_order=[
                        ExecutionItem(
                            type="class_include", class_name="a", relationship="include"
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree(entry_class="a")

        assert root.name == "a"
        b_node = root.children[0]
        assert b_node.name == "b"
        circular_ref = b_node.children[0]
        assert "CIRCULAR" in (circular_ref.details or "")

    def test_unanalyzed_class_reference(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="class_include",
                            class_name="external::module",
                            relationship="include",
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        ext_node = root.children[0]
        assert ext_node.name == "external::module"
        assert "not analyzed" in (ext_node.details or "")

    def test_inheritance(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "child",
                    "manifests/init.pp",
                    class_inherits=ClassInheritance(
                        parent_class="parent",
                        child_class="child",
                        overridden_params=["package_name"],
                    ),
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        assert any("inherits parent" in c.name for c in root.children)

    def test_conditionals_in_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="conditional",
                            condition="$ssl_enabled",
                            condition_type="if",
                            execution_order=[],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        cond_nodes = [c for c in root.children if isinstance(c, ConditionalNode)]
        assert len(cond_nodes) == 1
        assert "ssl_enabled" in cond_nodes[0].name

    def test_iterations_in_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="iteration",
                            iterator_type="each",
                            collection_variable="$backends",
                            item_variable="$name, $config",
                            execution_order=[],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        iter_nodes = [c for c in root.children if isinstance(c, IterationNode)]
        assert len(iter_nodes) == 1
        assert "$backends" in iter_nodes[0].name

    def test_exported_and_virtual_resources(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="exported_resource",
                            resource_type="nagios_host",
                            title="web01",
                        ),
                        ExecutionItem(
                            type="virtual_resource",
                            resource_type="user",
                            title="deploy",
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        exported = [c for c in root.children if isinstance(c, ExportedResourceNode)]
        virtual = [c for c in root.children if isinstance(c, VirtualResourceNode)]
        assert len(exported) == 1
        assert "nagios_host" in exported[0].name
        assert len(virtual) == 1
        assert "user" in virtual[0].name

    def test_relationship_chains(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    relationship_chains=[
                        "Package[webapp] -> File[webapp.cfg] ~> Service[webapp]"
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        rel_nodes = [c for c in root.children if isinstance(c, RelationshipNode)]
        assert len(rel_nodes) == 1
        assert "Package[webapp]" in rel_nodes[0].name

    def test_resource_details_extraction(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="resource",
                            resource_type="file",
                            title="/etc/webapp/app.cfg",
                            attributes={
                                "ensure": "file",
                                "owner": "root",
                                "mode": "0640",
                            },
                        ),
                        ExecutionItem(
                            type="resource",
                            resource_type="exec",
                            title="reload_config",
                            attributes={"command": "/usr/sbin/webapp -c"},
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        file_node = root.children[0]
        assert isinstance(file_node, ResourceNode)
        assert "ensure: file" in (file_node.details or "")
        exec_node = root.children[1]
        assert isinstance(exec_node, ResourceNode)
        assert "command:" in (exec_node.details or "")


class TestFormatTree:
    def test_format_simple_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="resource", resource_type="package", title="webapp"
                        ),
                        ExecutionItem(
                            type="class_include",
                            class_name="main::config",
                            relationship="include",
                        ),
                    ],
                ),
                _make_manifest("main::config", "manifests/config.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        output = builder.format_tree(root)

        assert "[class] main" in output
        assert "[resource] package[webapp]" in output
        assert "[class] main::config" in output
        assert "├── " in output or "└── " in output

    def test_format_deep_nesting(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "a",
                    "manifests/a.pp",
                    execution_order=[
                        ExecutionItem(
                            type="class_include", class_name="b", relationship="include"
                        )
                    ],
                ),
                _make_manifest(
                    "b",
                    "manifests/b.pp",
                    execution_order=[
                        ExecutionItem(
                            type="class_include", class_name="c", relationship="include"
                        )
                    ],
                ),
                _make_manifest("c", "manifests/c.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree(entry_class="a")
        output = builder.format_tree(root)

        lines = output.strip().split("\n")
        assert len(lines) == 3
        assert "[class] a" in lines[0]
        assert "[class] b" in lines[1]
        assert "[class] c" in lines[2]


class TestCaseBranchesInTree:
    def test_simple_case_branches(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "profile_packages",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="conditional",
                            condition="$facts['os']['family']",
                            condition_type="case",
                            case_branches=[
                                CaseBranch(
                                    pattern="RedHat",
                                    items=[
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="package",
                                            title="httpd",
                                            attributes={"ensure": "installed"},
                                        ),
                                    ],
                                ),
                                CaseBranch(
                                    pattern="Debian",
                                    items=[
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="package",
                                            title="apache2",
                                            attributes={"ensure": "installed"},
                                        ),
                                    ],
                                ),
                                CaseBranch(
                                    pattern="default",
                                    items=[],
                                    note="Unsupported OS",
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        cond_nodes = [c for c in root.children if isinstance(c, ConditionalNode)]
        assert len(cond_nodes) == 1
        assert "case" in cond_nodes[0].name

        branch_nodes = [
            c for c in cond_nodes[0].children if isinstance(c, CaseBranchNode)
        ]
        assert len(branch_nodes) == 3
        assert branch_nodes[0].name == "RedHat"
        assert branch_nodes[1].name == "Debian"
        assert branch_nodes[2].name == "default"

        redhat_resources = [
            c for c in branch_nodes[0].children if isinstance(c, ResourceNode)
        ]
        assert len(redhat_resources) == 1
        assert "httpd" in redhat_resources[0].name

        assert len(branch_nodes[2].children) == 0

    def test_case_with_resources_after(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "profile_webserver",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="conditional",
                            condition="$::osfamily",
                            condition_type="case",
                            case_branches=[
                                CaseBranch(
                                    pattern="RedHat",
                                    items=[
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="package",
                                            title="httpd",
                                            attributes={"ensure": "installed"},
                                        ),
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="service",
                                            title="httpd",
                                            attributes={"ensure": "running"},
                                        ),
                                    ],
                                ),
                                CaseBranch(
                                    pattern="Debian",
                                    items=[
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="package",
                                            title="apache2",
                                            attributes={"ensure": "installed"},
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        ExecutionItem(
                            type="resource",
                            resource_type="file",
                            title="/etc/webserver/custom.conf",
                            attributes={"ensure": "file", "mode": "0644"},
                        ),
                        ExecutionItem(
                            type="resource",
                            resource_type="exec",
                            title="reload-webserver",
                            attributes={"command": "/usr/bin/systemctl reload httpd"},
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        assert len(root.children) == 3

        assert isinstance(root.children[0], ConditionalNode)

        resource_nodes = [c for c in root.children if isinstance(c, ResourceNode)]
        assert len(resource_nodes) == 2
        resource_names = [r.name for r in resource_nodes]
        assert any("custom.conf" in n for n in resource_names)
        assert any("reload-webserver" in n for n in resource_names)

    def test_case_branch_with_class_include(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "profile_app",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="conditional",
                            condition="$::osfamily",
                            condition_type="case",
                            case_branches=[
                                CaseBranch(
                                    pattern="RedHat",
                                    items=[
                                        NestedExecutionItem(
                                            type="class_include",
                                            class_name="profile_app::redhat",
                                            relationship="include",
                                        ),
                                    ],
                                ),
                                CaseBranch(
                                    pattern="Debian",
                                    items=[
                                        NestedExecutionItem(
                                            type="class_include",
                                            class_name="profile_app::debian",
                                            relationship="include",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
                _make_manifest(
                    "profile_app::redhat",
                    "manifests/redhat.pp",
                    execution_order=[
                        ExecutionItem(
                            type="resource",
                            resource_type="package",
                            title="httpd",
                            attributes={"ensure": "installed"},
                        ),
                    ],
                ),
                _make_manifest(
                    "profile_app::debian",
                    "manifests/debian.pp",
                    execution_order=[
                        ExecutionItem(
                            type="resource",
                            resource_type="package",
                            title="apache2",
                            attributes={"ensure": "installed"},
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        cond_node = root.children[0]
        assert isinstance(cond_node, ConditionalNode)

        redhat_branch = cond_node.children[0]
        assert isinstance(redhat_branch, CaseBranchNode)
        assert redhat_branch.name == "RedHat"
        assert len(redhat_branch.children) == 1
        assert isinstance(redhat_branch.children[0], ClassNode)
        assert redhat_branch.children[0].name == "profile_app::redhat"

        debian_branch = cond_node.children[1]
        assert isinstance(debian_branch, CaseBranchNode)
        assert len(debian_branch.children) == 1
        assert isinstance(debian_branch.children[0], ClassNode)
        assert debian_branch.children[0].name == "profile_app::debian"

    def test_case_branch_with_multiple_resource_types(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="conditional",
                            condition="$env",
                            condition_type="case",
                            case_branches=[
                                CaseBranch(
                                    pattern="production",
                                    items=[
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="package",
                                            title="nginx",
                                        ),
                                        NestedExecutionItem(
                                            type="exported_resource",
                                            resource_type="nagios_host",
                                            title="web01",
                                        ),
                                        NestedExecutionItem(
                                            type="virtual_resource",
                                            resource_type="user",
                                            title="deploy",
                                        ),
                                        NestedExecutionItem(
                                            type="collector",
                                            resource_type="Nagios_host",
                                            query="tag == production",
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        branch = root.children[0].children[0]
        assert isinstance(branch, CaseBranchNode)
        assert len(branch.children) == 4
        assert isinstance(branch.children[0], ResourceNode)
        assert isinstance(branch.children[1], ExportedResourceNode)
        assert isinstance(branch.children[2], VirtualResourceNode)
        assert isinstance(branch.children[3], CollectorNode)

    def test_case_format_tree_output(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    execution_order=[
                        ExecutionItem(
                            type="conditional",
                            condition="$::osfamily",
                            condition_type="case",
                            case_branches=[
                                CaseBranch(
                                    pattern="RedHat",
                                    items=[
                                        NestedExecutionItem(
                                            type="resource",
                                            resource_type="package",
                                            title="httpd",
                                        ),
                                    ],
                                ),
                                CaseBranch(
                                    pattern="default",
                                    items=[],
                                    note="Unsupported OS",
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        output = builder.format_tree(root)

        assert "[conditional] case" in output
        assert "[branch] RedHat" in output
        assert "[branch] default" in output
        assert "[resource] package[httpd]" in output
