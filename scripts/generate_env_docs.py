#!/usr/bin/env python3
"""Generate environment variable documentation from pydantic-settings."""

import sys
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import SecretStr
from pydantic.fields import FieldInfo

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.settings import (  # noqa: E402
    AAPSettings,
    AWSSettings,
    GitHubSettings,
    LLMSettings,
    LoggingSettings,
    MoleculeSettings,
    OpenAISettings,
    ProcessingSettings,
)

# Settings classes with their display name and env_prefix
# Using Any for the class type to avoid pyrefly issues with pydantic models
SETTINGS_CLASSES: list[tuple[str, Any, str]] = [
    ("LLM", LLMSettings, ""),
    ("OpenAI", OpenAISettings, "OPENAI_"),
    ("AWS Bedrock", AWSSettings, "AWS_"),
    ("Ansible Automation Platform", AAPSettings, "AAP_"),
    ("GitHub", GitHubSettings, "GITHUB_"),
    ("Processing", ProcessingSettings, ""),
    ("Logging", LoggingSettings, ""),
    ("Molecule Testing", MoleculeSettings, ""),
]


def get_env_var_name(field_name: str, field_info: FieldInfo, env_prefix: str) -> str:
    """Determine the environment variable name for a field."""
    # Check for validation_alias first (used for fields without prefix)
    if field_info.validation_alias:
        alias = field_info.validation_alias
        # Handle AliasPath or string
        if isinstance(alias, str):
            return alias
        return str(alias)
    # Otherwise use prefix + field name in uppercase
    return f"{env_prefix}{field_name.upper()}"


def get_type_string(annotation: Any) -> str:
    """Convert a type annotation to a readable string."""
    if annotation is None:
        return "string"

    # Handle SecretStr
    if annotation is SecretStr:
        return "secret"

    # Handle Optional types (Union with None)
    origin = get_origin(annotation)
    if origin is not None:
        args = get_args(annotation)
        # Check for Optional (Union[X, None])
        if type(None) in args:
            # Get the non-None type
            non_none_types = [a for a in args if a is not type(None)]
            if non_none_types:
                return get_type_string(non_none_types[0])

    # Handle basic types
    if annotation is str:
        return "string"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "float"
    if annotation is bool:
        return "boolean"

    # Handle Literal types
    if origin is not None and str(origin) == "typing.Literal":
        args = get_args(annotation)
        return f"enum: {', '.join(repr(a) for a in args)}"

    # Fallback
    return (
        str(annotation).replace("typing.", "").replace("<class '", "").replace("'>", "")
    )


def get_default_string(default: Any, type_str: str) -> str:
    """Format the default value for display."""
    if default is None:
        return "-"
    if type_str == "secret":
        # Don't show actual secret defaults
        if isinstance(default, SecretStr):
            val = default.get_secret_value()
            if val and val != "not-needed":
                return "`***`"
            return f"`{val}`"
        return "`***`"
    if isinstance(default, bool):
        return f"`{str(default).lower()}`"
    if isinstance(default, str):
        return f"`{default}`"
    if isinstance(default, (int, float)):
        return f"`{default}`"
    return f"`{default}`"


def generate_env_docs(
    output_file: str = "docs/configuration_options.md",
) -> None:
    """Generate markdown documentation for environment variables."""
    lines: list[str] = []

    # Jekyll frontmatter
    lines.append("---")
    lines.append("layout: default")
    lines.append("title: Configuration Options")
    lines.append("nav_order: 4")
    lines.append("---")
    lines.append("")
    lines.append("# Environment Variables")
    lines.append("{: .no_toc }")
    lines.append("")
    lines.append("Auto-generated from `src/config/settings.py`.")
    lines.append("{: .fs-3 .text-grey-dk-000 }")
    lines.append("")
    lines.append("## Table of contents")
    lines.append("{: .no_toc .text-delta }")
    lines.append("")
    lines.append("* TOC")
    lines.append("{:toc}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Generate tables for each settings class
    for category_name, settings_class, env_prefix in SETTINGS_CLASSES:
        lines.append(f"## {category_name} Configuration")
        lines.append("")
        lines.append("| Variable | Type | Default | Description |")
        lines.append("|----------|------|---------|-------------|")

        # Get fields from the pydantic model
        for field_name, field_info in settings_class.model_fields.items():
            # Skip private fields
            if field_name.startswith("_"):
                continue

            env_var = get_env_var_name(field_name, field_info, env_prefix)
            type_str = get_type_string(field_info.annotation)
            default_str = get_default_string(field_info.default, type_str)
            description = field_info.description or "-"

            lines.append(
                f"| `{env_var}` | {type_str} | {default_str} | {description} |"
            )

        lines.append("")

    # Write to file
    output_path = project_root / output_file
    output_path.write_text("\n".join(lines))
    print(f"Environment variable documentation generated at: {output_file}")


if __name__ == "__main__":
    generate_env_docs()
