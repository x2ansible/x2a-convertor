"""Tests for Chef analysis models."""

from src.inputs.chef.models import (
    CustomCodeAnalysis,
    CustomCodeAnalysisResult,
    StructuredAnalysis,
)


class TestCustomCodeAnalysis:
    def test_format_conversion_decision_not_convertible_with_reason(self):
        analysis = CustomCodeAnalysis(
            component_type="library",
            name="secret_helper",
            conversion_outcome="not_convertible",
            flag_reason="internal gem not present in source",
        )
        decision = analysis.format_conversion_decision()
        assert "NOT SAFELY CONVERTIBLE" in decision
        assert "internal gem not present in source" in decision

    def test_format_conversion_decision_not_convertible_without_reason(self):
        analysis = CustomCodeAnalysis(
            component_type="custom_resource",
            name="secret_setting",
            conversion_outcome="not_convertible",
        )
        decision = analysis.format_conversion_decision()
        assert "NOT SAFELY CONVERTIBLE" in decision
        assert "Reason" not in decision

    def test_format_conversion_decision_existing_modules(self):
        analysis = CustomCodeAnalysis(
            component_type="custom_resource", name="fetch_token"
        )
        assert analysis.format_conversion_decision() == (
            "  Conversion: existing Ansible modules"
        )


class TestCustomCodeAnalysisResult:
    def test_format_summary_includes_decision(self):
        result = CustomCodeAnalysisResult(
            file_path="cookbooks/app/libraries/helper.rb",
            analysis=CustomCodeAnalysis(
                component_type="library",
                name="helper",
                description="Fetches a token over HTTP",
                functions=[{"name": "fetch_token", "parameters": ["url"]}],
            ),
        )
        summary = result.format_summary()
        assert "library: helper" in summary
        assert "cookbooks/app/libraries/helper.rb" in summary
        assert "Fetches a token over HTTP" in summary
        assert "fetch_token" in summary
        assert "existing Ansible modules" in summary


class TestStructuredAnalysisCustomCode:
    def test_format_custom_code_summary_empty(self):
        analysis = StructuredAnalysis()
        assert (
            analysis.format_custom_code_summary()
            == "No custom resources or libraries detected."
        )

    def test_format_custom_code_summary_joins_results(self):
        analysis = StructuredAnalysis(
            custom_code=[
                CustomCodeAnalysisResult(
                    file_path="cookbooks/app/resources/ada.rb",
                    analysis=CustomCodeAnalysis(
                        component_type="custom_resource", name="ada"
                    ),
                ),
                CustomCodeAnalysisResult(
                    file_path="cookbooks/app/libraries/helper.rb",
                    analysis=CustomCodeAnalysis(
                        component_type="library", name="helper"
                    ),
                ),
            ]
        )
        summary = analysis.format_custom_code_summary()
        assert "custom_resource: ada" in summary
        assert "library: helper" in summary

    def test_custom_code_counts_in_totals_and_paths(self):
        analysis = StructuredAnalysis(
            custom_code=[
                CustomCodeAnalysisResult(
                    file_path="cookbooks/app/resources/ada.rb",
                    analysis=CustomCodeAnalysis(
                        component_type="custom_resource", name="ada"
                    ),
                )
            ]
        )
        assert analysis.get_total_files_analyzed() == 1
        assert "cookbooks/app/resources/ada.rb" in analysis.analyzed_file_paths
