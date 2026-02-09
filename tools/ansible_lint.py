import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ansiblelint
from ansiblelint.__main__ import fix
from ansiblelint.config import Options
from ansiblelint.errors import MatchError
from ansiblelint.rules import BaseRule, RulesCollection
from ansiblelint.runner import LintResult, get_matches
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from tools.base_tool import X2ATool

logger = get_logger(__name__)

ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE = (
    "All files pass linting checks, no ansible-lint issues found."
)
SYNTAX_ERROR_RULES = ["load-failure", "syntax-check", "parser-error"]
ERROR_PATH_NOT_EXISTS = "ERROR: Path '{path}' does not exist."
ERROR_PATH_NOT_DIRECTORY = "ERROR: Path '{path}' must be a directory, not a file."
ERROR_ANSIBLE_LINT_NOT_INSTALLED = (
    "ERROR: ansible-lint is not installed. Install it with: uv add ansible-lint."
)
ERROR_RUNNING_ANSIBLE_LINT = "ERROR: running ansible-lint:\n```{error}```"


class AnsibleLintInput(BaseModel):
    """Input schema for Ansible linting tool."""

    ansible_path: str = Field(
        description="Path to a single Ansible file or a directory to lint"
    )
    autofix: bool = Field(
        default=True,
        description="Whether to automatically fix issues. Set to False to only report issues without fixing them.",
    )


@dataclass
class LintConfiguration:
    """Configuration for ansible-lint execution."""

    options: Options
    rules: RulesCollection

    @classmethod
    def create(cls) -> "LintConfiguration":
        """Create fresh Options and RulesCollection objects."""
        rules_dir = Path(ansiblelint.__file__).parent / "rules"
        options = Options(
            offline=True,
            lintables=["."],
            _skip_ansible_syntax_check=True,
            skip_list=["yaml[line-length]"],
        )
        rules = RulesCollection(rulesdirs=[rules_dir], options=options)
        return cls(options=options, rules=rules)


class IssueFormatter:
    """Formats ansible-lint issues into human-readable strings."""

    @staticmethod
    def format_issue(match: MatchError, base_path: str) -> str:
        """Format a single lint match into a string."""
        full_path = (
            str(Path(base_path) / match.filename) if base_path else match.filename
        )
        return f"[{match.rule.severity}] {full_path}:{match.lineno or 0} [{match.rule.id}] {match.message} ({match.details})"

    @staticmethod
    def format_rule_help(rule: BaseRule) -> str:
        """Format help information for a rule."""
        # Try to load custom concise help from tools/lint/{rule_id}.md
        # Convert hyphens to underscores for filename
        rule_filename = rule.id.replace("-", "_")
        custom_help_path = Path(__file__).parent / "lint" / f"{rule_filename}.md"

        if custom_help_path.exists():
            try:
                custom_help = custom_help_path.read_text()
                # Custom help already includes title, just return it
                return custom_help.strip()
            except Exception:
                pass

        # Fallback to default ansible-lint help
        parts = [f"[{rule.id}] {rule.shortdesc}"]

        if hasattr(rule, "description") and rule.description:
            parts.append(f"  Description: {rule.description}")

        if hasattr(rule, "help") and rule.help:
            parts.append(f"\n{rule.help}")

        return "\n".join(parts)

    @classmethod
    def collect_unique_rules(cls, matches: list) -> list:
        """Collect unique rules from matches, preserving order."""
        seen_rule_ids = set()
        unique_rules = []

        for match in matches:
            if match.rule.id not in seen_rule_ids:
                seen_rule_ids.add(match.rule.id)
                unique_rules.append(match.rule)
        return unique_rules

    @classmethod
    def format_issues(
        cls, matches: list[MatchError], prefix: str = "", base_path: str = ""
    ) -> str:
        """Format ansible-lint matches into a human-readable string with rule hints."""
        issues = [cls.format_issue(match, base_path) for match in matches]

        header = prefix if prefix else f"Found {len(matches)} ansible-lint issue(s):"
        result = f"{header}\n" + "\n".join(issues)

        # Add rule hints section at the end
        unique_rules = cls.collect_unique_rules(matches)
        if unique_rules:
            result += "\n\n" + "=" * 30
            result += "\nRule Hints (How to Fix):\n"
            result += "=" * 30 + "\n"
            rule_helps = [cls.format_rule_help(rule) for rule in unique_rules]
            result += "\n\n".join(rule_helps)

        return result


class PathValidator:
    """Validates paths for ansible-lint operations."""

    @staticmethod
    def validate(ansible_path: str) -> tuple[bool, str | None]:
        """Validate the provided path.

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        path = Path(ansible_path)

        if not path.exists():
            logger.error(f"Path '{ansible_path}' does not exist")
            return False, ERROR_PATH_NOT_EXISTS.format(path=ansible_path)

        if not path.is_dir():
            logger.error(f"Path '{ansible_path}' must be a directory, not a file")
            return False, ERROR_PATH_NOT_DIRECTORY.format(path=ansible_path)

        return True, None


@contextmanager
def change_directory(path: Path) -> Iterator[None]:
    """Context manager to temporarily change working directory."""
    original_cwd = Path.cwd()
    try:
        os.chdir(path)
        logger.debug(f"Changed directory to {path} for ansible-lint execution")
        yield
    finally:
        os.chdir(original_cwd)
        logger.debug(f"Restored directory to {original_cwd}")


class AnsibleLintTool(X2ATool):
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

    def _has_syntax_errors(self, result: LintResult) -> bool:
        """Check if lint result contains syntax errors."""
        return any(match.rule.id in SYNTAX_ERROR_RULES for match in result.matches)

    def _get_syntax_error_matches(self, result: LintResult) -> list:
        """Extract syntax error matches from lint result."""
        return [
            match for match in result.matches if match.rule.id in SYNTAX_ERROR_RULES
        ]

    def _run_lint(self, config: LintConfiguration) -> LintResult:
        """Execute ansible-lint with given configuration."""
        return get_matches(config.rules, config.options)

    def _apply_fixes(self, config: LintConfiguration, result: LintResult) -> None:
        """Apply ansible-lint fixes to issues."""
        fix(runtime_options=config.options, result=result, rules=config.rules)

    def _handle_syntax_errors(self, result: LintResult, base_path: str) -> str:
        """Handle lint results containing syntax errors."""
        syntax_errors = self._get_syntax_error_matches(result)
        self.log.warning(
            f"Found {len(syntax_errors)} syntax error(s) that prevent auto-fixing"
        )

        prefix = (
            f"Found {len(result.matches)} ansible-lint issue(s) "
            f"(including {len(syntax_errors)} syntax error(s)):"
        )
        return IssueFormatter.format_issues(
            result.matches, prefix=prefix, base_path=base_path
        )

    def _handle_no_autofix(self, result: LintResult, base_path: str) -> str:
        """Handle lint results when autofix is disabled."""
        self.log.info(
            f"Autofix disabled, returning {len(result.matches)} issue(s) without fixing"
        )
        return IssueFormatter.format_issues(result.matches, base_path=base_path)

    def _perform_lint_and_fix_cycle(self, ansible_path: str, base_path: str) -> str:
        """Execute the full lint-fix-verify cycle."""
        config = LintConfiguration.create()
        result = self._run_lint(config)

        if not result.matches:
            self.log.info(f"No issues found for '{ansible_path}'")
            return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

        self.log.debug(f"Found {len(result.matches)} matches, attempting fixes")
        self._apply_fixes(config, result)

        config = LintConfiguration.create()
        result = self._run_lint(config)

        if not result.matches:
            self.log.info(f"No issues found after fixes for '{ansible_path}'")
            return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

        self.log.info(f"After fixes, still found {len(result.matches)} matches")
        return IssueFormatter.format_issues(result.matches, base_path=base_path)

    # pyrefly: ignore
    def _run(self, ansible_path: str, autofix: bool = True) -> str:
        """Lint Ansible files and report issues.

        Args:
            ansible_path: Path to Ansible directory to lint
            autofix: Whether to automatically fix issues (default: True)
        """
        self.log.info(f"AnsibleLintTool in {ansible_path} (autofix={autofix})")

        try:
            is_valid, error_message = PathValidator.validate(ansible_path)
            if not is_valid:
                assert error_message is not None
                return error_message

            absolute_path = Path(ansible_path).resolve()
            relative_base_path = ansible_path.lstrip("./")

            with change_directory(absolute_path):
                return self._execute_linting_workflow(
                    ansible_path, relative_base_path, autofix
                )

        except ImportError:
            self.log.error("ansible-lint is not installed")
            return ERROR_ANSIBLE_LINT_NOT_INSTALLED
        except Exception as e:
            self.log.error(f"Error running ansible-lint: {e!s}")
            return f"ERROR: running ansible-lint:\n```{e!s}```"

    def _execute_linting_workflow(
        self, ansible_path: str, base_path: str, autofix: bool
    ) -> str:
        """Execute the linting workflow with appropriate strategy based on autofix setting."""
        config = LintConfiguration.create()
        result = self._run_lint(config)

        if not result.matches:
            self.log.info(f"No issues found for '{ansible_path}'")
            return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

        if self._has_syntax_errors(result):
            return self._handle_syntax_errors(result, base_path)

        if not autofix:
            return self._handle_no_autofix(result, base_path)

        return self._perform_lint_and_fix_cycle(ansible_path, base_path)
