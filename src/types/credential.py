"""Credential management types for AAP credential configuration.

This module contains data types for extracting third-party credentials
from migration plans and generating AAP-style credential configuration files
(controller_credential_types.yml, controller_credentials.yml, validate_credentials.yml).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import yaml
from pydantic import BaseModel, Field


class CredentialField(BaseModel):
    """A single input field for an AAP credential type."""

    id: str = Field(
        description="Snake_case identifier for this field (e.g., 'api_token')"
    )
    type: str = Field(
        default="string",
        description="Field type: string or boolean",
    )
    label: str = Field(description="Human-readable label (e.g., 'API Token')")
    secret: bool = Field(
        default=False,
        description="Whether this field contains a secret value (passwords, keys, tokens)",
    )
    help_text: str = Field(
        default="",
        description="Help text describing this field",
    )


class ExtractedCredential(BaseModel):
    """A credential extracted from a migration plan's Credentials section."""

    name: str = Field(
        description="Human-readable credential name (e.g., 'CyberArk Conjur API')"
    )
    description: str = Field(
        default="",
        description="Description of what this credential is used for",
    )
    source_provider: str = Field(
        description="Original provider (e.g., 'cyberark_conjur', 'hashicorp_vault', 'chef_vault')",
    )
    fields: list[CredentialField] = Field(
        default_factory=list,
        description="List of credential input fields",
    )
    required_fields: list[str] = Field(
        default_factory=list,
        description="List of field IDs that are required",
    )
    usage_context: str = Field(
        default="",
        description="How this credential is used in the source code (e.g., 'database connection', 'API authentication')",
    )


class CredentialExtractionOutput(BaseModel):
    """LLM structured output for extracting credentials from migration plan."""

    credentials: list[ExtractedCredential] = Field(
        default_factory=list,
        description="List of credentials found in the migration plan's Credentials section",
    )


@dataclass(frozen=True)
class CredentialConfig:
    """Domain state carrying rendered AAP credential YAML and variable names.

    Generated deterministically from extracted credentials -- no LLM involved
    in the YAML rendering step.
    """

    credential_types_yaml: str
    credentials_yaml: str
    validate_tasks_yaml: str
    variable_names: tuple[str, ...]
    credentials: tuple[ExtractedCredential, ...]

    @classmethod
    def empty(cls) -> CredentialConfig:
        """Create an empty config indicating no credentials were found."""
        return cls(
            credential_types_yaml="",
            credentials_yaml="",
            validate_tasks_yaml="",
            variable_names=(),
            credentials=(),
        )

    @property
    def has_credentials(self) -> bool:
        """Check if any credentials were extracted."""
        return len(self.credentials) > 0

    @classmethod
    def from_extracted(
        cls,
        credentials: list[ExtractedCredential],
        module_name: str,
    ) -> CredentialConfig:
        """Build a CredentialConfig from extracted credentials.

        Renders the three YAML files deterministically using the AAP format.

        Args:
            credentials: List of extracted credentials from LLM
            module_name: Name of the module being migrated

        Returns:
            CredentialConfig with rendered YAML strings
        """
        if not credentials:
            return cls.empty()

        variable_names = _collect_variable_names(credentials)
        credential_types_yaml = _render_credential_types(credentials)
        credentials_yaml = _render_credentials(credentials, module_name)
        validate_tasks_yaml = _render_validate_tasks(variable_names)

        return cls(
            credential_types_yaml=credential_types_yaml,
            credentials_yaml=credentials_yaml,
            validate_tasks_yaml=validate_tasks_yaml,
            variable_names=tuple(variable_names),
            credentials=tuple(credentials),
        )


# ---------------------------------------------------------------------------
# YAML Rendering (pure functions)
# ---------------------------------------------------------------------------


def _collect_variable_names(credentials: list[ExtractedCredential]) -> list[str]:
    """Collect all variable names from credential fields."""
    return [field.id for cred in credentials for field in cred.fields]


def _render_credential_types(credentials: list[ExtractedCredential]) -> str:
    """Render controller_credential_types.yml content."""
    types = [_build_credential_type_entry(cred) for cred in credentials]

    content = str(
        yaml.dump(
            {"controller_credential_types": types},
            default_flow_style=False,
            sort_keys=False,
        )
    )

    # Inject !unsafe tags on injector values (yaml.dump cannot emit custom tags cleanly)
    content = _inject_unsafe_tags(content)

    return "---\n" + content


def _build_credential_type_entry(cred: ExtractedCredential) -> dict:
    """Build a single credential type entry for controller_credential_types.yml."""
    fields = [_build_field_entry(f) for f in cred.fields]

    injectors = {
        "extra_vars": {f.id: f"UNSAFE_PLACEHOLDER {{{{{f.id}}}}}" for f in cred.fields}
    }

    entry: dict = {
        "name": cred.name,
        "description": cred.description or f"Credential type for {cred.name}",
        "kind": "cloud",
        "inputs": {
            "fields": fields,
            "required": cred.required_fields or [f.id for f in cred.fields if f.secret],
        },
        "injectors": injectors,
    }

    return entry


def _build_field_entry(field: CredentialField) -> dict:
    """Build a single field entry for the inputs.fields list."""
    entry: dict = {
        "id": field.id,
        "type": field.type,
        "label": field.label,
    }

    if field.secret:
        entry["secret"] = True

    if field.help_text:
        entry["help_text"] = field.help_text

    return entry


def _inject_unsafe_tags(content: str) -> str:
    """Replace UNSAFE_PLACEHOLDER markers with !unsafe YAML tags.

    yaml.dump cannot emit custom tags on specific values, so we use a
    placeholder string and post-process. yaml.dump outputs the values
    unquoted, so we match without surrounding quotes.
    """
    return re.sub(
        r"UNSAFE_PLACEHOLDER \{\{(\w+)\}\}",
        r"!unsafe '{{ \1 }}'",
        content,
    )


def _render_credentials(
    credentials: list[ExtractedCredential], module_name: str
) -> str:
    """Render controller_credentials.yml content."""
    creds = [_build_credential_entry(cred, module_name) for cred in credentials]

    content = str(
        yaml.dump(
            {"controller_credentials": creds},
            default_flow_style=False,
            sort_keys=False,
        )
    )

    return "---\n" + content


def _build_credential_entry(cred: ExtractedCredential, module_name: str) -> dict:
    """Build a single credential entry for controller_credentials.yml."""
    inputs = {}
    for field in cred.fields:
        if field.secret:
            inputs[field.id] = "{{ " + f"vault_{field.id}" + " }}"
        else:
            inputs[field.id] = "{{ " + field.id + " }}"

    return {
        "name": f"{cred.name} - {module_name}",
        "description": cred.description or f"Credential for {module_name}",
        "organization": "Default",
        "credential_type": cred.name,
        "update_secrets": True,
        "inputs": inputs,
    }


def _render_validate_tasks(variable_names: list[str]) -> str:
    """Render tasks/validate_credentials.yml content."""
    tasks = [
        {
            "name": "Validate required credential variables are defined",
            "ansible.builtin.assert": {
                "that": [f"{var} is defined" for var in variable_names],
                "fail_msg": "One or more required credential variables are not defined. "
                "Ensure the AAP credential type is attached to the job template.",
                "quiet": True,
            },
        }
    ]

    content = str(
        yaml.dump(
            tasks,
            default_flow_style=False,
            sort_keys=False,
        )
    )

    return "---\n" + content
