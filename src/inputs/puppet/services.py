"""Puppet analysis services.

This module provides services for analyzing Puppet files using LLM.
Each service has a single responsibility (SRP).
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from prompts.get_prompt import get_prompt
from src.inputs.input_agent import InputAgent
from src.types.file_analysis_state import FileAnalysisState
from src.types.telemetry import AgentMetrics
from src.utils.logging import get_logger

from .models import (
    CredentialAnalysis,
    CustomTypeAnalysis,
    HieraDataAnalysis,
    ManifestExecutionAnalysis,
    PuppetTemplateAnalysis,
)

logger = get_logger(__name__)


def _extract_json(text: str) -> str:
    """Extract JSON from LLM text response, stripping markdown fences."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    brace_start = text.find("{")
    if brace_start >= 0:
        return text[brace_start:]
    return text


def _invoke_structured_fallback(
    agent: InputAgent,
    schema: type[BaseModel],
    messages: list[dict[str, str]],
    metrics: AgentMetrics | None = None,
) -> BaseModel | None:
    """Fallback: invoke LLM as plain text and parse JSON from the response."""
    try:
        fallback_messages = list(messages)
        if fallback_messages and fallback_messages[0].get("role") == "system":
            fallback_messages[0] = {
                "role": "system",
                "content": fallback_messages[0]["content"]
                + "\n\nRespond with ONLY a valid JSON object. No markdown fences, no explanations.",
            }
        raw = agent.invoke_llm(fallback_messages, metrics)
        json_str = _extract_json(raw)
        return schema.model_validate(json.loads(json_str))
    except Exception as e:
        logger.error(f"JSON text fallback also failed: {e}")
        return None


class ManifestAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing Puppet manifest (.pp) files using LLM.

    Responsibility: Extract resources, classes, and control structures from manifests.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return state.update(result=ManifestExecutionAnalysis())

        file_content = file_path.read_text()
        system_prompt = get_prompt("puppet_manifest_analysis_system").format()
        task_prompt = get_prompt("puppet_manifest_analysis_task").format(
            file_path=str(file_path), file_content=file_content
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt},
        ]

        try:
            result = self.invoke_structured(
                ManifestExecutionAnalysis, messages, metrics
            )
        except Exception as e:
            logger.warning(
                f"Native structured output failed for {file_path.name}: {e}, "
                "falling back to JSON text parsing"
            )
            result = _invoke_structured_fallback(
                self, ManifestExecutionAnalysis, messages, metrics
            )

        if result is None:
            logger.error(f"Failed to analyze manifest {file_path}")
            return state.update(result=ManifestExecutionAnalysis())

        logger.info(
            f"Extracted {len(result.resources)} resources, "
            f"{len(result.class_includes)} includes from {file_path.name}"
        )
        return state.update(result=result)


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
            logger.warning(f"Hiera data file not found: {file_path}")
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task_prompt},
        ]

        try:
            result = self.invoke_structured(HieraDataAnalysis, messages, metrics)
        except Exception as e:
            logger.warning(
                f"Native structured output failed for {file_path.name}: {e}, "
                "falling back to JSON text parsing"
            )
            result = _invoke_structured_fallback(
                self, HieraDataAnalysis, messages, metrics
            )

        if result is None:
            logger.error(f"Failed to analyze Hiera data {file_path}")
            return state.update(result=HieraDataAnalysis())

        logger.info(
            f"Extracted {len(result.variables)} variables from {file_path.name} "
            f"(level: {hierarchy_level})"
        )
        return state.update(result=result)


class TemplateAnalysisService(InputAgent[FileAnalysisState]):
    """Service for analyzing ERB (.erb) and EPP (.epp) template files using LLM.

    Responsibility: Extract variables, loops, and Ruby logic from templates.
    """

    def execute(
        self, state: FileAnalysisState, metrics: AgentMetrics | None
    ) -> FileAnalysisState:
        file_path = Path(state.path)
        if not file_path.exists():
            logger.warning(f"Template not found: {file_path}")
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
                f"Analyzed {template_type} template {file_path.name}: "
                f"{len(result.variables_used)} variables, "
                f"{len(result.ruby_logic)} complex blocks"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze template {file_path}: {e}")
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
            logger.warning(f"Custom type file not found: {file_path}")
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
                f"Analyzed {result.component_type} '{result.name}' from {file_path.name}"
            )
            return state.update(result=result)
        except Exception as e:
            logger.error(f"Failed to analyze custom type {file_path}: {e}")
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
