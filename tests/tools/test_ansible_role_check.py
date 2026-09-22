"""Tests for the ansible_role_check tool."""

from unittest.mock import MagicMock

from src.exporters.tools.apme import CheckReport, CheckViolation
from tools.ansible_role_check import (
    ANSIBLE_ROLE_CHECK_SUCCESS_MESSAGE,
    AnsibleRoleCheckTool,
)


def test_missing_role_path_returns_error(tmp_path):
    result = AnsibleRoleCheckTool()._run(str(tmp_path / "missing"))

    assert result == f"ERROR: Role path '{tmp_path / 'missing'}' does not exist"


def test_clean_role_returns_success(tmp_path):
    role = tmp_path / "role"
    role.mkdir()
    tool = AnsibleRoleCheckTool()
    tool._apme.check = MagicMock(return_value=CheckReport())

    result = tool._run(str(role))

    assert result == ANSIBLE_ROLE_CHECK_SUCCESS_MESSAGE
    tool._apme.check.assert_called_once()


def test_violations_are_rendered_as_xml(tmp_path):
    role = tmp_path / "role"
    role.mkdir()
    report = CheckReport(
        violations=[
            CheckViolation(
                "L017", "warning", "Avoid relative path", "tasks/main.yml", 4
            )
        ]
    )
    tool = AnsibleRoleCheckTool()
    tool._apme.check = MagicMock(return_value=report)

    result = tool._run(str(role))

    assert '<apme_check_results total="1"' in result
    assert 'rule="L017"' in result
    assert "Avoid relative path" in result


def test_apme_errors_are_returned_as_tool_errors(tmp_path):
    role = tmp_path / "role"
    role.mkdir()
    tool = AnsibleRoleCheckTool()
    tool._apme.check = MagicMock(side_effect=RuntimeError("scanner failed"))

    result = tool._run(str(role))

    assert (
        result
        == "ERROR: Unexpected error running APME check:\n```\nscanner failed\n```"
    )
