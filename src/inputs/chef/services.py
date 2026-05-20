"""Chef analysis services.

This module provides services for analyzing Chef files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.types.file_analysis_state import FileAnalysisState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger

from .models import (
    DefaultAttributesOutput,
    ProviderAnalysisOutput,
    RecipeExecutionAnalysis,
)

logger = get_logger(__name__)


class RecipeAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Chef recipe files using LLM.

    Responsibility: Extract execution order from recipe files.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=RecipeExecutionAnalysis(execution_order=[]))

        file_content = file_path.read_text()
        system_prompt = get_prompt("chef_recipe_analysis_system").format()
        task_prompt = get_prompt("chef_recipe_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(RecipeExecutionAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.execution_order)} execution items "
                f"from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return state.update(result=RecipeExecutionAnalysis(execution_order=[]))


class ProviderAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Chef provider files using LLM.

    Responsibility: Extract templates and resources created by providers.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Provider not found: {file_path}")
            return state.update(result=ProviderAnalysisOutput())

        file_content = file_path.read_text()
        system_prompt = get_prompt("chef_provider_analysis_system").format()
        task_prompt = get_prompt("chef_provider_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(ProviderAnalysisOutput, messages, metrics)
            logger.info(
                f"Provider {file_path.name} has "
                f"{len(result.unconditional_templates)} unconditional templates, "
                f"{len(result.conditionals)} conditional branches"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze provider {file_path}: {e}")
            return state.update(result=ProviderAnalysisOutput())


class AttributeAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Chef attributes files using LLM.

    Responsibility: Extract default attribute values from attributes/default.rb.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Attributes file not found: {file_path}")
            return state.update(result=DefaultAttributesOutput())

        file_content = file_path.read_text()
        system_prompt = get_prompt("chef_attributes_extraction_system").format()
        task_prompt = get_prompt("chef_attributes_extraction_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(DefaultAttributesOutput, messages, metrics)

            if result.platform_specific_notes:
                logger.info("Platform-specific attributes found:")
                for note in result.platform_specific_notes:
                    logger.info(f"  - {note}")

            logger.info(
                f"Extracted {len(result.attributes)} top-level default attributes "
                f"from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze attributes {file_path}: {e}")
            return state.update(result=DefaultAttributesOutput())
