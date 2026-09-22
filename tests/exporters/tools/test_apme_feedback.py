"""Coverage for APME prompt rendering and tool boundary behavior."""

from unittest.mock import MagicMock

from src.exporters.tools.apme import ApmeRuleDoc, CheckReport, CheckViolation
from tools.ansible_role_check import AnsibleRoleCheckTool
from tools.ansible_rule_doc import AnsibleRuleDocTool


def test_rule_doc_xml_escapes_and_render_all_empty():
    doc = ApmeRuleDoc('R"1', "Use <the> & documented form.", 'Fix "this" & that.')
    assert doc.to_xml_prompt() == (
        "<rule id='R\"1'>\n"
        "  <documentation>Use &lt;the&gt; &amp; documented form.</documentation>\n"
        '  <remediation_guidance>Fix "this" &amp; that.</remediation_guidance>\n'
        "</rule>"
    )
    assert ApmeRuleDoc.render_all([]) == "<rule_documentation/>"


def test_check_report_xml_groups_escapes_and_maps_role_scope():
    report = CheckReport(
        violations=[
            CheckViolation("L027", "warning", "Use <role> & vars", "", 3, "role"),
            CheckViolation("L018", "error", 'Bad "path"', "tasks/a&b.yml", None),
        ]
    )
    rendered = report.to_xml_prompt()
    assert '<file path="meta/main.yml">' in rendered
    assert '<file path="tasks/a&amp;b.yml">' in rendered
    assert "Use &lt;role&gt; &amp; vars" in rendered
    assert 'line="?"' in rendered


def test_relative_path_and_error_docs(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert (
        CheckReport._relative_path(str(tmp_path / "tasks/main.yml")) == "tasks/main.yml"
    )
    assert (
        CheckReport._relative_path("tasks/main.yml", base_dir=tmp_path / "role")
        == "role/tasks/main.yml"
    )
    assert CheckReport._relative_path("") == "<unknown>"
    assert CheckReport._relative_path("", "role") == "meta/main.yml"

    docs = {"L017": ApmeRuleDoc("L017", documentation="one"), "R114": None}
    monkeypatch.setattr(
        ApmeRuleDoc,
        "from_rule_id",
        classmethod(lambda cls, rule_id: docs.get(rule_id)),
    )
    report = CheckReport(
        violations=[
            CheckViolation("R114", "warning", "x", "a"),
            CheckViolation("L017", "warning", "x", "a"),
            CheckViolation("L017", "warning", "y", "b"),
        ]
    )
    assert report.get_errors_doc() == [docs["L017"]]


def test_rule_doc_tool_happy_path_and_missing_doc(monkeypatch):
    tool = AnsibleRuleDocTool()
    doc = ApmeRuleDoc("R1", documentation="Description")
    monkeypatch.setattr(ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, _: doc))
    assert "### R1" in tool._run("R1")

    monkeypatch.setattr(ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, _: None))
    monkeypatch.setattr(
        "tools.ansible_rule_doc.list_rules_with_guidance", lambda: ["R1"]
    )
    assert "No documentation found" in tool._run("UNKNOWN")


def test_role_check_tool_missing_and_happy_path(tmp_path):
    tool = AnsibleRoleCheckTool()
    missing = tmp_path / "missing"
    assert "does not exist" in tool._run(str(missing))

    role = tmp_path / "role"
    role.mkdir()
    report = MagicMock(has_violations=False)
    tool._apme.check = MagicMock(return_value=report)
    assert "passed" in tool._run(str(role))
