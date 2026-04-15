"""Credential extraction agent for AAP credential configuration.

This agent extracts third-party credentials from migration plans and generates
AAP-style credential configuration files (controller_credential_types.yml,
controller_credentials.yml, validate_credentials.yml).

Runs as a workflow node before the planning agent so that both the planning
and write agents have access to credential_config in the state.
"""

from __future__ import annotations

from pathlib import Path

from prompts.get_prompt import get_prompt
from src.base_agent import BaseAgent
from src.exporters.state import ExportState
from src.types import ChecklistStatus
from src.types.credential import (
    CredentialConfig,
    CredentialExtractionOutput,
)
from src.types.telemetry import AgentMetrics


class CredentialAgent(BaseAgent[ExportState]):
    """Agent that extracts credentials from migration plan and writes AAP config files.

    Runs as its own workflow node before the planning agent.
    Extracts the ## Credentials section, uses LLM structured output to parse it,
    then writes the credential files and updates the checklist.
    """

    EXTRACTION_PROMPT_NAME = "export_credential_extraction_system"

    def execute(self, state: ExportState, metrics: AgentMetrics | None) -> ExportState:
        """Extract credentials and write AAP configuration files."""
        self._log.info("Starting credential extraction")

        extraction_prompt = self._build_extraction_prompt(state)
        credentials = self._extract_credentials(extraction_prompt, metrics)

        if not credentials:
            self._log.info("No credentials detected in migration plan")
            return state.update(credential_config=CredentialConfig.empty())

        self._log.info(f"Extracted {len(credentials)} credentials")

        credential_config = CredentialConfig.from_extracted(
            credentials, str(state.module)
        )

        state = self._write_credential_files(state, credential_config)

        if metrics:
            metrics.record_metric("credentials_found", len(credentials))

        return state.update(credential_config=credential_config)

    # -------------------------------------------------------------------------
    # Extraction
    # -------------------------------------------------------------------------

    def _build_extraction_prompt(self, state: ExportState) -> str:
        """Build the prompt for credential extraction from migration plan."""
        return get_prompt(self.EXTRACTION_PROMPT_NAME).format(
            high_level_migration_plan=state.high_level_migration_plan.to_document(),
            migration_plan=state.module_migration_plan.to_document(),
        )

    def _extract_credentials(self, prompt: str, metrics: AgentMetrics | None) -> list:
        """Extract credentials using LLM structured output."""
        try:
            result = self.invoke_structured(CredentialExtractionOutput, prompt, metrics)
            if isinstance(result, CredentialExtractionOutput):
                return result.credentials
            return []

        except Exception as e:
            self._log.warning(f"Credential extraction failed: {e}")
            return []

    # -------------------------------------------------------------------------
    # File Writing
    # -------------------------------------------------------------------------

    def _write_credential_files(
        self, state: ExportState, config: CredentialConfig
    ) -> ExportState:
        """Write all credential configuration files and update checklist."""
        ansible_path = state.get_ansible_path()

        self._write_credential_file(
            state,
            config.credential_types_yaml,
            Path(ansible_path)
            / "aap-configuration"
            / "controller_credential_types.yml",
            "AAP credential types configuration",
        )

        self._write_credential_file(
            state,
            config.credentials_yaml,
            Path(ansible_path) / "aap-configuration" / "controller_credentials.yml",
            "AAP credentials configuration",
        )

        self._write_credential_file(
            state,
            config.validate_tasks_yaml,
            Path(ansible_path) / "tasks" / "validate_credentials.yml",
            "Credential validation tasks",
        )

        return state

    def _write_credential_file(
        self,
        state: ExportState,
        content: str,
        file_path: Path,
        description: str,
    ) -> None:
        """Write a single credential file and update the checklist."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        self._log.info(f"Created: {file_path}")

        target_path_str = str(file_path)
        source_path = "N/A"

        assert state.checklist is not None, (
            "Checklist must exist before writing credential files"
        )

        updated = state.checklist.update_task(
            source_path=source_path,
            target_path=target_path_str,
            status=ChecklistStatus.COMPLETE,
            notes=description,
        )

        if not updated:
            state.checklist.add_task(
                category="credentials",
                source_path=source_path,
                target_path=target_path_str,
                status=ChecklistStatus.COMPLETE,
                description=description,
            )
            self._log.info(f"Added task to checklist: {target_path_str}")

        state.checklist.save(state.get_checklist_path())
