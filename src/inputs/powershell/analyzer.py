"""Powershell infrastructure analyzer.

This module implements the main PowershellSubagent that orchestrates all
Powershell analysis. It composes services and BaseAgent subclasses as graph
nodes following the pattern from src/inputs/chef/analyzer.py.
"""

from pathlib import Path
from typing import ClassVar, Literal

from langgraph.graph import END, StateGraph

from src.inputs.powershell.analysis_validation_agent import AnalysisValidationAgent
from src.inputs.powershell.cleanup_agent import CleanupAgent
from src.inputs.powershell.models import (
    DSCAnalysisResult,
    ModuleAnalysisResult,
    PowershellStructuredAnalysis,
    ScriptAnalysisResult,
)
from src.inputs.powershell.report_writer_agent import ReportWriterAgent
from src.inputs.powershell.services import (
    DSCAnalysisService,
    ModuleAnalysisService,
    ScriptAnalysisService,
)
from src.inputs.powershell.state import PowershellAnalysisState
from src.model import get_model, get_runnable_config
from src.types import Telemetry
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PowershellSubagent:
    """Main Powershell analyzer - implements InfrastructureAnalyzer protocol.

    This class orchestrates all Powershell analysis using a LangGraph workflow.

    Workflow phases:
    1. scan_files - Scan for .ps1, .psm1, .psd1 files; classify by type
    2. analyze_structure - Use analysis services to analyze all files
    3. write_report - Generate migration plan using ReportWriterAgent
    4. validate_with_analysis - Validate plan using AnalysisValidationAgent
    5. cleanup_specification - Clean up using CleanupAgent
    """

    DSC_KEYWORDS: ClassVar[list[str]] = ["Configuration", "Import-DscResource", "Node"]

    def __init__(self, model=None) -> None:
        self.model = model or get_model()

        self._script_service = ScriptAnalysisService(self.model)
        self._dsc_service = DSCAnalysisService(self.model)
        self._module_service = ModuleAnalysisService(self.model)

        self._report_writer = ReportWriterAgent(model=self.model)
        self._analysis_validator = AnalysisValidationAgent(model=self.model)
        self._cleanup = CleanupAgent(model=self.model)

        self._workflow = self._create_workflow()
        logger.debug(self._workflow.get_graph().draw_mermaid())

    def _create_workflow(self):
        """Create LangGraph workflow composing agents as nodes."""
        workflow = StateGraph(PowershellAnalysisState)

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
        self, state: PowershellAnalysisState
    ) -> Literal["continue", "failed"]:
        """Conditional edge: check if agent failed."""
        if state.failed:
            logger.error(f"Agent failed: {state.failure_reason}")
            return "failed"
        return "continue"

    def _scan_files(self, state: PowershellAnalysisState) -> PowershellAnalysisState:
        """Scan for Powershell files and classify them."""
        slog = logger.bind(phase="scan_files")
        slog.info(f"Scanning for Powershell files in {state.path}")

        base_path = Path(state.path)
        ps1_files = list(base_path.rglob("*.ps1"))
        psm1_files = list(base_path.rglob("*.psm1"))
        psd1_files = list(base_path.rglob("*.psd1"))

        all_files = ps1_files + psm1_files + psd1_files
        slog.info(
            f"Found {len(ps1_files)} .ps1, {len(psm1_files)} .psm1, "
            f"{len(psd1_files)} .psd1 files"
        )

        if not all_files:
            slog.warning("No Powershell files found")
            return state.mark_failed("No Powershell files found in the repository")

        dependency_modules = self._extract_import_modules(all_files, slog)

        return state.update(dependency_modules=dependency_modules)

    def _extract_import_modules(self, files: list[Path], slog) -> list[str]:
        """Extract Import-Module references from all files."""
        modules: set[str] = set()

        for file_path in files:
            try:
                content = file_path.read_text(errors="replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("Import-Module"):
                        module_name = stripped.replace("Import-Module", "").strip()
                        module_name = (
                            module_name.strip("'\"").split()[0] if module_name else ""
                        )
                        if module_name:
                            modules.add(module_name)
            except Exception as e:
                slog.warning(f"Failed to read {file_path}: {e}")

        slog.info(f"Found {len(modules)} Import-Module references")
        return sorted(modules)

    def _is_dsc_file(self, file_path: Path) -> bool:
        """Check if a file contains DSC Configuration blocks."""
        try:
            content = file_path.read_text(errors="replace")
            return any(keyword in content for keyword in self.DSC_KEYWORDS)
        except Exception:
            return False

    def _analyze_structure(
        self, state: PowershellAnalysisState
    ) -> PowershellAnalysisState:
        """Analyze all Powershell files using analysis services."""
        slog = logger.bind(phase="analyze_structure")
        slog.info("Starting structured analysis of Powershell files")

        base_path = Path(state.path)
        ps1_files = list(base_path.rglob("*.ps1"))
        psm1_files = list(base_path.rglob("*.psm1"))

        scripts, dsc_configs = self._analyze_scripts_and_dsc(ps1_files, slog)
        modules = self._analyze_modules(psm1_files, slog)

        structured_analysis = PowershellStructuredAnalysis(
            scripts=scripts,
            dsc_configs=dsc_configs,
            modules=modules,
        )

        slog.info(
            f"Analyzed {len(scripts)} scripts, {len(dsc_configs)} DSC configs, "
            f"{len(modules)} modules"
        )

        execution_summary = self._build_execution_summary(structured_analysis)

        return state.update(
            structured_analysis=structured_analysis,
            execution_summary=execution_summary,
        )

    def _analyze_scripts_and_dsc(
        self, ps1_files: list[Path], slog
    ) -> tuple[list[ScriptAnalysisResult], list[DSCAnalysisResult]]:
        """Classify and analyze .ps1 files as scripts or DSC configs."""
        scripts: list[ScriptAnalysisResult] = []
        dsc_configs: list[DSCAnalysisResult] = []

        for file_path in ps1_files:
            try:
                if self._is_dsc_file(file_path):
                    slog.debug(f"Analyzing DSC config: {file_path}")
                    analysis = self._dsc_service.analyze(file_path)
                    dsc_configs.append(
                        DSCAnalysisResult(
                            file_path=str(file_path),
                            configuration_name=analysis.configuration_name,
                            node_name=analysis.node_name,
                            resources=analysis.resources,
                        )
                    )
                else:
                    slog.debug(f"Analyzing script: {file_path}")
                    analysis = self._script_service.analyze(file_path)
                    scripts.append(
                        ScriptAnalysisResult(
                            file_path=str(file_path),
                            execution_items=analysis.execution_order,
                        )
                    )
            except Exception as e:
                slog.warning(f"Failed to analyze {file_path}: {e}")

        return scripts, dsc_configs

    def _analyze_modules(
        self, psm1_files: list[Path], slog
    ) -> list[ModuleAnalysisResult]:
        """Analyze .psm1 module files."""
        modules: list[ModuleAnalysisResult] = []

        for file_path in psm1_files:
            try:
                slog.debug(f"Analyzing module: {file_path}")
                analysis = self._module_service.analyze(file_path)
                modules.append(
                    ModuleAnalysisResult(
                        file_path=str(file_path),
                        exported_functions=analysis.exported_functions,
                        dependencies=analysis.dependencies,
                        parameters=analysis.parameters,
                    )
                )
            except Exception as e:
                slog.warning(f"Failed to analyze module {file_path}: {e}")

        return modules

    def _build_execution_summary(self, analysis: PowershellStructuredAnalysis) -> str:
        """Build summary of all analyzed Powershell code."""
        lines = [
            "=" * 80,
            "POWERSHELL ANALYSIS SUMMARY",
            "=" * 80,
            "",
            f"Total files analyzed: {analysis.get_total_files_analyzed()}",
            "",
        ]
        lines.extend(self._format_scripts_summary(analysis.scripts))
        lines.extend(self._format_dsc_summary(analysis.dsc_configs))
        lines.extend(self._format_modules_summary(analysis.modules))
        lines.extend(self._format_dependencies_summary(analysis.all_dependencies))
        lines.extend(["=" * 80, ""])
        return "\n".join(lines)

    def _format_scripts_summary(self, scripts: list[ScriptAnalysisResult]) -> list[str]:
        """Format scripts section of the summary."""
        if not scripts:
            return []
        lines = ["SCRIPTS:"]
        for script in scripts:
            lines.append(f"  {script.file_path}")
            lines.append(f"    Operations: {len(script.execution_items)} items")
            for item in script.execution_items[:10]:
                lines.append(f"    - [{item.type}] {item.command}")
        lines.append("")
        return lines

    def _format_dsc_summary(self, dsc_configs: list[DSCAnalysisResult]) -> list[str]:
        """Format DSC configurations section of the summary."""
        if not dsc_configs:
            return []
        lines = ["DSC CONFIGURATIONS:"]
        for dsc in dsc_configs:
            lines.append(f"  {dsc.file_path} (Configuration: {dsc.configuration_name})")
            for resource in dsc.resources:
                lines.append(
                    f"    - {resource.resource_type}[{resource.name}] "
                    f"(Ensure: {resource.ensure})"
                )
        lines.append("")
        return lines

    def _format_modules_summary(self, modules: list[ModuleAnalysisResult]) -> list[str]:
        """Format modules section of the summary."""
        if not modules:
            return []
        lines = ["MODULES:"]
        for module in modules:
            lines.append(f"  {module.file_path}")
            if module.exported_functions:
                lines.append(f"    Exports: {', '.join(module.exported_functions)}")
            if module.dependencies:
                lines.append(f"    Dependencies: {', '.join(module.dependencies)}")
        lines.append("")
        return lines

    def _format_dependencies_summary(self, dependencies: list[str]) -> list[str]:
        """Format dependencies section of the summary."""
        if not dependencies:
            return []
        lines = ["ALL IMPORT-MODULE DEPENDENCIES:"]
        for dep in dependencies:
            lines.append(f"  - {dep}")
        lines.append("")
        return lines

    def invoke(
        self, path: str, user_message: str, telemetry: Telemetry | None = None
    ) -> str:
        """Analyze Powershell code and return migration plan.

        This method satisfies the InfrastructureAnalyzer protocol.

        Args:
            path: Path to Powershell code directory
            user_message: User's migration requirements
            telemetry: Optional telemetry collector

        Returns:
            Migration specification as markdown string
        """
        logger.info("Using Powershell agent for migration analysis...")

        initial_state = PowershellAnalysisState(
            path=path,
            user_message=user_message,
            specification="",
            dependency_modules=[],
            telemetry=telemetry,
        )

        result = self._workflow.invoke(initial_state, config=get_runnable_config())

        if result.get("failed"):
            logger.error(
                f"Powershell analysis failed: {result.get('failure_reason', 'unknown')}"
            )

        return result["specification"]
