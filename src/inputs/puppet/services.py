"""Puppet analysis services.

This module provides services for analyzing Puppet files using LLM.
Each service has a single responsibility (SRP).
"""

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.types.document import DocumentFile
from src.types.file_analysis_state import FileAnalysisState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger
from src.utils.path import Path

from .models import (
    CredentialAnalysis,
    CustomTypeAnalysis,
    HieraDataAnalysis,
    ManifestExecutionAnalysis,
    PuppetTemplateAnalysis,
)

logger = get_logger(__name__)


class ManifestAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Puppet manifest (.pp) files using LLM.

    Responsibility: Extract resources, classes, and control structures from manifests.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            raise FileNotFoundError(
                f"Manifest file not found: {file_path.relative_to_cwd()}"
            )

        document = DocumentFile.from_path(file_path)
        system_prompt = get_prompt("puppet_manifest_analysis_system").format()
        task_prompt = get_prompt("puppet_manifest_analysis_task").format(
            document=document.to_document()
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(
                ManifestExecutionAnalysis, messages, metrics
            )
            if not result:
                logger.error(
                    f"Empty analysis result for manifest {file_path.relative_to_cwd()}"
                )
                return state.update(result=ManifestExecutionAnalysis())
            execution_count = len(result.execution_order)
            logger.info(
                f"Extracted {execution_count} execution items "
                f"from {file_path.relative_to_cwd()}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(
                f"Failed to analyze manifest {file_path.relative_to_cwd()}: {e}"
            )
            return state.update(result=ManifestExecutionAnalysis())


class HieraDataAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Hiera data files using LLM.

    Responsibility: Extract variable mapping to Ansible targets,
    merge behavior, and cross-level overrides.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Hiera data file not found: {file_path.relative_to_cwd()}")
            return state.update(result=HieraDataAnalysis())

        hierarchy_level = state.metadata.get("hierarchy_level", "")
        full_hierarchy = state.metadata.get("full_hierarchy", "")

        file_content = file_path.read_text()
        system_prompt = get_prompt("puppet_hiera_analysis_system").format()
        task_prompt = get_prompt("puppet_hiera_analysis_task").format(
            file_path=str(file_path),
            file_content=file_content,
            hierarchy_level=hierarchy_level,
            full_hierarchy=full_hierarchy,
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(HieraDataAnalysis, messages, metrics)
            logger.info(
                f"Extracted {len(result.variables)} variables from {file_path.relative_to_cwd()} "
                f"(level: {hierarchy_level})"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(
                f"Failed to analyze Hiera data {file_path.relative_to_cwd()}: {e}"
            )
            return state.update(result=HieraDataAnalysis())


class TemplateAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing ERB (.erb) and EPP (.epp) template files using LLM.

    Responsibility: Extract variables, loops, and Ruby logic from templates.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Template not found: {file_path.relative_to_cwd()}")
            return state.update(result=PuppetTemplateAnalysis(template_type="unknown"))

        file_content = file_path.read_text()
        template_type = "epp" if file_path.suffix == ".epp" else "erb"
        system_prompt = get_prompt("puppet_template_analysis_system").format()
        task_prompt = get_prompt("puppet_template_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(PuppetTemplateAnalysis, messages, metrics)
            logger.info(
                f"Analyzed {template_type} template {file_path.relative_to_cwd()}: "
                f"{len(result.variables_used)} variables, "
                f"{len(result.ruby_logic)} complex blocks"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(
                f"Failed to analyze template {file_path.relative_to_cwd()}: {e}"
            )
            return state.update(
                result=PuppetTemplateAnalysis(template_type=template_type)
            )


class CustomTypeAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing custom types, providers, facts, and functions using LLM.

    Responsibility: Extract custom component details and Ansible equivalents.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Custom type file not found: {file_path.relative_to_cwd()}")
            return state.update(
                result=CustomTypeAnalysis(component_type="unknown", name="unknown")
            )

        file_content = file_path.read_text()
        system_prompt = get_prompt("puppet_custom_type_analysis_system").format()
        task_prompt = get_prompt("puppet_custom_type_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(CustomTypeAnalysis, messages, metrics)
            logger.info(
                f"Analyzed {result.component_type} '{result.name}' from {file_path.relative_to_cwd()}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(
                f"Failed to analyze custom type {file_path.relative_to_cwd()}: {e}"
            )
            return state.update(
                result=CustomTypeAnalysis(component_type="unknown", name=file_path.stem)
            )


class CredentialDetectionService(InputAgent[FileAnalysisState]):
    """Service for detecting credentials and secrets across Hiera data and manifests.

    Responsibility: Identify credentials and recommend Ansible-safe handling.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        hiera_variables = state.metadata.get("hiera_variables", "")
        manifest_params = state.metadata.get("manifest_params", "")

        system_prompt = get_prompt("puppet_credential_detection_system").format()
        task_prompt = get_prompt("puppet_credential_detection_task").format(
            hiera_variables=hiera_variables,
            manifest_params=manifest_params,
        )

        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task_prompt},
            ]
            result = self.invoke_structured(CredentialAnalysis, messages, metrics)
            logger.info(f"Detected {result.total_detected} credentials")
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to detect credentials: {e}")
            return state.update(result=CredentialAnalysis())
