import os
import logging
from pathlib import Path
from typing import Any

import ansiblelint
from ansiblelint.rules import RulesCollection
from ansiblelint.runner import Runner
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)


class AnsibleLintInput(BaseModel):
    """Input schema for Ansible linting tool."""

    ansible_path: str = Field(
        description="Path to a single Ansible file or a directory to lint"
    )


class AnsibleLintTool(BaseTool):
    """Tool to lint Ansible files using ansible-lint."""

    name: str = "ansible_lint"
    description: str = (
        "Lints Ansible playbooks, roles, and task files using ansible-lint. "
        "Checks for best practices, syntax issues, and potential problems. "
        "Returns a list of issues found or confirmation that no issues were detected."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleLintInput

    # pyrefly: ignore
    def _run(self, ansible_path: str) -> str:
        """Lint Ansible files and report issues."""
        logger.debug(f"AnsibleLintTool in {ansible_path}")

        try:
            path = Path(ansible_path)
            if not path.exists():
                logger.error(
                    f"AnsibleLintTool error: Path '{ansible_path}' does not exist"
                )
                return f"ERROR: Path '{ansible_path}' does not exist."

            # Load all built-in rules from ansible-lint package
            rules_dir = os.path.join(os.path.dirname(ansiblelint.__file__), "rules")
            rules = RulesCollection(rulesdirs=[rules_dir])

            # Run linter with all rules
            runner = Runner(str(path), rules=rules)
            matches = runner.run()

            if not matches:
                logger.debug(f"No AnsibleLintTool issues found for {ansible_path}")
                return "All files pass linting checks, no ansible-lint issues found."

            # Format issues
            issues: list[str] = []
            for match in matches:
                issue = (
                    f"{match.filename}:{match.lineno or 0} "
                    f"[{match.rule.id}] {match.message}"
                )
                issues.append(issue)

            result = f"Found {len(matches)} ansible-lint issue(s):\n\n"
            result += "\n".join(issues)
            logger.debug(
                f"AnsibleLintTool found {len(matches)} ansible-lint issue(s) for {ansible_path}: {result}"
            )
            return result

        except ImportError:
            logger.error(
                "Error: ansible-lint is not installed. Install it with: uv add ansible-lint"
            )
            return "ERROR: ansible-lint is not installed. Install it with: uv add ansible-lint."
        except Exception as e:
            logger.error(f"Error running ansible-lint: {str(e)}")
            return f"ERROR: running ansible-lint:\n```{str(e)}```"
