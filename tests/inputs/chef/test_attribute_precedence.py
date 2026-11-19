from pathlib import Path
from unittest.mock import Mock

import pytest

from src.inputs.chef.analyzer import ChefSubagent
from src.inputs.chef.execution_tree_builder import ExecutionTreeBuilder
from src.inputs.chef.models import (
    CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER,
    AttributeAssignment,
    AttributesAnalysisResult,
    ChefAttributePrecedence,
    ChefAttributesOutput,
    ChefAttributeWrite,
    RecipeAnalysisResult,
    RecipeExecutionAnalysis,
    StructuredAnalysis,
)
from src.inputs.chef.path_resolver import ChefPathResolver
from src.inputs.tree_analysis import TreeSitterAnalyzer
from src.types.file_analysis_state import FileAnalysisState


def _attribute_file(file_path: str, **values) -> AttributesAnalysisResult:
    assignments = list(values.get("assignments", []))
    if "assignments" not in values:
        for precedence in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER:
            level_values = values.get(f"{precedence.value}_attributes", {})
            assignments.extend(
                ChefAttributeWrite(
                    precedence=precedence,
                    attribute_path=[key],
                    value=value,
                )
                for key, value in level_values.items()
            )
    return AttributesAnalysisResult(
        file_path=file_path,
        analysis=ChefAttributesOutput(assignments=assignments),
    )


def test_tree_sitter_marks_bang_attribute_assignment(tmp_path: Path) -> None:
    attribute_file = tmp_path / "precedence.rb"
    attribute_file.write_text("force_default!['app']['service'] = {'workers' => 4}\n")

    result = TreeSitterAnalyzer().parse_file(str(attribute_file))

    assert "error" not in result
    assignment = result["chef_attributes"][0]
    assert assignment.precedence == "force_default"
    assert assignment.clears_precedence is True


def test_automatic_is_a_chef_level_but_not_a_cookbook_merge_level() -> None:
    assignment = AttributeAssignment(
        attribute_path="node.automatic['app']['port']",
        precedence="automatic",
        value=8080,
    )

    assert assignment.precedence is ChefAttributePrecedence.AUTOMATIC
    assert "automatic" not in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER


def test_unclassified_assignment_does_not_default_to_chef_precedence() -> None:
    assignment = AttributeAssignment(
        attribute_path="node['app']['port']",
        value=8080,
    )

    assert assignment.precedence is None
    assert assignment.format_label() == ("[attribute] node['app']['port'] = 8080")


def test_merges_attribute_values_by_exact_precedence_level() -> None:
    attributes = StructuredAnalysis(
        attributes=[
            _attribute_file(
                "cookbooks/app/attributes/default.rb",
                default_attributes={
                    "app": {
                        "tags": ["base", "shared"],
                        "config": {"base": True, "setting": "default"},
                    }
                },
                force_default_attributes={
                    "app": {
                        "tags": ["forced", "shared"],
                        "config": {"forced": True, "setting": "force_default"},
                    }
                },
                normal_attributes={
                    "app": {
                        "tags": ["normal"],
                        "config": {"normal": True, "setting": "normal"},
                    }
                },
                override_attributes={
                    "app": {
                        "tags": ["override"],
                        "config": {"override": True, "setting": "override"},
                    }
                },
                force_override_attributes={
                    "app": {
                        "tags": ["force_override"],
                        "config": {
                            "force_override": True,
                            "setting": "force_override",
                        },
                    }
                },
            ),
            _attribute_file(
                "cookbooks/app/attributes/web.rb",
                default_attributes={
                    "app": {
                        "tags": ["extra", "shared"],
                        "config": {"second_default": True},
                    }
                },
                override_attributes={"app": {"tags": ["override_extra", "override"]}},
            ),
        ]
    )

    assert attributes.merged_attribute_values() == {
        "app": {
            "tags": ["force_override"],
            "config": {
                "second_default": True,
                "forced": True,
                "normal": True,
                "force_override": True,
                "setting": "force_override",
            },
        }
    }


def test_later_array_assignment_replaces_same_level_value() -> None:
    attributes = StructuredAnalysis(
        attributes=[
            _attribute_file(
                "cookbooks/app/attributes/default.rb",
                default_attributes={"app": {"tags": ["base", "shared"]}},
            ),
            _attribute_file(
                "cookbooks/app/attributes/web.rb",
                default_attributes={"app": {"tags": ["extra", "shared"]}},
            ),
        ]
    )

    assert attributes.merged_attribute_values() == {
        "app": {"tags": ["extra", "shared"]}
    }


def test_attribute_summary_keeps_file_and_precedence() -> None:
    analysis = StructuredAnalysis(
        attributes=[
            _attribute_file(
                "cookbooks/app/attributes/web.rb",
                override_attributes={"app": {"port": 8443}},
            )
        ]
    )

    summary = analysis.format_attribute_summary()

    assert "cookbooks/app/attributes/web.rb [override]" in summary
    assert '"port": 8443' in summary


def test_bang_reset_is_path_scoped_and_keeps_higher_precedence_values() -> None:
    analysis = StructuredAnalysis(
        attributes=[
            _attribute_file(
                "cookbooks/app/attributes/default.rb",
                default_attributes={
                    "app": {
                        "name": "base",
                        "sites": {
                            "main": {"port": 80, "root": "/srv/main"},
                            "docs": {"port": 8080},
                        },
                    }
                },
            ),
            _attribute_file(
                "cookbooks/app/attributes/precedence.rb",
                assignments=[
                    ChefAttributeWrite(
                        precedence="force_default",
                        attribute_path=["app", "sites"],
                        value={"legacy": {"port": 9000}},
                    ),
                    ChefAttributeWrite(
                        precedence="force_default",
                        attribute_path=["app", "sites"],
                        value={"main": {"port": 8001}},
                        clears_precedence=True,
                    ),
                ],
            ),
            _attribute_file(
                "cookbooks/app/attributes/zz_override.rb",
                override_attributes={"app": {"sites": {"api": {"port": 9000}}}},
            ),
        ]
    )
    builder = ExecutionTreeBuilder(analysis, ChefPathResolver(), [])

    assert any(
        assignment.clears_precedence
        for assignment in analysis.attributes[1].analysis.assignments
    )
    assert analysis.merged_attribute_values() == {
        "app": {
            "name": "base",
            "sites": {"main": {"port": 8001}, "api": {"port": 9000}},
        }
    }
    assert builder._get_collection_attributes("app.sites") == {
        "main": {"port": 8001},
        "api": {"port": 9000},
    }
    assert '[force_default!] app.sites = {"main": {"port": 8001}}' in (
        analysis.format_attribute_summary()
    )


def test_bang_reset_summary_includes_authoritative_effective_values() -> None:
    analysis = StructuredAnalysis(
        attributes=[
            _attribute_file(
                "cookbooks/app/attributes/default.rb",
                default_attributes={"app": {"service": {"workers": 2, "timeout": 30}}},
            ),
            _attribute_file(
                "cookbooks/app/attributes/precedence.rb",
                assignments=[
                    ChefAttributeWrite(
                        precedence="force_default",
                        attribute_path=["app", "service"],
                        value={"workers": 4},
                        clears_precedence=True,
                    )
                ],
            ),
        ]
    )

    summary = analysis.format_attribute_summary()
    effective_values = summary.split(
        "COOKBOOK ATTRIBUTE VALUES BY ANSIBLE TARGET:\n", 1
    )[1]

    assert analysis.merged_attribute_values() == {"app": {"service": {"workers": 4}}}
    assert '"timeout"' not in effective_values
    assert '"workers": 4' in effective_values


def test_collection_lookup_uses_merged_precedence_values() -> None:
    analysis = StructuredAnalysis(
        attributes=[
            _attribute_file(
                "cookbooks/app/attributes/default.rb",
                default_attributes={
                    "app": {
                        "sites": {
                            "main": {"port": 80, "root": "/srv/www"},
                            "docs": {"port": 8080},
                        }
                    }
                },
                override_attributes={
                    "app": {"sites": {"main": {"port": 8443}, "api": {"port": 9000}}}
                },
            )
        ]
    )
    builder = ExecutionTreeBuilder(analysis, ChefPathResolver(), [])

    assert builder._get_collection_attributes("app.sites") == {
        "main": {"port": 8443, "root": "/srv/www"},
        "docs": {"port": 8080},
        "api": {"port": 9000},
    }


def test_attribute_assignment_label_includes_precedence_and_reset() -> None:
    assignment = AttributeAssignment(
        attribute_path="node.force_default['app']['port']",
        precedence="force_default",
        value=8080,
        clears_precedence=True,
    )

    assert assignment.format_label() == (
        "[attribute: force_default] node.force_default['app']['port'] = 8080 "
        "(clears precedence)"
    )


def test_execution_tree_displays_recipe_assignment_precedence() -> None:
    recipe_path = "cookbooks/app/recipes/default.rb"
    recipe = RecipeAnalysisResult(
        file_path=recipe_path,
        analysis=RecipeExecutionAnalysis(
            execution_order=[
                AttributeAssignment(
                    attribute_path="node.override['app']['port']",
                    precedence="override",
                    value=8443,
                )
            ]
        ),
    )
    builder = ExecutionTreeBuilder(
        StructuredAnalysis(recipes=[recipe]), ChefPathResolver(), []
    )

    tree = builder.build_tree(recipe_path)

    assert "[attribute: override]" in tree.children[0].format_label()


def test_attribute_discovery_includes_named_files_and_loads_default_first(
    tmp_path: Path,
) -> None:
    app_attributes = tmp_path / "cookbooks" / "app" / "attributes"
    app_attributes.mkdir(parents=True)
    for filename in ("z_platform.rb", "default.rb", "10_web.rb"):
        (app_attributes / filename).write_text("# attributes\n")

    def analyze_attribute_file(state: FileAnalysisState) -> FileAnalysisState:
        return state.update(
            result=ChefAttributesOutput(
                assignments=[
                    ChefAttributeWrite(
                        precedence="default",
                        attribute_path=["app", "source_file"],
                        value=Path(state.path).stem,
                    )
                ]
            )
        )

    analyzer = object.__new__(ChefSubagent)
    results = analyzer._analyze_files_by_pattern(
        paths=[tmp_path / "cookbooks"],
        pattern="**/attributes/*.rb",
        file_type="attributes",
        analysis_service=analyze_attribute_file,
        result_class=AttributesAnalysisResult,
        slog=Mock(),
        sort_key=ChefSubagent._attribute_file_sort_key,
    )

    assert [Path(item.file_path).name for item in results] == [
        "default.rb",
        "10_web.rb",
        "z_platform.rb",
    ]
    assert [item.analysis.assignments[0].value for item in results] == [
        "default",
        "10_web",
        "z_platform",
    ]


class TestChefAttributeResolution:
    @pytest.mark.parametrize(
        ("level", "retained"),
        [
            ("default", {"force_default", "normal", "override", "force_override"}),
            ("force_default", {"normal", "override", "force_override"}),
            ("normal", {"default", "force_default", "override", "force_override"}),
            ("override", {"default", "force_default", "normal", "force_override"}),
            ("force_override", {"default", "force_default", "normal"}),
        ],
    )
    def test_bang_resets_only_its_chef_component_group(self, level, retained):
        writes = [
            ChefAttributeWrite(
                precedence=precedence,
                attribute_path=["app", "settings"],
                value={precedence.value: True},
            )
            for precedence in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER
        ]
        writes.append(
            ChefAttributeWrite(
                precedence=level,
                attribute_path=["app", "settings"],
                value={"replacement": True},
                clears_precedence=True,
            )
        )
        analysis = StructuredAnalysis(
            attributes=[_attribute_file("attributes/default.rb", assignments=writes)]
        )

        assert analysis.merged_attribute_values() == {
            "app": {"settings": dict.fromkeys(retained | {"replacement"}, True)}
        }

    def test_repeated_hash_assignment_replaces_only_the_assigned_path(self):
        writes = [
            ChefAttributeWrite(
                precedence="default",
                attribute_path=["app"],
                value={"service": {"workers": 2, "timeout": 30}, "port": 80},
            ),
            ChefAttributeWrite(
                precedence="default",
                attribute_path=["app", "service"],
                value={"workers": 4},
            ),
        ]
        analysis = StructuredAnalysis(
            attributes=[_attribute_file("attributes/default.rb", assignments=writes)]
        )

        assert analysis.merged_attribute_values() == {
            "app": {"service": {"workers": 4}, "port": 80}
        }
        assert writes[0].value["service"]["workers"] == 2

    def test_later_lower_level_write_survives_an_earlier_force_bang(self):
        writes = [
            ChefAttributeWrite(
                precedence="force_default",
                attribute_path=["app"],
                value={"workers": 4},
                clears_precedence=True,
            ),
            ChefAttributeWrite(
                precedence="default",
                attribute_path=["app"],
                value={"timeout": 30},
            ),
        ]
        analysis = StructuredAnalysis(
            attributes=[_attribute_file("attributes/default.rb", assignments=writes)]
        )

        assert analysis.merged_attribute_values() == {
            "app": {"workers": 4, "timeout": 30}
        }

    def test_attribute_summary_contains_resolved_values_without_a_bang(self):
        analysis = StructuredAnalysis(
            attributes=[
                _attribute_file(
                    "cookbooks/app/attributes/default.rb",
                    default_attributes={
                        "app": {"service": {"workers": 2, "timeout": 30}}
                    },
                    override_attributes={"app": {"service": {"workers": 4}}},
                )
            ]
        )

        summary = analysis.format_attribute_summary()

        assert '"timeout": 30' in summary
        assert '"workers": 4' in summary
        assert "COOKBOOK ATTRIBUTE VALUES BY ANSIBLE TARGET" in summary
        assert "cookbooks/app/attributes/default.rb [override] app" in summary

    def test_target_groups_follow_assignments_across_files_and_bang_resets(self):
        analysis = StructuredAnalysis(
            attributes=[
                _attribute_file(
                    "attributes/base.rb",
                    default_attributes={
                        "worker": {
                            "port": 9000,
                            "service": {"workers": 2, "timeout": 30},
                            "database": "development",
                        }
                    },
                ),
                _attribute_file(
                    "attributes/deployment.rb",
                    assignments=[
                        ChefAttributeWrite(
                            precedence="force_default",
                            attribute_path=["worker", "port"],
                            value=9001,
                        ),
                        ChefAttributeWrite(
                            precedence="force_default",
                            attribute_path=["worker", "service"],
                            value={"workers": 6},
                            clears_precedence=True,
                        ),
                        ChefAttributeWrite(
                            precedence="force_override",
                            attribute_path=["worker", "database"],
                            value="production",
                        ),
                    ],
                ),
            ]
        )

        assert analysis.resolve_attributes().values_by_target() == {
            "defaults/main.yml": {"worker": {"port": 9001, "service": {"workers": 6}}},
            "vars/main.yml": {"worker": {"database": "production"}},
        }

    @pytest.mark.parametrize("level", ["normal", "override", "force_override"])
    def test_target_groups_keep_mixed_dictionaries_whole(self, level):
        analysis = StructuredAnalysis(
            attributes=[
                _attribute_file(
                    "attributes/base.rb",
                    assignments=[
                        ChefAttributeWrite(
                            precedence="default",
                            attribute_path=["worker"],
                            value={
                                "port": 9000,
                                "service": {"workers": 2, "timeout": 30},
                            },
                        ),
                        ChefAttributeWrite(
                            precedence=level,
                            attribute_path=["worker", "service", "workers"],
                            value=6,
                        ),
                    ],
                )
            ]
        )

        assert analysis.resolve_attributes().values_by_target() == {
            "defaults/main.yml": {"worker": {"port": 9000}},
            "vars/main.yml": {"worker": {"service": {"workers": 6, "timeout": 30}}},
        }

    def test_target_groups_preserve_scalar_roots_and_empty_dictionaries(self):
        analysis = StructuredAnalysis(
            attributes=[
                _attribute_file(
                    "attributes/base.rb",
                    default_attributes={
                        "feature_enabled": False,
                        "empty": {},
                        "name": "base",
                    },
                    override_attributes={"name": "production"},
                )
            ]
        )

        assert analysis.resolve_attributes().values_by_target() == {
            "defaults/main.yml": {"feature_enabled": False, "empty": {}},
            "vars/main.yml": {"name": "production"},
        }
