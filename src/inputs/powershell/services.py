"""PowerShell analysis services.

This module provides services for analyzing PowerShell files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.model import get_runnable_config
from src.utils.logging import get_logger

from .models import (
    DSCExecutionAnalysis,
    ModuleExecutionAnalysis,
    ScriptExecutionAnalysis,
)

logger = get_logger(__name__)


class ScriptAnalysisService:
    """Service for analyzing PowerShell script files using LLM.

    Responsibility: Extract execution order from .ps1 script files.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> ScriptExecutionAnalysis:
        """Analyze script and extract execution order."""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return ScriptExecutionAnalysis(execution_order=[])

        file_content = file_path.read_text()
        system_prompt = get_prompt("powershell_script_analysis_system").format()
        task_prompt = get_prompt("powershell_script_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                ScriptExecutionAnalysis
            )
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"Extracted {len(result.execution_order)} execution items "
                f"from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return ScriptExecutionAnalysis(execution_order=[])


class DSCAnalysisService:
    """Service for analyzing PowerShell DSC configuration files using LLM.

    Responsibility: Extract DSC resources from Configuration blocks.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> DSCExecutionAnalysis:
        """Analyze DSC configuration and extract resources."""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return DSCExecutionAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("powershell_dsc_analysis_system").format()
        task_prompt = get_prompt("powershell_dsc_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(DSCExecutionAnalysis)
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"Extracted {len(result.resources)} DSC resources from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze DSC {file_path}: {e}")
            return DSCExecutionAnalysis()


class ModuleAnalysisService:
    """Service for analyzing PowerShell module files using LLM.

    Responsibility: Extract exported functions and dependencies from .psm1 files.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> ModuleExecutionAnalysis:
        """Analyze module and extract exports and dependencies."""
        if not file_path.exists():
            logger.warning(f"Module not found: {file_path}")
            return ModuleExecutionAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("powershell_module_analysis_system").format()
        task_prompt = get_prompt("powershell_module_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                ModuleExecutionAnalysis
            )
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"Extracted {len(result.exported_functions)} functions, "
                f"{len(result.dependencies)} dependencies from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze module {file_path}: {e}")
            return ModuleExecutionAnalysis()
