"""Chef analysis services.

This module provides services for analyzing Chef files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.model import get_runnable_config
from src.utils.logging import get_logger

from .models import (
    DefaultAttributesOutput,
    ProviderAnalysisOutput,
    RecipeExecutionAnalysis,
)

logger = get_logger(__name__)


class RecipeAnalysisService:
    """Service for analyzing Chef recipe files using LLM.

    Responsibility: Extract execution order from recipe files.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> RecipeExecutionAnalysis:
        """Analyze recipe and extract execution order.

        Args:
            file_path: Path to recipe file

        Returns:
            RecipeExecutionAnalysis with execution_order
        """
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return RecipeExecutionAnalysis(execution_order=[])

        file_content = file_path.read_text()
        system_prompt = get_prompt("chef_recipe_analysis_system").format()
        task_prompt = get_prompt("chef_recipe_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                RecipeExecutionAnalysis
            )
            # Combine system and task prompts into a single message
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"✓ Extracted {len(result.execution_order)} execution items from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return RecipeExecutionAnalysis(execution_order=[])


class ProviderAnalysisService:
    """Service for analyzing Chef provider files using LLM.

    Responsibility: Extract templates and resources created by providers.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> ProviderAnalysisOutput:
        """Analyze provider and extract templates/resources created.

        Args:
            file_path: Path to provider file

        Returns:
            ProviderAnalysisOutput with templates and conditionals
        """
        if not file_path.exists():
            logger.warning(f"Provider not found: {file_path}")
            return ProviderAnalysisOutput()

        file_content = file_path.read_text()
        system_prompt = get_prompt("chef_provider_analysis_system").format()
        task_prompt = get_prompt("chef_provider_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                ProviderAnalysisOutput
            )
            # Combine system and task prompts into a single message
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )
            logger.info(
                f"✓ Provider {file_path.name} has {len(result.unconditional_templates)} unconditional templates, "
                f"{len(result.conditionals)} conditional branches"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze provider {file_path}: {e}")
            return ProviderAnalysisOutput()


class AttributeAnalysisService:
    """Service for analyzing Chef attributes files using LLM.

    Responsibility: Extract default attribute values from attributes/default.rb.
    """

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> DefaultAttributesOutput:
        """Analyze attributes file and extract default values.

        Args:
            file_path: Path to attributes/default.rb file

        Returns:
            DefaultAttributesOutput with extracted attributes
        """
        if not file_path.exists():
            logger.warning(f"Attributes file not found: {file_path}")
            return DefaultAttributesOutput()

        file_content = file_path.read_text()
        system_prompt = get_prompt("chef_attributes_extraction_system").format()
        task_prompt = get_prompt("chef_attributes_extraction_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                DefaultAttributesOutput
            )
            # Combine system and task prompts into a single message
            combined_prompt = f"{system_prompt}\n\n{task_prompt}"
            result = structured_model.invoke(
                combined_prompt, config=get_runnable_config()
            )

            if result.platform_specific_notes:
                logger.info("Platform-specific attributes found:")
                for note in result.platform_specific_notes:
                    logger.info(f"  - {note}")

            logger.info(
                f"✓ Extracted {len(result.attributes)} top-level default attributes from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze attributes {file_path}: {e}")
            return DefaultAttributesOutput()
