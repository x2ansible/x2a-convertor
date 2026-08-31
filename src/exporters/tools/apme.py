"""APME (Ansible Playbook Migration Engine) integration.

Provides native Python access to APME's formatting, validation, and rule documentation
without subprocess calls.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from apme_engine.cli.output import deduplicate_violations, sort_violations
from apme_engine.formatter import (
    FormatResult,
    format_directory,
    format_file,
)
from apme_engine.graph.content_graph import ContentGraph
from apme_engine.graph.scanner import (
    GraphScanReport,
    filter_noqa_violations,
    graph_report_to_violations,
    load_graph_rules,
    native_rules_dir,
    scan,
)
from apme_engine.opa_client import OpaInfrastructureError
from apme_engine.rule_catalog import get_rule_documentation, get_rule_guidance
from apme_engine.runner import run_scan
from apme_engine.validators.opa import OpaValidator

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Rule IDs excluded from every APME check run in this project, regardless of
# environment. Keep this list short and documented -- it is a project-wide
# policy decision, not a per-run/per-user toggle.
#
# L079 (role variable prefix): x2a-generated roles already namespace
# variables per the write-agent's own conventions; this rule fires too many
# false positives against migrated content that intentionally keeps upstream
# variable names for compatibility.
EXCLUDED_RULE_IDS: list[str] = [
    "L079",
    "L060",
    "L040",
    "L042",
]


@dataclass
class FormatReport:
    """Summary of formatting operations.

    Attributes:
        files_checked: Total files examined.
        files_changed: Files that were reformatted.
        results: Detailed results per file.
    """

    files_checked: int = 0
    files_changed: int = 0
    results: list[FormatResult] = field(default_factory=list)

    def summary(self) -> str:
        """Return a human-readable summary."""
        if self.files_changed == 0:
            return f"All {self.files_checked} file(s) already formatted."
        return f"Reformatted {self.files_changed}/{self.files_checked} file(s)."


@dataclass
class ApmeRuleDoc:
    """Documentation and remediation guidance for a single APME rule.

    Attributes:
        rule_id: Rule identifier (e.g. R114, L039, M006).
        documentation: Rule description with pass/fail examples, or None if
            the catalog has no documentation for this rule.
        guidance: AI-remediation guidance (when to fix vs. justify a noqa),
            or None if the catalog has no guidance for this rule.
    """

    rule_id: str
    documentation: str | None = None
    guidance: str | None = None

    @classmethod
    def from_rule_id(cls, rule_id: str) -> "ApmeRuleDoc | None":
        """Build an ApmeRuleDoc by looking up a rule ID in APME's catalog.

        Returns:
            ApmeRuleDoc, or None if the catalog has neither documentation
            nor guidance for this rule ID.
        """
        documentation = get_rule_documentation(rule_id)
        guidance = get_rule_guidance(rule_id)

        if documentation is None and guidance is None:
            return None

        return cls(rule_id=rule_id, documentation=documentation, guidance=guidance)

    def to_markdown(self) -> str:
        """Render this rule's documentation as Markdown.

        Used by the ``ansible_rule_doc`` tool for interactive, single-rule
        lookups during the agent's react loop -- Markdown reads better than
        XML for that one-off, human/LLM-readable display.

        Format:
            ### R114

            ...documentation body, examples...

            **Remediation guidance:**

            ...guidance...
        """
        sections = [f"### {self.rule_id}"]
        if self.documentation:
            sections.append(self.documentation)
        if self.guidance:
            sections.append(f"**Remediation guidance:**\n\n{self.guidance}")
        return "\n\n".join(sections)

    def to_xml_prompt(self) -> str:
        """Render this rule's documentation as XML for an LLM prompt.

        Used to pre-populate the ValidationAgent's fix-errors prompt with
        docs for every rule in a CheckReport (see
        ``CheckReport.get_errors_doc()``) -- XML keeps unambiguous
        boundaries when many rules' docs are concatenated together inside
        a larger prompt.

        Format:
            <rule id="R114">
              <documentation>...markdown body, examples...</documentation>
              <remediation_guidance>...</remediation_guidance>
            </rule>
        """
        lines = [f"<rule id={quoteattr(self.rule_id)}>"]
        if self.documentation:
            lines.append(
                f"  <documentation>{escape(self.documentation)}</documentation>"
            )
        if self.guidance:
            lines.append(
                f"  <remediation_guidance>{escape(self.guidance)}</remediation_guidance>"
            )
        lines.append("</rule>")
        return "\n".join(lines)

    @staticmethod
    def render_all(docs: Iterable["ApmeRuleDoc"]) -> str:
        """Render a collection of rule docs as one XML block for a prompt.

        Format:
            <rule_documentation>
              <rule id="R114">...</rule>
              <rule id="L039">...</rule>
            </rule_documentation>

        Returns a self-closing `<rule_documentation/>` when `docs` is empty.
        """
        docs = list(docs)
        if not docs:
            return "<rule_documentation/>"

        body = "\n".join(doc.to_xml_prompt() for doc in docs)
        return f"<rule_documentation>\n{body}\n</rule_documentation>"


@dataclass
class CheckViolation:
    """A single validation violation.

    Attributes:
        rule_id: Rule identifier (e.g., L021, R108).
        severity: Violation severity (error, warning, info).
        message: Human-readable violation description.
        file: File path where the violation occurred.
        line: Line number(s) of the violation.
        scope: Rule scope (task, play, role, etc.).
    """

    rule_id: str
    severity: str
    message: str
    file: str
    line: int | list[int] | None = None
    scope: str = "task"


@dataclass
class CheckReport:
    """Summary of validation checks.

    Attributes:
        violations: List of detected violations.
        rules_evaluated: Number of rules that were evaluated.
        nodes_scanned: Number of graph nodes scanned.
        elapsed_ms: Time spent scanning in milliseconds.
    """

    violations: list[CheckViolation] = field(default_factory=list)
    rules_evaluated: int = 0
    nodes_scanned: int = 0
    elapsed_ms: float = 0.0

    @classmethod
    def from_violation_dicts(
        cls,
        violation_dicts: list[dict],
        *,
        content_graph: ContentGraph | None,
        rules_evaluated: int = 0,
        nodes_scanned: int = 0,
        elapsed_ms: float = 0.0,
    ) -> "CheckReport":
        """Build a CheckReport from raw validator violation dicts.

        Applies the same post-fan-out steps the APME gRPC daemon applies
        before returning a scan result (see ``engine_server.py``'s
        ``FixSession`` handler and ``apme check``'s own CLI post-processing
        in ``apme_engine.cli.check``): drop violations suppressed by inline
        ``# noqa: <rule_id>`` comments via ``filter_noqa_violations()``, then
        sort and deduplicate identical (rule, file, line) hits via the same
        ``apme_engine.cli.output.sort_violations`` /
        ``deduplicate_violations`` helpers the CLI uses -- reused rather than
        reimplemented here so this stays in sync with upstream apme_engine
        changes instead of drifting from a hand-rolled copy. Without the
        noqa step, in-process callers like ``AnsibleRoleCheckTool`` would
        report ``# noqa``-suppressed violations that the ``apme check`` CLI
        correctly hides.

        Args:
            violation_dicts: Merged violation dicts from all rule sources.
            content_graph: ContentGraph used to resolve ``# noqa:`` comments
                by node id (``path`` key on each violation dict).
            rules_evaluated: Number of rules that were evaluated.
            nodes_scanned: Number of graph nodes scanned.
            elapsed_ms: Time spent scanning in milliseconds.

        Returns:
            CheckReport with noqa-filtered, deduplicated violations.
        """
        filtered = filter_noqa_violations(violation_dicts, content_graph)
        deduped = deduplicate_violations(sort_violations(filtered))
        violations = [
            CheckViolation(
                rule_id=str(v.get("rule_id", "")),
                severity=str(v.get("severity", "warning")),
                message=str(v.get("message", "")),
                file=str(v.get("file", "")),
                line=cls._normalize_line(v.get("line")),
                scope=str(v.get("scope", "task")),
            )
            for v in deduped
        ]
        return cls(
            violations=violations,
            rules_evaluated=rules_evaluated,
            nodes_scanned=nodes_scanned,
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _normalize_line(line: object) -> int | list[int] | None:
        """Normalize a raw violation dict's line value to int, list[int], or None."""
        if line is None:
            return None
        if isinstance(line, int):
            return line
        if isinstance(line, list):
            return [int(x) for x in line if isinstance(x, int | float)]
        return None

    @property
    def has_violations(self) -> bool:
        """Return True if any violations were found."""
        return len(self.violations) > 0

    @property
    def error_count(self) -> int:
        """Count of error-level violations."""
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        """Count of warning-level violations."""
        return sum(1 for v in self.violations if v.severity == "warning")

    def distinct_rule_ids(self) -> list[str]:
        """Return the sorted, deduplicated rule IDs across all violations."""
        return sorted({v.rule_id for v in self.violations})

    def get_errors_doc(self) -> list[ApmeRuleDoc]:
        """Return documentation for every distinct rule ID in this report.

        Used to pre-populate a fix-errors prompt with docs for every rule
        reported in the current check, so the agent has remediation
        guidance and pass/fail examples on its very first turn instead of
        needing a round of ``ansible_rule_doc`` tool calls before it can
        start fixing anything.

        Returns:
            One ApmeRuleDoc per distinct rule ID that has documentation or
            guidance in the catalog (rule IDs without either are skipped).
        """
        return [
            doc
            for rule_id in self.distinct_rule_ids()
            if (doc := ApmeRuleDoc.from_rule_id(rule_id)) is not None
        ]

    def summary(self) -> str:
        """Return a human-readable summary."""
        if not self.violations:
            return f"No violations found ({self.nodes_scanned} nodes scanned)."
        return (
            f"Found {len(self.violations)} violation(s): "
            f"{self.error_count} error(s), {self.warning_count} warning(s)."
        )

    def to_xml_prompt(self) -> str:
        """Return violations as XML grouped by file path, for LLM prompts.

        XML gives unambiguous, machine-parseable boundaries between the
        report's own structure (file paths, per-violation rule/line/severity)
        and arbitrary text inside violation messages or downstream rule
        documentation/YAML examples that get concatenated after this report
        in a prompt -- unlike Markdown headers (`###`) or `---` separators,
        which can collide with headings or YAML document markers that
        legitimately appear inside that other content.

        Format:
            <apme_check_results total="2" errors="0" warnings="0">
              <file path="tasks/nginx.yml">
                <violation line="46" rule="R114" severity="medium">A file change with parameterized path found</violation>
                <violation line="46" rule="L017" severity="low">Avoid relative path in src</violation>
              </file>
            </apme_check_results>
        """
        if not self.violations:
            return '<apme_check_results total="0" errors="0" warnings="0"/>'

        # Group violations by file
        by_file: dict[str, list[CheckViolation]] = {}
        for v in self.violations:
            file_path = self._relative_path(v.file)
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(v)

        lines = [
            f'<apme_check_results total="{len(self.violations)}" '
            f'errors="{self.error_count}" warnings="{self.warning_count}">'
        ]

        for file_path in sorted(by_file.keys()):
            lines.append(f"  <file path={quoteattr(file_path)}>")
            file_violations = sorted(
                by_file[file_path], key=lambda v: self._sort_key(v)
            )
            for v in file_violations:
                line_str = self._format_line(v.line).removeprefix("L")
                lines.append(
                    f"    <violation line={quoteattr(line_str)} "
                    f"rule={quoteattr(v.rule_id)} "
                    f"severity={quoteattr(v.severity)}>"
                    f"{escape(v.message)}</violation>"
                )
            lines.append("  </file>")

        lines.append("</apme_check_results>")

        return "\n".join(lines)

    @staticmethod
    def _relative_path(file_path: str) -> str:
        """Convert absolute path to relative path from cwd."""
        if not file_path:
            return "<unknown>"
        try:
            return str(Path(file_path).relative_to(Path.cwd()))
        except ValueError:
            return file_path

    @staticmethod
    def _format_line(line: int | list[int] | None) -> str:
        """Format line number(s) for display."""
        if line is None:
            return "L?"
        if isinstance(line, list):
            return f"L{line[0]}" if line else "L?"
        return f"L{line}"

    @staticmethod
    def _sort_key(v: CheckViolation) -> int:
        """Return sort key for ordering violations by line number."""
        if v.line is None:
            return 0
        if isinstance(v.line, list):
            return v.line[0] if v.line else 0
        return v.line


class APME:
    """APME integration for Ansible content validation and formatting.

    Provides native Python access to:
    - format(): YAML formatting with Ansible-specific normalization
    - check(): Graph-based rule evaluation for Ansible best practices
    - get_rule_doc(): Rule documentation + remediation guidance lookup

    Example:
        apme = APME()
        report = apme.format("/path/to/ansible/role")
        if report.files_changed:
            print(f"Reformatted {report.files_changed} files")

        check_report = apme.check("/path/to/ansible/role")
        for violation in check_report.violations:
            print(f"{violation.rule_id}: {violation.message}")

        rule_doc = apme.get_rule_doc("R114")
    """

    def __init__(self) -> None:
        """Initialize APME instance."""
        self._rules_dir = native_rules_dir()

    def format(
        self,
        path: str | Path,
        *,
        apply: bool = True,
        exclude_patterns: list[str] | None = None,
    ) -> FormatReport:
        """Format Ansible YAML files with APME's formatter.

        Applies Ansible-specific YAML normalization:
        - Task key ordering (name first, then action, then metadata)
        - Jinja2 spacing normalization ({{ var }} style)
        - Tab-to-space conversion
        - Task list blank line insertion
        - Name capitalization
        - Inline key=value expansion to YAML dict form

        Args:
            path: File or directory to format.
            apply: If True, write changes to disk. If False, dry-run only.
            exclude_patterns: Glob patterns to exclude (e.g., ["vendor/*"]).

        Returns:
            FormatReport with summary and per-file results.
        """
        path = Path(path).resolve()
        slog = logger.bind(path=str(path), apply=apply)

        if not path.exists():
            slog.warning("Path does not exist")
            return FormatReport()

        if path.is_file():
            results = [format_file(path)]
        else:
            results = format_directory(path, exclude_patterns=exclude_patterns)

        files_changed = 0
        for result in results:
            if result.changed:
                files_changed += 1
                if apply:
                    result.path.write_text(result.formatted, encoding="utf-8")
                    slog.debug("Formatted file", file=str(result.path))

        report = FormatReport(
            files_checked=len(results),
            files_changed=files_changed,
            results=results,
        )

        slog.info(report.summary())
        return report

    def check(
        self,
        path: str | Path,
        *,
        rule_ids: list[str] | None = None,
        exclude_rule_ids: list[str] | None = None,
        include_test_contents: bool = True,
        include_opa_rules: bool = True,
    ) -> CheckReport:
        """Run APME validation checks on Ansible content.

        Combines two of the same rule sources `apme check` uses: the native
        graph-based scanner (structural rules like duplicate keys, role
        variable prefixing) and the OPA/Rego rule bundle (style/best-practice
        rules like preferring `command` over `shell`, avoiding `lineinfile`).
        `rule_ids`/`exclude_rule_ids` filtering applies to both sources.

        Unlike the `apme` CLI (which drives a full gRPC daemon pipeline that
        also includes ansible-risk-insight, secret scanning, and dependency
        health checks), this only runs the two rule sources above -- no
        daemon, and OPA evaluation needs a local `opa` binary or Podman
        (see `apme_engine.opa_client`). If neither is available, OPA rules
        are skipped and only native rules are reported.

        Args:
            path: File or directory to check.
            rule_ids: If provided, only run these specific rules.
            exclude_rule_ids: Rule IDs to skip, in addition to this project's
                static `EXCLUDED_RULE_IDS`. Defaults to `EXCLUDED_RULE_IDS`
                when not provided.
            include_test_contents: Include test directories (e.g. `molecule/`)
                in the scan. Defaults to True -- molecule playbooks go through
                the same rules as the rest of the role (see R114 on
                variable-built paths in converge.yml/verify.yml).
            include_opa_rules: Also evaluate the OPA/Rego rule bundle, in
                addition to native graph rules. Silently skipped (with a
                warning) if OPA is unavailable in this environment.

        Returns:
            CheckReport with violations and scan statistics.
        """
        path = Path(path).resolve()
        slog = logger.bind(path=str(path))

        if not path.exists():
            slog.warning("Path does not exist")
            return CheckReport()

        excluded = sorted(set(EXCLUDED_RULE_IDS) | set(exclude_rule_ids or []))

        # Run the engine scanner to build the content graph
        slog.debug("Running APME scan")
        context = run_scan(
            target_path=str(path),
            project_root=str(path) if path.is_dir() else str(path.parent),
            include_scandata=True,
            include_test_contents=include_test_contents,
        )

        # Load and filter graph rules
        rules, _ = load_graph_rules(
            rules_dir=self._rules_dir,
            rule_id_list=rule_ids,
            exclude_rule_ids=excluded,
        )

        # Get the content graph from scandata
        scandata = context.scandata
        if scandata is None or not hasattr(scandata, "content_graph"):
            slog.warning("No content graph available from scan")
            return CheckReport()

        content_graph = scandata.content_graph
        if content_graph is None:
            slog.warning("Content graph is None")
            return CheckReport()

        # Run graph-based rule evaluation
        slog.debug("Running graph rule evaluation", rules_count=len(rules))
        graph_report: GraphScanReport = scan(content_graph, rules, owned_only=True)

        # Convert to violation dicts
        violation_dicts = graph_report_to_violations(graph_report)

        if include_opa_rules:
            violation_dicts += self._run_opa_rules(context, rule_ids, excluded, slog)

        # Same post-fan-out steps the `apme check` gRPC daemon applies:
        # drop inline-suppressed violations, then dedupe.
        report = CheckReport.from_violation_dicts(
            violation_dicts,
            content_graph=content_graph,
            rules_evaluated=graph_report.rules_evaluated,
            nodes_scanned=graph_report.nodes_scanned,
            elapsed_ms=graph_report.elapsed_ms,
        )

        slog.info(report.summary())
        return report

    @staticmethod
    def get_rule_doc(rule_id: str) -> ApmeRuleDoc | None:
        """Look up documentation and remediation guidance for one rule ID.

        Args:
            rule_id: Rule identifier reported by check() (e.g. R114, L039).

        Returns:
            ApmeRuleDoc, or None if the catalog has no documentation or
            guidance for this rule ID.
        """
        return ApmeRuleDoc.from_rule_id(rule_id)

    @staticmethod
    def _run_opa_rules(
        context, rule_ids: list[str] | None, excluded: list[str], slog
    ) -> list[dict]:
        """Run the OPA/Rego rule bundle and return filtered violation dicts.

        Returns an empty list (with a warning logged) if OPA is unavailable
        in this environment (no `opa` binary or Podman) -- OPA evaluation is
        a best-effort addition, never a hard requirement for `check()`.
        """
        try:
            opa_violations = OpaValidator().run(context)
        except (OpaInfrastructureError, FileNotFoundError, OSError) as e:
            slog.warning(f"OPA rule evaluation unavailable, skipping: {e}")
            return []
        except Exception as e:
            slog.warning(f"OPA rule evaluation failed, skipping: {e}")
            return []

        filtered = [v for v in opa_violations if v.get("rule_id") not in excluded]
        if rule_ids is not None:
            filtered = [v for v in filtered if v.get("rule_id") in rule_ids]
        return filtered
