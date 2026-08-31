"""Ansible role structure/rule checking tool backed by APME.

Delegates to ``src.exporters.tools.apme.APME.check()``, the same native
graph-based scanner that powers the standalone ``apme check`` CLI, so the
LLM agents get identical rule coverage (best-practice lint rules, risk
rules, modernization rules, etc.) without shelling out to a subprocess.
"""

from pathlib import Path

from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from src.exporters.tools.apme import APME
from src.utils.logging import get_logger
from tools.base_tool import X2ATool

logger = get_logger(__name__)

ANSIBLE_ROLE_CHECK_SUCCESS_MESSAGE = "APME check passed: no violations found."


class AnsibleRoleCheckInput(BaseModel):
    """Input schema for the Ansible role check tool."""

    ansible_role_path: str = Field(
        description="Path to Ansible role directory or file to check (e.g., './ansible/nginx-multisite')"
    )


class AnsibleRoleCheckTool(X2ATool):
    """Tool to check an Ansible role against APME's rule catalog.

    Runs the same native graph-based scanner as ``apme check``: best-practice
    lint rules, risk rules (e.g. privilege escalation, mutable file paths),
    and modernization rules. Returns an XML report of violations grouped
    by file, or a success message when the role is clean.

    Use ``ansible_rule_doc`` to look up remediation guidance for a specific
    rule ID reported here (e.g. how to fix or justify a ``noqa`` for R114).
    """

    name: str = "ansible_role_check"
    description: str = (
        "Checks an Ansible role or file against APME's rule catalog (the same "
        "engine behind `apme check`): best-practice lint rules, risk rules "
        "(e.g. privilege escalation, mutable file paths from variables), and "
        "modernization rules. Returns violations grouped by file with rule "
        "IDs (as XML), or confirmation that no violations were found. Use "
        "`ansible_rule_doc` on a reported rule ID for remediation guidance."
    )
    args_schema: ArgsSchema | None = AnsibleRoleCheckInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._apme = APME()

    # pyrefly: ignore
    def _run(self, ansible_role_path: str) -> str:
        """Check the Ansible role/file against APME rules."""
        path = Path(ansible_role_path)
        self.log.debug(f"AnsibleRoleCheckTool checking {ansible_role_path}")

        if not path.exists():
            return f"ERROR: Role path '{ansible_role_path}' does not exist"

        try:
            report = self._apme.check(path)
        except Exception as e:
            self.log.error(f"Unexpected error checking '{ansible_role_path}': {e}")
            return f"ERROR: Unexpected error running APME check:\n```\n{e}\n```"

        if not report.has_violations:
            self.log.info(f"'{ansible_role_path}' passed APME check")
            return ANSIBLE_ROLE_CHECK_SUCCESS_MESSAGE

        self.log.info(
            f"'{ansible_role_path}' has {len(report.violations)} APME violation(s)"
        )
        return report.to_xml_prompt()
