import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import ansiblelint
from ansiblelint import config as ansible_config
from ansiblelint.__main__ import fix
from ansiblelint.app import get_app
from ansiblelint.config import Options
from ansiblelint.errors import MatchError
from ansiblelint.rules import BaseRule, RulesCollection
from ansiblelint.runner import LintResult, get_matches
from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from tools.base_tool import X2ATool

logger = get_logger(__name__)

ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE = (
    "All files pass linting checks, no ansible-lint issues found."
)
CRITICAL_RULE_IDS = ["load-failure", "syntax-check", "parser-error", "internal-error"]
SYNTAX_ERROR_RULES = CRITICAL_RULE_IDS[:3]  # Subset for legacy _run() method
# yaml[line-length] is intentionally skipped: generated Ansible frequently
# contains long lines (embedded templates, URLs, long module arguments) that are
# not worth wrapping and would otherwise flood the report with low-value noise.
DEFAULT_SKIP_RULES = ["yaml[line-length]"]
# "all" enables every transformable rule during autofix. ansible-lint only
# applies a transform when its rule id/tag is in write_list, so this is what
# actually turns autofixing on. Non-transformable rules are unaffected and still
# reported for manual handling.
AUTOFIX_WRITE_LIST = ["all"]
ERROR_PATH_NOT_EXISTS = "ERROR: Path '{path}' does not exist."
ERROR_PATH_NOT_DIRECTORY = "ERROR: Path '{path}' must be a directory, not a file."
ERROR_ANSIBLE_LINT_NOT_INSTALLED = (
    "ERROR: ansible-lint is not installed. Install it with: uv add ansible-lint."
)
ERROR_RUNNING_ANSIBLE_LINT = "ERROR: running ansible-lint:\n```{error}```"


@dataclass(frozen=True)
class LintClassification:
    """Classification of ansible-lint matches by severity."""

    critical_matches: list[MatchError]
    warning_matches: list[MatchError]

    @property
    def has_critical_errors(self) -> bool:
        return len(self.critical_matches) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warning_matches) > 0

    @property
    def is_clean(self) -> bool:
        return not self.has_critical_errors and not self.has_warnings

    @property
    def all_matches(self) -> list[MatchError]:
        return self.critical_matches + self.warning_matches


class MatchClassifier:
    """Classifies ansible-lint matches into critical errors vs warnings."""

    @staticmethod
    def classify(matches: list[MatchError]) -> LintClassification:
        critical = [m for m in matches if m.rule.id in CRITICAL_RULE_IDS]
        warnings = [m for m in matches if m.rule.id not in CRITICAL_RULE_IDS]
        return LintClassification(critical_matches=critical, warning_matches=warnings)


class AnsibleLintInput(BaseModel):
    """Input schema for Ansible linting tool."""

    ansible_path: str = Field(
        description="Path to a directory containing Ansible files to lint"
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
            skip_list=DEFAULT_SKIP_RULES,
        )
        # get_app() (rather than constructing App directly) runs
        # runtime.prepare_environment()/enable_plugin_loader(), which installs
        # the AnsibleCollectionFinder. Without it, ansible-lint fails with
        # "an AnsibleCollectionFinder has not been installed in this process".
        app = get_app(offline=True, cached=False)
        rules = RulesCollection(app=app, rulesdirs=[rules_dir], options=options)
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
        """Format help for a rule: why it matters plus how to suppress it."""
        return (
            f"{IssueFormatter._rule_help_body(rule)}\n"
            f"{IssueFormatter._suppression_hint(rule.id)}"
        )

    @staticmethod
    def _rule_help_body(rule: BaseRule) -> str:
        """Explain why a rule matters and how to fix it.

        Prefers the concise curated help in tools/lint/{rule_id}.md, falling
        back to ansible-lint's own shortdesc/description/help.
        """
        # Convert hyphens to underscores for the filename
        rule_filename = rule.id.replace("-", "_")
        custom_help_path = Path(__file__).parent / "lint" / f"{rule_filename}.md"

        if custom_help_path.exists():
            try:
                # Custom help already includes title, just return it
                return custom_help_path.read_text().strip()
            except OSError:
                pass

        # Fallback to default ansible-lint help
        parts = [f"[{rule.id}] {rule.shortdesc}"]

        if getattr(rule, "description", None):
            parts.append(f"  Description: {rule.description}")

        if getattr(rule, "help", None):
            parts.append(f"\n{rule.help}")

        return "\n".join(parts)

    @staticmethod
    def _suppression_hint(rule_id: str) -> str:
        """Describe how to suppress a rule when the finding is intentional."""
        return (
            f"  To suppress (only when the finding is a false positive or "
            f"deliberate): add `# noqa: {rule_id} - <reason>` on the offending "
            f"line, or add '{rule_id}' to the ansible-lint skip_list."
        )

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
        cls,
        matches: list[MatchError],
        prefix: str = "",
        base_path: str = "",
        fixed_count: int = 0,
    ) -> str:
        """Format ansible-lint matches into a human-readable string with rule hints.

        When ``fixed_count`` is positive, the report leads with how many issues
        were auto-fixed so the reader can tell what was resolved automatically
        versus what still needs manual attention.
        """
        issues = [cls.format_issue(match, base_path) for match in matches]

        lines: list[str] = []
        if fixed_count > 0:
            lines.append(f"Automatically fixed {fixed_count} issue(s).")
            default_header = f"Found {len(matches)} ansible-lint issue(s) that require manual changes:"
        else:
            default_header = f"Found {len(matches)} ansible-lint issue(s):"
        lines.append(prefix if prefix else default_header)
        lines.extend(issues)
        result = "\n".join(lines)

        # Add rule hints section at the end
        unique_rules = cls.collect_unique_rules(matches)
        if unique_rules:
            result += "\n\n" + "=" * 30
            result += "\nRule Hints (How to Fix or Suppress):\n"
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


class _InternalErrorRule(BaseRule):
    """Rule stub for path-validation errors in lint_and_classify."""

    id = "internal-error"
    severity = "VERY_HIGH"
    version_changed = "1.0.0"

    def __init__(self, description: str):
        self._shortdesc = description
        self.description = description
        super().__init__()


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
    args_schema: ArgsSchema | None = AnsibleLintInput
    DEBUG_LOG_ARGS: ClassVar[list[str]] = ["ansible_path"]

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

    def _lint_fresh(self) -> tuple[LintConfiguration, LintResult]:
        """Create a fresh configuration and run ansible-lint.

        Each pass needs its own LintConfiguration: ansible-lint mutates the
        Options/RulesCollection state while applying fixes, so reusing them
        across passes yields stale results. Centralizing the create-then-run
        pair here keeps every call site consistent.
        """
        config = LintConfiguration.create()
        return config, self._run_lint(config)

    def _apply_fixes(self, config: LintConfiguration, result: LintResult) -> None:
        """Apply ansible-lint fixes to issues.

        ansible-lint's fix() decides which transforms to apply from the global
        ``ansiblelint.config.options.write_list`` singleton -- not from the
        Options we pass as runtime_options. So enabling autofix means mutating
        that global. We set it to AUTOFIX_WRITE_LIST around the fix() call and
        restore the previous value afterwards to avoid leaking global state
        across invocations. (Lint calls are already serialized in the exporter,
        see FLPATH-4915, so this mutation is safe against concurrent runs.)
        """
        previous_write_list = ansible_config.options.write_list
        ansible_config.options.write_list = AUTOFIX_WRITE_LIST
        try:
            fix(runtime_options=config.options, result=result, rules=config.rules)
        finally:
            ansible_config.options.write_list = previous_write_list

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
        config, result = self._lint_fresh()

        if not result.matches:
            self.log.info(f"No issues found for '{ansible_path}'")
            return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

        before_count = len(result.matches)
        self.log.debug(f"Found {before_count} matches, attempting fixes")
        self._apply_fixes(config, result)

        _, result = self._lint_fresh()
        fixed_count = max(before_count - len(result.matches), 0)

        if not result.matches:
            self.log.info(
                f"All {fixed_count} issue(s) fixed for '{ansible_path}'"
                if fixed_count
                else f"No issues found after fixes for '{ansible_path}'"
            )
            if fixed_count:
                return (
                    f"Automatically fixed {fixed_count} issue(s). "
                    f"{ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE}"
                )
            return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

        self.log.info(
            f"After fixes, {len(result.matches)} match(es) remain ({fixed_count} fixed)"
        )
        return IssueFormatter.format_issues(
            result.matches, base_path=base_path, fixed_count=fixed_count
        )

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
            # Broad by design: this is an LLM tool whose contract is to always
            # return a string. ansible-lint internals raise a wide, unstable set
            # of exception types, so any failure is reported to the agent rather
            # than propagated. The exception type is included to aid debugging.
            self.log.error(f"Error running ansible-lint: {e!s}")
            return f"ERROR: running ansible-lint ({type(e).__name__}):\n```{e!s}```"

    def _execute_linting_workflow(
        self, ansible_path: str, base_path: str, autofix: bool
    ) -> str:
        """Execute the linting workflow with appropriate strategy based on autofix setting."""
        _, result = self._lint_fresh()

        if not result.matches:
            self.log.info(f"No issues found for '{ansible_path}'")
            return ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE

        if self._has_syntax_errors(result):
            return self._handle_syntax_errors(result, base_path)

        if not autofix:
            return self._handle_no_autofix(result, base_path)

        return self._perform_lint_and_fix_cycle(ansible_path, base_path)

    def lint_and_classify(self, ansible_path: str) -> LintClassification:
        """Lint and return a structured classification instead of a string.

        Used by AnsibleLintValidator for severity-based acceptance.
        The existing _run() method is unchanged (LLM tool contract).
        """
        self.log.info(f"lint_and_classify in {ansible_path}")

        try:
            is_valid, error_message = PathValidator.validate(ansible_path)
            if not is_valid:
                assert error_message is not None
                error_rule = _InternalErrorRule(error_message)
                error_match = MatchError(message=error_message, rule=error_rule)
                return LintClassification(
                    critical_matches=[error_match], warning_matches=[]
                )

            absolute_path = Path(ansible_path).resolve()
            with change_directory(absolute_path):
                return self._classify_linting_workflow(ansible_path)

        except ImportError:
            self.log.error("ansible-lint is not installed")
            error_rule = _InternalErrorRule(ERROR_ANSIBLE_LINT_NOT_INSTALLED)
            error_match = MatchError(
                message=ERROR_ANSIBLE_LINT_NOT_INSTALLED, rule=error_rule
            )
            return LintClassification(
                critical_matches=[error_match], warning_matches=[]
            )
        except Exception as e:
            # Broad by design: callers rely on a LintClassification rather than
            # a raised exception, so any ansible-lint failure is surfaced as a
            # critical internal-error match (see the module _run docstring).
            error_msg = ERROR_RUNNING_ANSIBLE_LINT.format(error=str(e))
            self.log.error(f"Error running ansible-lint: {e!s}")
            error_rule = _InternalErrorRule(error_msg)
            error_match = MatchError(message=error_msg, rule=error_rule)
            return LintClassification(
                critical_matches=[error_match], warning_matches=[]
            )

    def _classify_linting_workflow(self, ansible_path: str) -> LintClassification:
        """Run lint with autofix, then classify remaining matches."""
        config, result = self._lint_fresh()

        if not result.matches:
            self.log.info(f"No issues found for '{ansible_path}'")
            return LintClassification(critical_matches=[], warning_matches=[])

        classification = MatchClassifier.classify(result.matches)

        if classification.has_critical_errors:
            self.log.warning(
                f"Found {len(classification.critical_matches)} critical error(s), skipping autofix"
            )
            return classification

        self.log.debug(f"Found {len(result.matches)} matches, attempting fixes")
        self._apply_fixes(config, result)

        _, result = self._lint_fresh()

        if not result.matches:
            self.log.info(f"All issues fixed for '{ansible_path}'")
            return LintClassification(critical_matches=[], warning_matches=[])

        self.log.info(f"After fixes, {len(result.matches)} matches remain")
        return MatchClassifier.classify(result.matches)
