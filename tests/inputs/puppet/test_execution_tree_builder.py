"""Tests for Puppet execution tree builder."""

from src.inputs.puppet.execution_tree_builder import (
    ExecutionTreeNode,
    PuppetExecutionTreeBuilder,
)
from src.inputs.puppet.models import (
    ClassInclude,
    ClassInheritance,
    ConditionalBlock,
    IterationBlock,
    ManifestAnalysisResult,
    ManifestExecutionAnalysis,
    PuppetResourceDeclaration,
    PuppetStructuredAnalysis,
)


def _make_manifest(class_name, file_path, **kwargs) -> ManifestAnalysisResult:
    return ManifestAnalysisResult(
        file_path=file_path,
        analysis=ManifestExecutionAnalysis(class_name=class_name, **kwargs),
    )


class TestExecutionTreeNode:
    def test_class_format(self):
        node = ExecutionTreeNode(
            node_type="class",
            name="profile_haproxy",
            file_path="manifests/init.pp",
        )
        label = node.format_label()
        assert "[class] profile_haproxy" in label
        assert "manifests/init.pp" in label

    def test_class_with_details(self):
        node = ExecutionTreeNode(
            node_type="class",
            name="profile_haproxy",
            file_path="manifests/init.pp",
            details="entry point",
        )
        label = node.format_label()
        assert "(entry point)" in label

    def test_resource_format(self):
        node = ExecutionTreeNode(node_type="resource", name="package[haproxy]")
        assert node.format_label() == "[resource] package[haproxy]"

    def test_iteration_format(self):
        node = ExecutionTreeNode(node_type="iteration", name="$backends.each |$name|")
        assert "LOOP" in node.format_label()

    def test_conditional_format(self):
        node = ExecutionTreeNode(node_type="conditional", name="if $ssl_enabled")
        assert "[conditional]" in node.format_label()

    def test_exported_format(self):
        node = ExecutionTreeNode(node_type="exported", name="nagios_host[web01]")
        assert "@@" in node.format_label()

    def test_virtual_format(self):
        node = ExecutionTreeNode(node_type="virtual", name="user[deploy]")
        assert "@" in node.format_label()

    def test_unknown_type_format(self):
        node = ExecutionTreeNode(node_type="unknown", name="something")
        assert node.format_label() == "something"

    def test_unknown_type_with_details(self):
        node = ExecutionTreeNode(node_type="unknown", name="something", details="extra")
        assert node.format_label() == "something (extra)"


class TestPuppetExecutionTreeBuilder:
    def test_simple_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "profile_haproxy",
                    "manifests/init.pp",
                    class_includes=[
                        ClassInclude(
                            class_name="profile_haproxy::install",
                            relationship="include",
                        ),
                    ],
                ),
                _make_manifest(
                    "profile_haproxy::install",
                    "manifests/install.pp",
                    resources=[
                        PuppetResourceDeclaration(
                            resource_type="package",
                            title="haproxy",
                            attributes={"ensure": "installed"},
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        assert root.name == "profile_haproxy"
        assert root.node_type == "class"
        assert len(root.children) == 1
        child = root.children[0]
        assert child.name == "profile_haproxy::install"
        assert len(child.children) == 1
        assert "package" in child.children[0].name

    def test_entry_class_detection_via_init_pp(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest("profile_haproxy::config", "manifests/config.pp"),
                _make_manifest("profile_haproxy", "manifests/init.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        assert root.name == "profile_haproxy"

    def test_entry_class_fallback_to_first(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest("profile_haproxy::config", "manifests/config.pp"),
                _make_manifest("profile_haproxy::install", "manifests/install.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        assert root.name == "profile_haproxy::config"

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
                    class_includes=[
                        ClassInclude(class_name="b", relationship="include"),
                    ],
                ),
                _make_manifest(
                    "b",
                    "manifests/b.pp",
                    class_includes=[
                        ClassInclude(class_name="a", relationship="include"),
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
                    class_includes=[
                        ClassInclude(
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
                    conditionals=[
                        ConditionalBlock(
                            condition="$ssl_enabled",
                            condition_type="if",
                            resources=[
                                PuppetResourceDeclaration(
                                    resource_type="file", title="/etc/ssl/cert.pem"
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        cond_nodes = [c for c in root.children if c.node_type == "conditional"]
        assert len(cond_nodes) == 1
        assert "ssl_enabled" in cond_nodes[0].name
        assert len(cond_nodes[0].children) == 1

    def test_iterations_in_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    iterations=[
                        IterationBlock(
                            iterator_type="each",
                            collection_variable="$backends",
                            item_variable="$name, $config",
                            resources=[
                                PuppetResourceDeclaration(
                                    resource_type="file", title="backend.cfg"
                                ),
                            ],
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        iter_nodes = [c for c in root.children if c.node_type == "iteration"]
        assert len(iter_nodes) == 1
        assert "$backends" in iter_nodes[0].name
        assert len(iter_nodes[0].children) == 1

    def test_exported_and_virtual_resources(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    exported_resources=[
                        PuppetResourceDeclaration(
                            resource_type="nagios_host", title="web01"
                        ),
                    ],
                    virtual_resources=[
                        PuppetResourceDeclaration(resource_type="user", title="deploy"),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        exported = [c for c in root.children if c.node_type == "exported"]
        virtual = [c for c in root.children if c.node_type == "virtual"]
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
                        "Package[haproxy] -> File[haproxy.cfg] ~> Service[haproxy]"
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        rel_nodes = [c for c in root.children if c.node_type == "relationship"]
        assert len(rel_nodes) == 1
        assert "Package[haproxy]" in rel_nodes[0].name

    def test_resource_details_extraction(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    resources=[
                        PuppetResourceDeclaration(
                            resource_type="file",
                            title="/etc/haproxy/haproxy.cfg",
                            attributes={
                                "ensure": "file",
                                "owner": "root",
                                "mode": "0640",
                            },
                        ),
                        PuppetResourceDeclaration(
                            resource_type="exec",
                            title="reload_config",
                            attributes={"command": "/usr/sbin/haproxy -c"},
                        ),
                    ],
                ),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()

        file_node = root.children[0]
        assert "ensure: file" in (file_node.details or "")
        exec_node = root.children[1]
        assert "command:" in (exec_node.details or "")


class TestFormatTree:
    def test_format_simple_tree(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "main",
                    "manifests/init.pp",
                    resources=[
                        PuppetResourceDeclaration(
                            resource_type="package", title="haproxy"
                        ),
                    ],
                    class_includes=[
                        ClassInclude(class_name="main::config", relationship="include"),
                    ],
                ),
                _make_manifest("main::config", "manifests/config.pp"),
            ]
        )
        builder = PuppetExecutionTreeBuilder(analysis)
        root = builder.build_tree()
        output = builder.format_tree(root)

        assert "[class] main" in output
        assert "[resource] package[haproxy]" in output
        assert "[class] main::config" in output
        assert "├── " in output or "└── " in output

    def test_format_deep_nesting(self):
        analysis = PuppetStructuredAnalysis(
            manifests=[
                _make_manifest(
                    "a",
                    "manifests/a.pp",
                    class_includes=[
                        ClassInclude(class_name="b", relationship="include")
                    ],
                ),
                _make_manifest(
                    "b",
                    "manifests/b.pp",
                    class_includes=[
                        ClassInclude(class_name="c", relationship="include")
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
