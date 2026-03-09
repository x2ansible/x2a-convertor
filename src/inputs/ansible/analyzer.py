"""Ansible infrastructure analyzer.

This module implements the main AnsibleSubagent that orchestrates all
Ansible analysis. It composes services and BaseAgent subclasses as graph
nodes following the pattern from src/inputs/powershell/analyzer.py.
"""

from pathlib import Path
from typing import Literal

from langgraph.graph import END, StateGraph

from src.inputs.ansible.analysis_validation_agent import AnalysisValidationAgent
from src.inputs.ansible.cleanup_agent import CleanupAgent
from src.inputs.ansible.models import (
    AnsibleStructuredAnalysis,
    MetaAnalysisResult,
    TaskFileAnalysisResult,
    TemplateAnalysisResult,
    VariablesAnalysisResult,
)
from src.inputs.ansible.report_writer_agent import ReportWriterAgent
from src.inputs.ansible.services import (
    MetaAnalysisService,
    TaskFileAnalysisService,
    TemplateAnalysisService,
    VariablesAnalysisService,
)
from src.inputs.ansible.state import AnsibleAnalysisState
from src.model import get_model, get_runnable_config
from src.types import Telemetry
from src.utils.logging import get_logger

logger = get_logger(__name__)

YAML_EXTENSIONS = {".yml", ".yaml"}


class AnsibleSubagent:
    """Main Ansible analyzer - implements InfrastructureAnalyzer protocol.

    This class orchestrates all Ansible analysis using a LangGraph workflow.

    Workflow phases:
    1. scan_files - Scan for Ansible role files; classify by type
    2. analyze_structure - Use analysis services to analyze all files
    3. write_report - Generate migration plan using ReportWriterAgent
    4. validate_with_analysis - Validate plan using AnalysisValidationAgent
    5. cleanup_specification - Clean up using CleanupAgent
    """

    def __init__(self, model=None) -> None:
        self.model = model or get_model()

        self._task_service = TaskFileAnalysisService(self.model)
        self._vars_service = VariablesAnalysisService(self.model)
        self._meta_service = MetaAnalysisService(self.model)
        self._template_service = TemplateAnalysisService(self.model)

        self._report_writer = ReportWriterAgent(model=self.model)
        self._analysis_validator = AnalysisValidationAgent(model=self.model)
        self._cleanup = CleanupAgent(model=self.model)

        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_workflow(self):
        """Create LangGraph workflow composing agents as nodes."""
        workflow = StateGraph(AnsibleAnalysisState)

        workflow.add_node("scan_files", lambda state: self._scan_files(state))
        workflow.add_node(
            "analyze_structure", lambda state: self._analyze_structure(state)
        )
        workflow.add_node("write_report", self._report_writer)
        workflow.add_node("validate_with_analysis", self._analysis_validator)
        workflow.add_node("cleanup_specification", self._cleanup)

        workflow.set_entry_point("scan_files")
        workflow.add_edge("scan_files", "analyze_structure")
        workflow.add_edge("analyze_structure", "write_report")
        workflow.add_conditional_edges(
            "write_report",
            self._check_failure_after_agent,
            {"continue": "validate_with_analysis", "failed": END},
        )
        workflow.add_conditional_edges(
            "validate_with_analysis",
            self._check_failure_after_agent,
            {"continue": "cleanup_specification", "failed": END},
        )
        workflow.add_edge("cleanup_specification", END)

        return workflow.compile()

    def _check_failure_after_agent(
        self, state: AnsibleAnalysisState
    ) -> Literal["continue", "failed"]:
        """Conditional edge: check if agent failed."""
        if state.failed:
            logger.error(f"Agent failed: {state.failure_reason}")
            return "failed"
        return "continue"

    def _scan_files(self, state: AnsibleAnalysisState) -> AnsibleAnalysisState:
        """Scan for Ansible role files and classify them."""
        slog = logger.bind(phase="scan_files")
        slog.info(f"Scanning for Ansible role files in {state.path}")

        base_path = Path(state.path)

        # Check for role structure
        tasks_dir = base_path / "tasks"
        if not tasks_dir.exists():
            slog.warning("No tasks/ directory found - not an Ansible role")
            return state.mark_failed(
                "No tasks/ directory found in the repository. "
                "Expected an Ansible role structure."
            )

        # Parse existing collection dependencies
        collection_deps = self._parse_requirements(base_path, slog)

        slog.info(
            f"Found Ansible role structure at {base_path}, "
            f"{len(collection_deps)} collection dependencies"
        )

        return state.update(collection_dependencies=collection_deps)

    def _parse_requirements(self, base_path: Path, slog) -> list[str]:
        """Parse requirements.yml for existing collection dependencies."""
        deps: list[str] = []

        for req_path in [
            base_path / "requirements.yml",
            base_path / "collections" / "requirements.yml",
        ]:
            if req_path.exists():
                try:
                    import yaml

                    content = yaml.safe_load(req_path.read_text())
                    if isinstance(content, dict):
                        for col in content.get("collections", []):
                            if isinstance(col, dict) and "name" in col:
                                deps.append(col["name"])
                            elif isinstance(col, str):
                                deps.append(col)
                    slog.info(
                        f"Found {len(deps)} collection dependencies in {req_path}"
                    )
                except Exception as e:
                    slog.warning(f"Failed to parse {req_path}: {e}")

        return deps

    def _analyze_structure(
        self, state: AnsibleAnalysisState
    ) -> AnsibleAnalysisState:
        """Analyze all Ansible role files using analysis services."""
        slog = logger.bind(phase="analyze_structure")
        slog.info("Starting structured analysis of Ansible role files")

        base_path = Path(state.path)

        # Analyze tasks
        tasks_files = self._analyze_yaml_files(
            base_path / "tasks", "tasks", slog
        )

        # Analyze handlers
        handlers_files = self._analyze_yaml_files(
            base_path / "handlers", "handlers", slog
        )

        # Analyze defaults
        defaults_files = self._analyze_vars_files(
            base_path / "defaults", "defaults", slog
        )

        # Analyze vars
        vars_files = self._analyze_vars_files(
            base_path / "vars", "vars", slog
        )

        # Analyze meta
        meta = self._analyze_meta(base_path / "meta", slog)

        # Analyze templates
        templates = self._analyze_templates(base_path / "templates", slog)

        # Collect static files
        static_files = self._collect_static_files(base_path / "files", slog)

        structured_analysis = AnsibleStructuredAnalysis(
            tasks_files=tasks_files,
            handlers_files=handlers_files,
            defaults_files=defaults_files,
            vars_files=vars_files,
            meta=meta,
            templates=templates,
            static_files=static_files,
        )

        slog.info(
            f"Analyzed {len(tasks_files)} task files, "
            f"{len(handlers_files)} handler files, "
            f"{len(defaults_files)} defaults files, "
            f"{len(vars_files)} vars files, "
            f"{'1 meta file' if meta else 'no meta file'}, "
            f"{len(templates)} templates"
        )

        execution_summary = self._build_execution_summary(structured_analysis)

        return state.update(
            structured_analysis=structured_analysis,
            execution_summary=execution_summary,
        )

    def _analyze_yaml_files(
        self, directory: Path, file_type: str, slog
    ) -> list[TaskFileAnalysisResult]:
        """Analyze YAML task/handler files in a directory."""
        results: list[TaskFileAnalysisResult] = []

        if not directory.exists():
            return results

        for file_path in sorted(directory.iterdir()):
            if file_path.suffix not in YAML_EXTENSIONS:
                continue

            try:
                slog.debug(f"Analyzing {file_type}: {file_path}")
                analysis = self._task_service.analyze(file_path)
                results.append(
                    TaskFileAnalysisResult(
                        file_path=str(file_path),
                        file_type=file_type,
                        analysis=analysis,
                    )
                )
            except Exception as e:
                slog.warning(f"Failed to analyze {file_type} {file_path}: {e}")

        return results

    def _analyze_vars_files(
        self, directory: Path, file_type: str, slog
    ) -> list[VariablesAnalysisResult]:
        """Analyze defaults/vars YAML files in a directory."""
        results: list[VariablesAnalysisResult] = []

        if not directory.exists():
            return results

        for file_path in sorted(directory.iterdir()):
            if file_path.suffix not in YAML_EXTENSIONS:
                continue

            try:
                slog.debug(f"Analyzing {file_type}: {file_path}")
                analysis = self._vars_service.analyze(file_path)
                results.append(
                    VariablesAnalysisResult(
                        file_path=str(file_path),
                        file_type=file_type,
                        analysis=analysis,
                    )
                )
            except Exception as e:
                slog.warning(f"Failed to analyze {file_type} {file_path}: {e}")

        return results

    def _analyze_meta(
        self, directory: Path, slog
    ) -> MetaAnalysisResult | None:
        """Analyze meta/main.yml if it exists."""
        if not directory.exists():
            return None

        meta_file = directory / "main.yml"
        if not meta_file.exists():
            meta_file = directory / "main.yaml"
        if not meta_file.exists():
            return None

        try:
            slog.debug(f"Analyzing meta: {meta_file}")
            analysis = self._meta_service.analyze(meta_file)
            return MetaAnalysisResult(
                file_path=str(meta_file),
                analysis=analysis,
            )
        except Exception as e:
            slog.warning(f"Failed to analyze meta {meta_file}: {e}")
            return None

    def _analyze_templates(
        self, directory: Path, slog
    ) -> list[TemplateAnalysisResult]:
        """Analyze .j2 template files."""
        results: list[TemplateAnalysisResult] = []

        if not directory.exists():
            return results

        for file_path in sorted(directory.rglob("*.j2")):
            try:
                slog.debug(f"Analyzing template: {file_path}")
                analysis = self._template_service.analyze(file_path)
                results.append(
                    TemplateAnalysisResult(
                        file_path=str(file_path),
                        analysis=analysis,
                    )
                )
            except Exception as e:
                slog.warning(f"Failed to analyze template {file_path}: {e}")

        return results

    def _collect_static_files(self, directory: Path, slog) -> list[str]:
        """Collect static file paths from files/ directory."""
        if not directory.exists():
            return []

        static_files = [str(f) for f in sorted(directory.rglob("*")) if f.is_file()]
        slog.info(f"Found {len(static_files)} static files")
        return static_files

    def _build_execution_summary(
        self, analysis: AnsibleStructuredAnalysis
    ) -> str:
        """Build summary of all analyzed Ansible role code."""
        lines = [
            "=" * 80,
            "ANSIBLE ROLE ANALYSIS SUMMARY",
            "=" * 80,
            "",
            f"Total files analyzed: {analysis.get_total_files_analyzed()}",
            "",
        ]

        lines.extend(self._format_tasks_summary(analysis.tasks_files, "TASKS"))
        lines.extend(
            self._format_tasks_summary(analysis.handlers_files, "HANDLERS")
        )
        lines.extend(self._format_vars_summary(analysis.defaults_files, "DEFAULTS"))
        lines.extend(self._format_vars_summary(analysis.vars_files, "VARS"))
        lines.extend(self._format_meta_summary(analysis.meta))
        lines.extend(self._format_templates_summary(analysis.templates))
        lines.extend(self._format_static_files_summary(analysis.static_files))
        lines.extend(["=" * 80, ""])

        return "\n".join(lines)

    def _format_tasks_summary(
        self, files: list[TaskFileAnalysisResult], section_name: str
    ) -> list[str]:
        """Format tasks/handlers section of the summary."""
        if not files:
            return []
        lines = [f"{section_name}:"]
        for tf in files:
            lines.append(f"  {tf.file_path}")
            lines.append(f"    Tasks: {len(tf.analysis.tasks)}")
            for task in tf.analysis.tasks:
                loop_info = f" [loop: {task.loop}]" if task.loop else ""
                priv_info = ""
                if task.privilege_escalation:
                    priv_info = f" [priv: {task.privilege_escalation}]"
                note_info = f" NOTE: {task.note}" if task.note else ""
                lines.append(
                    f"    - [{task.module}] {task.name}"
                    f"{loop_info}{priv_info}{note_info}"
                )
        lines.append("")
        return lines

    def _format_vars_summary(
        self, files: list[VariablesAnalysisResult], section_name: str
    ) -> list[str]:
        """Format defaults/vars section of the summary."""
        if not files:
            return []
        lines = [f"{section_name}:"]
        for vf in files:
            lines.append(f"  {vf.file_path}")
            lines.append(f"    Variables: {len(vf.analysis.variables)}")
            for var_name in sorted(vf.analysis.variables.keys())[:20]:
                lines.append(f"    - {var_name}: {vf.analysis.variables[var_name]}")
            if len(vf.analysis.variables) > 20:
                lines.append(f"    ... and {len(vf.analysis.variables) - 20} more")
            if vf.analysis.notes:
                lines.append("    Notes:")
                for note in vf.analysis.notes:
                    lines.append(f"      - {note}")
        lines.append("")
        return lines

    def _format_meta_summary(self, meta: MetaAnalysisResult | None) -> list[str]:
        """Format meta section of the summary."""
        if not meta:
            return []
        lines = [
            "META:",
            f"  {meta.file_path}",
            f"    Role name: {meta.analysis.role_name}",
            f"    Dependencies: {len(meta.analysis.dependencies)}",
        ]
        for dep in meta.analysis.dependencies:
            lines.append(f"    - {dep}")
        lines.append("")
        return lines

    def _format_templates_summary(
        self, templates: list[TemplateAnalysisResult]
    ) -> list[str]:
        """Format templates section of the summary."""
        if not templates:
            return []
        lines = ["TEMPLATES:"]
        for tmpl in templates:
            lines.append(f"  {tmpl.file_path}")
            lines.append(
                f"    Variables: {len(tmpl.analysis.variables_used)}"
            )
            if tmpl.analysis.bare_variables:
                lines.append(
                    f"    Bare variables: {', '.join(tmpl.analysis.bare_variables)}"
                )
            if tmpl.analysis.deprecated_tests:
                lines.append(
                    f"    Deprecated tests: {', '.join(tmpl.analysis.deprecated_tests)}"
                )
            if tmpl.analysis.notes:
                for note in tmpl.analysis.notes:
                    lines.append(f"    Note: {note}")
        lines.append("")
        return lines

    def _format_static_files_summary(self, static_files: list[str]) -> list[str]:
        """Format static files section of the summary."""
        if not static_files:
            return []
        lines = ["STATIC FILES:"]
        for f in static_files:
            lines.append(f"  {f}")
        lines.append("")
        return lines

    def invoke(
        self, path: str, user_message: str, telemetry: Telemetry | None = None
    ) -> str:
        """Analyze an Ansible role and return migration plan.

        This method satisfies the InfrastructureAnalyzer protocol.

        Args:
            path: Path to Ansible role directory
            user_message: User's migration requirements
            telemetry: Optional telemetry collector

        Returns:
            Migration specification as markdown string
        """
        logger.info("Using Ansible agent for migration analysis...")

        initial_state = AnsibleAnalysisState(
            path=path,
            user_message=user_message,
            specification="",
            collection_dependencies=[],
            telemetry=telemetry,
        )

        result = self._workflow.invoke(initial_state, config=get_runnable_config())

        if result.get("failed"):
            logger.error(
                f"Ansible analysis failed: {result.get('failure_reason', 'unknown')}"
            )

        return result["specification"]
