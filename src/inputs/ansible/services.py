"""Ansible analysis services.

This module provides services for analyzing Ansible role files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.types.file_analysis_state import FileAnalysisState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger

from .models import (
    MetaAnalysis,
    TaskFileExecutionAnalysis,
    TemplateAnalysis,
    VariablesAnalysis,
)

logger = get_logger(__name__)


class TaskFileAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Ansible task/handler files using LLM.

    Responsibility: Extract execution structure from tasks/*.yml and handlers/*.yml files.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=TaskFileExecutionAnalysis(tasks=[]))

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_task_analysis_system").format()
        task_prompt = get_prompt("ansible_task_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(
                TaskFileExecutionAnalysis, messages, metrics
            )
            logger.info(f"Extracted {len(result.tasks)} tasks from {file_path.name}")
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return state.update(result=TaskFileExecutionAnalysis(tasks=[]))


class VariablesAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Ansible defaults/vars files using LLM.

    Responsibility: Extract variables and flag legacy patterns from defaults/vars YAML files.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=VariablesAnalysis())

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_defaults_analysis_system").format()
        task_prompt = get_prompt("ansible_defaults_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(VariablesAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.variables)} variables from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return state.update(result=VariablesAnalysis())


class MetaAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Ansible meta/main.yml files using LLM.

    Responsibility: Extract role metadata and dependencies.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=MetaAnalysis())

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_meta_analysis_system").format()
        task_prompt = get_prompt("ansible_meta_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(MetaAnalysis, messages, metrics)
            logger.info(
                f"Extracted metadata for role '{result.role_name}' "
                f"from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return state.update(result=MetaAnalysis())


class TemplateAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Jinja2 template files using LLM.

    Responsibility: Extract variables and flag deprecated Jinja2 patterns from .j2 files.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=TemplateAnalysis())

        file_content = file_path.read_text()
        system_prompt = get_prompt("ansible_template_analysis_system").format()
        task_prompt = get_prompt("ansible_template_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(TemplateAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.variables_used)} variables "
                f"from template {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze template {file_path}: {e}")
            return state.update(result=TemplateAnalysis())
