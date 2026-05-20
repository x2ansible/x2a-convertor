"""PowerShell analysis services.

This module provides services for analyzing PowerShell files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.types.file_analysis_state import FileAnalysisState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger

from .models import (
    DSCExecutionAnalysis,
    ModuleExecutionAnalysis,
    ScriptExecutionAnalysis,
)

logger = get_logger(__name__)


class ScriptAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing PowerShell script files using LLM.

    Responsibility: Extract execution order from .ps1 script files.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=ScriptExecutionAnalysis(execution_order=[]))

        file_content = file_path.read_text()
        system_prompt = get_prompt("powershell_script_analysis_system").format()
        task_prompt = get_prompt("powershell_script_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(ScriptExecutionAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.execution_order)} execution items "
                f"from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return state.update(result=ScriptExecutionAnalysis(execution_order=[]))


class DSCAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing PowerShell DSC configuration files using LLM.

    Responsibility: Extract DSC resources from Configuration blocks.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=DSCExecutionAnalysis())

        file_content = file_path.read_text()
        system_prompt = get_prompt("powershell_dsc_analysis_system").format()
        task_prompt = get_prompt("powershell_dsc_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(DSCExecutionAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.resources)} DSC resources from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze DSC {file_path}: {e}")
            return state.update(result=DSCExecutionAnalysis())


class ModuleAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing PowerShell module files using LLM.

    Responsibility: Extract exported functions and dependencies from .psm1 files.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Module not found: {file_path}")
            return state.update(result=ModuleExecutionAnalysis())

        file_content = file_path.read_text()
        system_prompt = get_prompt("powershell_module_analysis_system").format()
        task_prompt = get_prompt("powershell_module_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(ModuleExecutionAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.exported_functions)} functions, "
                f"{len(result.dependencies)} dependencies from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze module {file_path}: {e}")
            return state.update(result=ModuleExecutionAnalysis())
