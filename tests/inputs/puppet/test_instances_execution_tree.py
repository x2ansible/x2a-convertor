"""Test that defined types (like redis::instance) are expanded in the execution tree."""

from src.inputs.puppet.execution_tree_builder import PuppetExecutionTreeBuilder
from src.inputs.puppet.models import (
    ExecutionItem,
    ManifestAnalysisResult,
    ManifestExecutionAnalysis,
    NestedExecutionItem,
    PuppetStructuredAnalysis,
)


def test_defined_type_expansion():
    """Test that defined types are expanded to show their execution order."""
    # Main class that uses a defined type
    main_class = ManifestAnalysisResult(
        file_path="manifests/init.pp",
        analysis=ManifestExecutionAnalysis(
            class_name="redis",
            execution_order=[
                # Loop that creates instances
                ExecutionItem(
                    type="iteration",
                    iterator_type="each",
                    collection_variable="$instances",
                    item_variable="$key",
                    execution_order=[
                        NestedExecutionItem(
                            type="resource",
                            resource_type="redis::instance",
                            title="$key",
                        )
                    ],
                )
            ],
        ),
    )

    # Defined type manifest
    instance_type = ManifestAnalysisResult(
        file_path="manifests/instance.pp",
        analysis=ManifestExecutionAnalysis(
            class_name="redis::instance",
            class_parameters={"port": "6379", "bind": "127.0.0.1"},
            execution_order=[
                ExecutionItem(
                    type="conditional",
                    condition_type="if",
                    condition="$log_dir != $redis::log_dir",
                    execution_order=[
                        NestedExecutionItem(
                            type="resource",
                            resource_type="file",
                            title="$log_dir",
                            attributes={"ensure": "directory"},
                        )
                    ],
                ),
                ExecutionItem(
                    type="resource",
                    resource_type="file",
                    title="$config_file",
                    attributes={"ensure": "file", "content": "template()"},
                ),
            ],
        ),
    )

    # Build the tree
    structured = PuppetStructuredAnalysis(
        manifests=[main_class, instance_type],
        hiera_data=[],
        templates=[],
        custom_types=[],
    )

    builder = PuppetExecutionTreeBuilder(structured, path_resolver=None)
    tree = builder.build_tree(entry_class="redis")

    # Format the tree
    formatted = builder.format_tree(tree)

    # Verify the tree structure
    assert "LOOP $instances.each |$key|" in formatted
    assert "[defined_type] redis::instance[$key]" in formatted
    assert "manifests/instance.pp" in formatted
    assert "2 parameters" in formatted

    # Most importantly: verify that the defined type's execution order is shown
    assert "[conditional] if $log_dir != $redis::log_dir" in formatted
    assert "[resource] file[$log_dir]" in formatted
    assert "[resource] file[$config_file]" in formatted

    print("\n" + formatted)


def test_defined_type_not_analyzed():
    """Test that undefined types are shown as regular resources when not analyzed."""
    main_class = ManifestAnalysisResult(
        file_path="manifests/init.pp",
        analysis=ManifestExecutionAnalysis(
            class_name="mymodule",
            execution_order=[
                ExecutionItem(
                    type="resource",
                    resource_type="unknown::type",
                    title="instance1",
                )
            ],
        ),
    )

    structured = PuppetStructuredAnalysis(
        manifests=[main_class], hiera_data=[], templates=[], custom_types=[]
    )

    builder = PuppetExecutionTreeBuilder(structured, path_resolver=None)
    tree = builder.build_tree(entry_class="mymodule")

    formatted = builder.format_tree(tree)

    # Should show as a regular resource (not expanded)
    assert "[resource] unknown::type[instance1]" in formatted
