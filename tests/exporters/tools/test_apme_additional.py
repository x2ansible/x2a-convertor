"""Additional unit coverage for APME formatting, reporting, and orchestration."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from apme_engine.formatter import FormatResult
from apme_engine.opa_client import OpaInfrastructureError

from src.exporters.tools import apme
from src.exporters.tools.apme import APME, ApmeRuleDoc, CheckReport, CheckViolation
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.ansible_rule_doc import AnsibleRuleDocTool


def test_format_report_summary() -> None:
    assert apme.FormatReport().summary() == "All 0 file(s) already formatted."
    assert apme.FormatReport(files_checked=3, files_changed=2).summary() == (
        "Reformatted 2/3 file(s)."
    )


def test_rule_doc_rendering_all_optional_sections() -> None:
    assert ApmeRuleDoc("R1").to_markdown() == "### R1"
    assert ApmeRuleDoc("R1", documentation="docs").to_markdown() == "### R1\n\ndocs"
    assert ApmeRuleDoc("R1", guidance="fix it").to_markdown() == (
        "### R1\n\n**Remediation guidance:**\n\nfix it"
    )
    assert ApmeRuleDoc.render_all([ApmeRuleDoc("R1")]) == (
        '<rule_documentation>\n<rule id="R1">\n</rule>\n</rule_documentation>'
    )


def test_rule_doc_xml_handles_each_optional_section() -> None:
    assert ApmeRuleDoc("R1", documentation="<docs>").to_xml_prompt() == (
        '<rule id="R1">\n  <documentation>&lt;docs&gt;</documentation>\n</rule>'
    )
    assert ApmeRuleDoc("R1", guidance="use & fix").to_xml_prompt() == (
        '<rule id="R1">\n  <remediation_guidance>use &amp; fix</remediation_guidance>\n</rule>'
    )


def test_rule_doc_catalog_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apme, "get_rule_documentation", lambda _: "documentation")
    monkeypatch.setattr(apme, "get_rule_guidance", lambda _: "guidance")
    assert ApmeRuleDoc.from_rule_id("R1") == ApmeRuleDoc(
        "R1", "documentation", "guidance"
    )

    monkeypatch.setattr(apme, "get_rule_documentation", lambda _: None)
    monkeypatch.setattr(apme, "get_rule_guidance", lambda _: None)
    assert ApmeRuleDoc.from_rule_id("missing") is None


def test_normalize_line_accepts_supported_values_only() -> None:
    assert CheckReport._normalize_line(None) is None
    assert CheckReport._normalize_line(4) == 4
    assert CheckReport._normalize_line([1, 2.0, "3", True]) == [1, 2, 1]
    assert CheckReport._normalize_line("4") is None
    assert CheckReport._normalize_line({"line": 4}) is None


def test_check_report_helpers_and_xml_ordering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    report = CheckReport(
        violations=[
            CheckViolation("L2", "warning", "later", "b.yml", [8, 9]),
            CheckViolation("L1", "error", "first & <bad>", "a.yml", 2),
            CheckViolation("L3", "info", "unknown", "", None),
        ],
        nodes_scanned=4,
    )
    assert report.has_violations
    assert report.error_count == 1
    assert report.warning_count == 1
    assert report.distinct_rule_ids() == ["L1", "L2", "L3"]
    assert report.summary() == "Found 3 violation(s): 1 error(s), 1 warning(s)."
    rendered = report.to_xml_prompt()
    assert rendered.index('path="a.yml"') < rendered.index('path="b.yml"')
    assert 'line="2"' in rendered
    assert 'line="8"' in rendered
    assert 'path="&lt;unknown&gt;"' in rendered
    assert "first &amp; &lt;bad&gt;" in rendered
    assert CheckReport().to_xml_prompt() == (
        '<apme_check_results total="0" errors="0" warnings="0"/>'
    )
    assert CheckReport._format_line([]) == "L?"
    assert CheckReport._format_line([7, 8]) == "L7"
    assert CheckReport._sort_key(CheckViolation("x", "x", "x", "x", [])) == 0


def test_relative_paths_and_rule_docs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert (
        CheckReport._relative_path(str(tmp_path / "tasks/main.yml")) == "tasks/main.yml"
    )
    assert CheckReport._relative_path("tasks/main.yml", base_dir=tmp_path / "role") == (
        "role/tasks/main.yml"
    )
    assert CheckReport._relative_path("") == "<unknown>"
    assert CheckReport._relative_path("", "role") == "meta/main.yml"
    docs = {"L1": ApmeRuleDoc("L1"), "L2": None}
    monkeypatch.setattr(
        ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, rule: docs[rule])
    )
    report = CheckReport(
        [
            CheckViolation("L2", "warning", "", "x"),
            CheckViolation("L1", "warning", "", "x"),
        ]
    )
    assert report.get_errors_doc() == [docs["L1"]]


def test_format_skips_unchanged_results_and_applies_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "a.yml"
    target.write_text("original")
    unchanged = FormatResult(target, "original", "original", False)
    changed = FormatResult(target, "original", "updated", True)
    monkeypatch.setattr(apme, "format_file", lambda _: unchanged)
    assert APME().format(target).files_changed == 0
    monkeypatch.setattr(apme, "format_file", lambda _: changed)
    assert APME().format(target).files_changed == 1
    assert target.read_text() == "updated"


def test_format_missing_file_and_file_and_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    instance = APME()
    assert instance.format(tmp_path / "missing").files_checked == 0
    target = tmp_path / "a.yml"
    target.write_text("old")
    result = FormatResult(target, "old", "new", True)
    monkeypatch.setattr(apme, "format_file", lambda _: result)
    file_report = instance.format(target, apply=False)
    assert file_report.files_changed == 1
    assert target.read_text() == "old"
    monkeypatch.setattr(apme, "format_directory", lambda _, exclude_patterns: [result])
    directory_report = instance.format(tmp_path, exclude_patterns=["vendor/*"])
    assert directory_report.files_changed == 1
    assert (tmp_path / "a.yml").read_text() == "new"


def test_run_opa_rules_handles_all_infrastructure_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def validator_for(error: Exception):
        class BrokenValidator:
            def run(self, _context):
                raise error

        return BrokenValidator

    for error in (
        OpaInfrastructureError("unavailable"),
        FileNotFoundError("opa"),
        OSError("exec"),
    ):
        monkeypatch.setattr(apme, "OpaValidator", validator_for(error))
        assert APME._run_opa_rules(object(), None, [], MagicMock()) == []


def test_run_opa_rules_filters_and_handles_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Validator:
        def run(self, _context):
            return [{"rule_id": "L1"}, {"rule_id": "L2"}]

    monkeypatch.setattr(apme, "OpaValidator", Validator)
    assert APME._run_opa_rules(object(), ["L2"], ["L3"], MagicMock()) == [
        {"rule_id": "L2"}
    ]
    assert APME._run_opa_rules(object(), None, ["L1"], MagicMock()) == [
        {"rule_id": "L2"}
    ]

    class BrokenValidator:
        def run(self, _context):
            raise OpaInfrastructureError("unavailable")

    monkeypatch.setattr(apme, "OpaValidator", BrokenValidator)
    assert APME._run_opa_rules(object(), None, [], MagicMock()) == []

    class FailingValidator:
        def run(self, _context):
            raise RuntimeError("failed")

    monkeypatch.setattr(apme, "OpaValidator", FailingValidator)
    assert APME._run_opa_rules(object(), None, [], MagicMock()) == []


def test_check_orchestration_and_early_returns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    instance = APME()
    assert not instance.check(tmp_path / "missing").has_violations
    context = MagicMock()
    context.scandata = None
    monkeypatch.setattr(apme, "run_scan", lambda **_: context)
    assert not instance.check(tmp_path).has_violations
    context = object()
    monkeypatch.setattr(apme, "run_scan", lambda **_: context)
    assert not instance.check(tmp_path).has_violations
    context = MagicMock()
    context.scandata = MagicMock(content_graph=None)
    assert not instance.check(tmp_path).has_violations

    graph = MagicMock()
    context.scandata.content_graph = graph
    graph_report = MagicMock(rules_evaluated=2, nodes_scanned=3, elapsed_ms=4.5)
    monkeypatch.setattr(apme, "load_graph_rules", lambda **_: (["rule"], None))
    monkeypatch.setattr(apme, "scan", lambda *_args, **_kwargs: graph_report)
    monkeypatch.setattr(apme, "graph_report_to_violations", lambda _: [])
    monkeypatch.setattr(apme.APME, "_run_opa_rules", staticmethod(lambda *args: []))
    report = instance.check(
        tmp_path, rule_ids=["L1"], exclude_rule_ids=["L2"], include_opa_rules=False
    )
    assert report.rules_evaluated == 2
    assert report.nodes_scanned == 3
    assert report.elapsed_ms == 4.5


def test_rule_doc_tool_and_role_check_error_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    doc_tool = AnsibleRuleDocTool()
    monkeypatch.setattr(ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, _: None))
    monkeypatch.setattr(
        "tools.ansible_rule_doc.list_rules_with_guidance", lambda: ["R1"]
    )
    assert "R1" in doc_tool._run("missing")

    role = tmp_path / "role"
    role.mkdir()
    role_tool = AnsibleRoleCheckTool()
    role_tool._apme.check = MagicMock(side_effect=RuntimeError("boom"))
    assert "Unexpected error" in role_tool._run(str(role))

    report = CheckReport([CheckViolation("L1", "error", "bad", "tasks/main.yml", 4)])
    role_tool._apme.check = MagicMock(return_value=report)
    assert "apme_check_results" in role_tool._run(str(role))


def test_get_rule_doc_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = ApmeRuleDoc("R1")
    monkeypatch.setattr(ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, _: doc))
    assert APME.get_rule_doc("R1") is doc
