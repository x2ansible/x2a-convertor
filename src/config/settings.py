"""Centralized configuration management using pydantic-settings.

This module provides type-safe configuration with environment variable loading,
validation, and sensible defaults for all x2a-convertor settings.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    model: str = Field(
        default="openai/gpt-oss-120b-maas",
        validation_alias="LLM_MODEL",
        description="Language model to use",
    )
    max_tokens: int = Field(
        default=8192,
        validation_alias="MAX_TOKENS",
        description="Maximum tokens for LLM responses",
    )
    temperature: float = Field(
        default=0.1,
        validation_alias="TEMPERATURE",
        description="Model temperature (creativity)",
    )
    reasoning_effort: str | None = Field(
        default=None,
        validation_alias="REASONING_EFFORT",
        description="Claude reasoning effort level",
    )
    rate_limit_requests: int | None = Field(
        default=None,
        validation_alias="RATE_LIMIT_REQUESTS",
        description="Rate limit requests per second",
    )


class OpenAISettings(BaseSettings):
    """OpenAI-specific configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_", extra="ignore")

    api_base: str | None = Field(
        default=None,
        description="OpenAI/compatible API endpoint",
    )
    api_key: SecretStr = Field(
        default=SecretStr("not-needed"),
        description="API key for OpenAI provider",
    )


class AWSSettings(BaseSettings):
    """AWS Bedrock configuration."""

    model_config = SettingsConfigDict(env_prefix="AWS_", extra="ignore")

    bearer_token_bedrock: SecretStr | None = Field(
        default=None,
        description="AWS Bedrock bearer token",
    )
    access_key_id: SecretStr | None = Field(
        default=None,
        description="AWS access key ID",
    )
    secret_access_key: SecretStr | None = Field(
        default=None,
        description="AWS secret access key",
    )
    session_token: SecretStr | None = Field(
        default=None,
        description="AWS session token (temporary credentials)",
    )
    region: str = Field(
        default="eu-west-2",
        description="AWS region for Bedrock",
    )


class AAPSettings(BaseSettings):
    """Ansible Automation Platform configuration."""

    model_config = SettingsConfigDict(env_prefix="AAP_", extra="ignore")

    controller_url: str | None = Field(
        default=None,
        description="AAP Controller base URL",
    )
    org_name: str | None = Field(
        default=None,
        description="Organization name",
    )
    api_prefix: str = Field(
        default="/api/controller/v2",
        description="API path prefix",
    )
    oauth_token: SecretStr | None = Field(
        default=None,
        description="OAuth token for auth",
    )
    username: str | None = Field(
        default=None,
        description="Username for basic auth",
    )
    password: SecretStr | None = Field(
        default=None,
        description="Password for basic auth",
    )
    ca_bundle: str | None = Field(
        default=None,
        description="Path to CA certificate",
    )
    verify_ssl: bool = Field(
        default=True,
        description="SSL verification flag",
    )
    timeout_s: float = Field(
        default=30.0,
        description="Request timeout in seconds",
    )
    project_name: str | None = Field(
        default=None,
        description="Project name in AAP",
    )
    scm_credential_id: int | None = Field(
        default=None,
        description="Credential ID for private repos",
    )

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, v: str) -> str:
        return v.rstrip("/")

    def is_enabled(self) -> bool:
        """Check if AAP integration is enabled (controller_url is set)."""
        return bool(self.controller_url)

    def validate_config(self) -> list[str]:
        """Validate configuration and return list of errors.

        Returns:
            List of validation error messages. Empty list means valid.
        """
        if not self.controller_url:
            return []

        errors: list[str] = []

        if not self.org_name:
            errors.append("AAP_ORG_NAME is required when AAP_CONTROLLER_URL is set")

        if not self.api_prefix.startswith("/"):
            errors.append("AAP_API_PREFIX must start with '/', e.g. /api/controller/v2")

        if self.ca_bundle:
            ca_path_obj = Path(self.ca_bundle)
            if not ca_path_obj.exists():
                errors.append(f"AAP_CA_BUNDLE file does not exist: {self.ca_bundle}")
            elif not ca_path_obj.is_file():
                errors.append(f"AAP_CA_BUNDLE is not a file: {self.ca_bundle}")

        if not self.oauth_token and not (self.username and self.password):
            errors.append(
                "Auth required: set AAP_OAUTH_TOKEN or AAP_USERNAME + AAP_PASSWORD"
            )

        return errors


class GitHubSettings(BaseSettings):
    """GitHub integration configuration."""

    model_config = SettingsConfigDict(env_prefix="GITHUB_", extra="ignore")

    token: SecretStr | None = Field(
        default=None,
        description="GitHub API authentication token",
    )
    api_base: str = Field(
        default="https://api.github.com",
        description="GitHub API base URL",
    )

    @field_validator("api_base")
    @classmethod
    def normalize_api_base(cls, v: str) -> str:
        return v.rstrip("/")


class ProcessingSettings(BaseSettings):
    """Processing limits configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    recursion_limit: int = Field(
        default=500,
        validation_alias="RECURSION_LIMIT",
        description="Maximum recursion limit for LLM calls",
    )
    max_write_attempts: int = Field(
        default=10,
        validation_alias="MAX_WRITE_ATTEMPTS",
        description="Maximum number of attempts to write all files from checklist",
    )
    max_validation_attempts: int = Field(
        default=5,
        validation_alias="MAX_VALIDATION_ATTEMPTS",
        description="Maximum number of attempts to fix validation errors",
    )


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    debug_all: bool = Field(
        default=False,
        validation_alias="DEBUG_ALL",
        description="Enable debug logging for all libraries",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Log level for x2convertor namespace",
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        if isinstance(v, str):
            return v.upper()
        return v


class MoleculeSettings(BaseSettings):
    """Molecule testing configuration."""

    model_config = SettingsConfigDict(extra="ignore")

    docker_image: str = Field(
        default="docker.io/geerlingguy/docker-fedora40-ansible:latest",
        validation_alias="MOLECULE_DOCKER_IMAGE",
        description="Docker image for Molecule tests",
    )


class Settings(BaseSettings):
    """Root settings class with all nested configurations.

    Usage:
        from src.config import get_settings

        settings = get_settings()
        model = settings.llm.model
        max_tokens = settings.llm.max_tokens
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    aws: AWSSettings = Field(default_factory=AWSSettings)
    aap: AAPSettings = Field(default_factory=AAPSettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    molecule: MoleculeSettings = Field(default_factory=MoleculeSettings)


# Singleton pattern for settings
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the global settings instance.

    Returns:
        The singleton Settings instance with all configuration loaded.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings singleton (useful for testing)."""
    global _settings
    _settings = None
