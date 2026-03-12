"""Ansible analysis services.

This module provides services for analyzing Ansible role files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.model import get_runnable_config
from src.utils.logging import get_logger

from .models import (
    MetaAnalysis,
    TaskFileExecutionAnalysis,
    TemplateAnalysis,
    VariablesAnalysis,
)

logger = get_logger(__name__)


class TaskFileAnalysisService:
    """Service for analyzing Ansible task/handler files using LLM.

    Responsibility: Extract execution structure from tasks/*.yml and handlers/*.yml files.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> TaskFileExecutionAnalysis:
        """Analyze task/handler file and extract execution structure."""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return TaskFileExecutionAnalysis(tasks=[])

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_task_analysis_system").format()
        task_prompt = get_prompt("ansible_task_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                TaskFileExecutionAnalysis
            )
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(f"Extracted {len(result.tasks)} tasks from {file_path.name}")
            return result
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return TaskFileExecutionAnalysis(tasks=[])


class VariablesAnalysisService:
    """Service for analyzing Ansible defaults/vars files using LLM.

    Responsibility: Extract variables and flag legacy patterns from defaults/vars YAML files.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> VariablesAnalysis:
        """Analyze defaults/vars file and extract variables."""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return VariablesAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_defaults_analysis_system").format()
        task_prompt = get_prompt("ansible_defaults_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(VariablesAnalysis)
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"Extracted {len(result.variables)} variables from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return VariablesAnalysis()


class MetaAnalysisService:
    """Service for analyzing Ansible meta/main.yml files using LLM.

    Responsibility: Extract role metadata and dependencies.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> MetaAnalysis:
        """Analyze meta/main.yml and extract metadata."""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return MetaAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_meta_analysis_system").format()
        task_prompt = get_prompt("ansible_meta_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(MetaAnalysis)
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"Extracted metadata for role '{result.role_name}' from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return MetaAnalysis()


class TemplateAnalysisService:
    """Service for analyzing Jinja2 template files using LLM.

    Responsibility: Extract variables and flag deprecated Jinja2 patterns from .j2 files.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> TemplateAnalysis:
        """Analyze .j2 template and extract variables and patterns."""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return TemplateAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_template_analysis_system").format()
        task_prompt = get_prompt("ansible_template_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(TemplateAnalysis)
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"Extracted {len(result.variables_used)} variables from template {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze template {file_path}: {e}")
            return TemplateAnalysis()
