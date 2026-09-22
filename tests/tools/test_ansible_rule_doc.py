"""Tests for the ansible_rule_doc tool."""

from src.exporters.tools.apme import ApmeRuleDoc
from tools.ansible_rule_doc import AnsibleRuleDocTool


def test_returns_markdown_for_known_rule(monkeypatch):
    doc = ApmeRuleDoc("R114", documentation="Description")
    monkeypatch.setattr(
        ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, _rule_id: doc)
    )

    result = AnsibleRuleDocTool()._run("R114")

    assert result == "### R114\n\nDescription"


def test_returns_available_rules_for_unknown_rule(monkeypatch):
    monkeypatch.setattr(
        ApmeRuleDoc, "from_rule_id", classmethod(lambda cls, _rule_id: None)
    )
    monkeypatch.setattr(
        "tools.ansible_rule_doc.list_rules_with_guidance",
        lambda: ["L039", "R114"],
    )

    result = AnsibleRuleDocTool()._run("UNKNOWN")

    assert result == (
        "No documentation found for rule 'UNKNOWN'. "
        "Rules with AI-remediation guidance: L039, R114"
    )
