import os
from pathlib import Path
from typing import Any

import ansiblelint
from ansiblelint.__main__ import fix
from ansiblelint.config import Options
from ansiblelint.rules import RulesCollection
from ansiblelint.runner import get_matches
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE = (
    "All files pass linting checks, no ansible-lint issues found."
)


class AnsibleLintInput(BaseModel):
    """Input schema for Ansible linting tool."""

    ansible_path: str = Field(
        description="Path to a single Ansible file or a directory to lint"
    )
    autofix: bool = Field(
        default=True,
        description="Whether to automatically fix issues. Set to False to only report issues without fixing them.",
    )


class AnsibleLintTool(BaseTool):
    """Tool to lint Ansible files using ansible-lint."""

    name: str = "ansible_lint"
    description: str = (
        "Lints Ansible playbooks, roles, and task files using ansible-lint. "
        "Checks for best practices, syntax issues, and potential problems. "
        "Returns a list of issues found or confirmation that no issues were detected. "
        "Use autofix=true to automatically fix issues (default), or autofix=false to only report them. "
        "Setting autofix=false is recommended when fixing may introduce new issues."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleLintInput

    def _format_lint_issues(
        self, matches: list, prefix: str = "", base_path: str = ""
    ) -> str:
        """Format ansible-lint matches into a human-readable string.

        Args:
            matches: List of ansible-lint match objects
            prefix: Optional prefix message to add before the issue list
            base_path: Base path to prepend to relative filenames (makes paths absolute)

        Returns:
            Formatted string with all issues listed
        """
        issues: list[str] = []
        for match in matches:
            # If base_path provided, construct full path; otherwise use relative
            if base_path:
                full_path = os.path.join(base_path, match.filename)
            else:
                full_path = match.filename

            issue = f"{full_path}:{match.lineno or 0} [{match.rule.id}] {match.message}"
            issues.append(issue)

        if prefix:
            result = f"{prefix}\n"
        else:
            result = f"Found {len(matches)} ansible-lint issue(s):\n"
        result += "\n".join(issues)
        return result

    # pyrefly: ignore
    def _run(self, ansible_path: str, autofix: bool = True) -> str:
        """Lint Ansible files and report issues.

        Args:
            ansible_path: Path to Ansible directory to lint
            autofix: Whether to automatically fix issues (default: True)
        """
        logger.info(f"AnsibleLintTool in {ansible_path} (autofix={autofix})")

        try:
            path = Path(ansible_path)
            if not path.exists():
                logger.error(
                    f"AnsibleLintTool error: Path '{ansible_path}' does not exist"
                )
                return f"ERROR: Path '{ansible_path}' does not exist."

            if not path.is_dir():
                logger.error(
                    f"AnsibleLintTool error: Path '{ansible_path}' must be a directory, not a file"
                )
                return f"ERROR: Path '{ansible_path}' must be a directory, not a file."

            # Convert to absolute path to ensure ansible-lint works correctly
            # even when the current working directory is different
            absolute_path = path.resolve()

            # Keep the original relative path for error reporting
            # Normalize it by removing leading './'
            relative_base_path = ansible_path.lstrip("./")

            # Save current directory and change to the ansible directory
            # This ensures relative paths in lintables work correctly
            original_cwd = os.getcwd()
            try:
                os.chdir(absolute_path)
                logger.debug(
                    f"Changed directory to {absolute_path} for ansible-lint execution"
                )

                # Load all built-in rules from ansible-lint package
                rules_dir = os.path.join(os.path.dirname(ansiblelint.__file__), "rules")
                options = Options(
                    offline=True,  # Prevent external dependencies and ansible-config dump
                    lintables=["."],  # Use current directory since we changed to it
                    _skip_ansible_syntax_check=True,  # Skip ansible-playbook --syntax-check
                    skip_list=[
                        "yaml[line-length]"
                    ],  # Skip line length checks for auto-generated code
                )

                # all available rules
                rules = RulesCollection(rulesdirs=[rules_dir], options=options)

                # Run linter
                lintResult = get_matches(rules, options)

                if not lintResult.matches:
                    logger.info(f"No AnsibleLintTool issues found for '{ansible_path}'")
                    return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

                # Check for syntax errors (load-failure, syntax-check) that prevent fixing
                syntax_errors = [
                    match
                    for match in lintResult.matches
                    if match.rule.id in ["load-failure", "syntax-check", "parser-error"]
                ]

                ## If syntax_errors the autofix is not going to work, and the LLM get into a loop that does not know where it fails.
                if syntax_errors:
                    logger.warning(
                        f"Found {len(syntax_errors)} syntax error(s) that prevent auto-fixing"
                    )
                    # Format all issues with filename and line (including syntax errors)
                    prefix = f"Found {len(lintResult.matches)} ansible-lint issue(s) (including {len(syntax_errors)} syntax error(s)):"
                    return self._format_lint_issues(
                        lintResult.matches, prefix=prefix, base_path=relative_base_path
                    )

                # If autofix is disabled, return issues immediately without attempting to fix
                if not autofix:
                    logger.info(
                        f"Autofix disabled, returning {len(lintResult.matches)} issue(s) without fixing"
                    )
                    return self._format_lint_issues(
                        lintResult.matches, base_path=relative_base_path
                    )

                logger.debug(
                    f"AnsibleLintTool found {len(lintResult.matches)} matches, trying to fix them"
                )

                # Try to fix it
                fix(runtime_options=options, result=lintResult, rules=rules)

                # Re-run linter
                lintResult = get_matches(rules, options)

                if not lintResult.matches:
                    logger.info(
                        f"No AnsibleLintTool issues found for {ansible_path} after fixes"
                    )
                    return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

                logger.info(
                    f"After fixes, the AnsibleLintTool still found {len(lintResult.matches)} matches."
                )

                # Format issues after fixes with relative paths
                result = self._format_lint_issues(
                    lintResult.matches, base_path=relative_base_path
                )
                logger.debug(
                    f"AnsibleLintTool found {len(lintResult.matches)} ansible-lint issue(s) for {ansible_path}: {result}"
                )
                return result
            finally:
                # Always restore the original directory
                os.chdir(original_cwd)
                logger.debug(f"Restored directory to {original_cwd}")

        except ImportError:
            logger.error(
                "Error: ansible-lint is not installed. Install it with: uv add ansible-lint"
            )
            return "ERROR: ansible-lint is not installed. Install it with: uv add ansible-lint."
        except Exception as e:
            logger.error(f"Error running ansible-lint: {str(e)}")
            return f"ERROR: running ansible-lint:\n```{str(e)}```"
