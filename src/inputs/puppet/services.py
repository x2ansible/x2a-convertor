"""Puppet analysis services.

This module provides services for analyzing Puppet files using LLM.
Each service has a single responsibility (SRP).
"""

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from prompts.get_prompt import get_prompt
from src.model import get_runnable_config
from src.utils.logging import get_logger

from .models import (
    CredentialAnalysis,
    CustomTypeAnalysis,
    HieraDataAnalysis,
    ManifestExecutionAnalysis,
    PuppetTemplateAnalysis,
)

logger = get_logger(__name__)

MAX_STRUCTURED_RETRIES = 3


class ManifestAnalysisService:
    """Analyze Puppet manifest (.pp) files using LLM."""

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> ManifestExecutionAnalysis:
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return ManifestExecutionAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("puppet_manifest_analysis_system").format()
        task_prompt = get_prompt("puppet_manifest_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                ManifestExecutionAnalysis
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_prompt),
            ]
            result = None
            for attempt in range(MAX_STRUCTURED_RETRIES):
                result = structured_model.invoke(messages, config=get_runnable_config())
                if result is not None:
                    break
                logger.warning(
                    f"Structured output returned None for {file_path.name}, retrying ({attempt + 1}/{MAX_STRUCTURED_RETRIES})"
                )
            if result is None:
                logger.error(
                    f"Structured output returned None after {MAX_STRUCTURED_RETRIES} retries for {file_path.name}"
                )
                return ManifestExecutionAnalysis()
            logger.info(
                f"Extracted {len(result.resources)} resources, "
                f"{len(result.class_includes)} includes from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze manifest {file_path}: {e}", exc_info=True)
            return ManifestExecutionAnalysis()


class HieraDataAnalysisService:
    """Analyze Hiera data files using LLM.

    Non-deterministic: reasons about variable mapping to Ansible targets,
    merge behavior, and cross-level overrides.
    """

    def __init__(self, model):
        self._model = model

    def analyze(
        self,
        file_path: Path,
        hierarchy_level: str = "",
        full_hierarchy: str = "",
    ) -> HieraDataAnalysis:
        if not file_path.exists():
            logger.warning(f"Hiera data file not found: {file_path}")
            return HieraDataAnalysis()

        file_content = file_path.read_text()
        system_prompt = get_prompt("puppet_hiera_analysis_system").format()
        task_prompt = get_prompt("puppet_hiera_analysis_task").format(
            file_path=str(file_path),
            file_content=file_content,
            hierarchy_level=hierarchy_level,
            full_hierarchy=full_hierarchy,
        )

        try:
            structured_model = self._model.with_structured_output(HieraDataAnalysis)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_prompt),
            ]
            result = None
            for attempt in range(MAX_STRUCTURED_RETRIES):
                result = structured_model.invoke(messages, config=get_runnable_config())
                if result is not None:
                    break
                logger.warning(
                    f"Structured output returned None for {file_path.name}, retrying ({attempt + 1}/{MAX_STRUCTURED_RETRIES})"
                )
            if result is None:
                logger.error(
                    f"Structured output returned None after {MAX_STRUCTURED_RETRIES} retries for {file_path.name}"
                )
                return HieraDataAnalysis()
            logger.info(
                f"Extracted {len(result.variables)} variables from {file_path.name} "
                f"(level: {hierarchy_level})"
            )
            return result
        except Exception as e:
            logger.error(
                f"Failed to analyze Hiera data {file_path}: {e}", exc_info=True
            )
            return HieraDataAnalysis()


class TemplateAnalysisService:
    """Analyze ERB (.erb) and EPP (.epp) template files using LLM."""

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> PuppetTemplateAnalysis:
        if not file_path.exists():
            logger.warning(f"Template not found: {file_path}")
            return PuppetTemplateAnalysis(template_type="unknown")

        file_content = file_path.read_text()
        template_type = "epp" if file_path.suffix == ".epp" else "erb"
        system_prompt = get_prompt("puppet_template_analysis_system").format()
        task_prompt = get_prompt("puppet_template_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(
                PuppetTemplateAnalysis
            )
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_prompt),
            ]
            result = None
            for attempt in range(MAX_STRUCTURED_RETRIES):
                result = structured_model.invoke(messages, config=get_runnable_config())
                if result is not None:
                    break
                logger.warning(
                    f"Structured output returned None for {file_path.name}, retrying ({attempt + 1}/{MAX_STRUCTURED_RETRIES})"
                )
            if result is None:
                logger.error(
                    f"Structured output returned None after {MAX_STRUCTURED_RETRIES} retries for {file_path.name}"
                )
                return PuppetTemplateAnalysis(template_type=template_type)
            logger.info(
                f"Analyzed {template_type} template {file_path.name}: "
                f"{len(result.variables_used)} variables, "
                f"{len(result.ruby_logic)} complex blocks"
            )
            return result
        except Exception as e:
            logger.error(f"Failed to analyze template {file_path}: {e}", exc_info=True)
            return PuppetTemplateAnalysis(template_type=template_type)


class CustomTypeAnalysisService:
    """Analyze custom types, providers, facts, and functions using LLM."""

    def __init__(self, model):
        self._model = model

    def analyze(self, file_path: Path) -> CustomTypeAnalysis:
        if not file_path.exists():
            logger.warning(f"Custom type file not found: {file_path}")
            return CustomTypeAnalysis(component_type="unknown", name="unknown")

        file_content = file_path.read_text()
        system_prompt = get_prompt("puppet_custom_type_analysis_system").format()
        task_prompt = get_prompt("puppet_custom_type_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            structured_model = self._model.with_structured_output(CustomTypeAnalysis)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_prompt),
            ]
            result = None
            for attempt in range(MAX_STRUCTURED_RETRIES):
                result = structured_model.invoke(messages, config=get_runnable_config())
                if result is not None:
                    break
                logger.warning(
                    f"Structured output returned None for {file_path.name}, retrying ({attempt + 1}/{MAX_STRUCTURED_RETRIES})"
                )
            if result is None:
                logger.error(
                    f"Structured output returned None after {MAX_STRUCTURED_RETRIES} retries for {file_path.name}"
                )
                return CustomTypeAnalysis(component_type="unknown", name=file_path.stem)
            logger.info(
                f"Analyzed {result.component_type} '{result.name}' from {file_path.name}"
            )
            return result
        except Exception as e:
            logger.error(
                f"Failed to analyze custom type {file_path}: {e}", exc_info=True
            )
            return CustomTypeAnalysis(component_type="unknown", name=file_path.stem)


class CredentialDetectionService:
    """Detect credentials and secrets across Hiera data and manifests."""

    def __init__(self, model):
        self._model = model

    def analyze(self, hiera_variables: str, manifest_params: str) -> CredentialAnalysis:
        system_prompt = get_prompt("puppet_credential_detection_system").format()
        task_prompt = get_prompt("puppet_credential_detection_task").format(
            hiera_variables=hiera_variables,
            manifest_params=manifest_params,
        )

        try:
            structured_model = self._model.with_structured_output(CredentialAnalysis)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=task_prompt),
            ]
            result = None
            for attempt in range(MAX_STRUCTURED_RETRIES):
                result = structured_model.invoke(messages, config=get_runnable_config())
                if result is not None:
                    break
                logger.warning(
                    f"Structured output returned None for credentials, retrying ({attempt + 1}/{MAX_STRUCTURED_RETRIES})"
                )
            if result is None:
                logger.error(
                    f"Structured output returned None after {MAX_STRUCTURED_RETRIES} retries for credentials"
                )
                return CredentialAnalysis()
            logger.info(f"Detected {result.total_detected} credentials")
            return result
        except Exception as e:
            logger.error(f"Failed to detect credentials: {e}", exc_info=True)
            return CredentialAnalysis()
