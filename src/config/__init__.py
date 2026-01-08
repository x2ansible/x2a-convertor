"""Configuration module for x2a-convertor.

This module provides centralized, type-safe configuration management
using pydantic-settings with environment variable loading.

Usage:
    from src.config import get_settings

    settings = get_settings()

    # Access LLM settings
    model = settings.llm.model
    max_tokens = settings.llm.max_tokens

    # Access processing settings
    recursion_limit = settings.processing.recursion_limit

    # Access sensitive values (use .get_secret_value() for actual value)
    api_key = settings.openai.api_key.get_secret_value()
"""

from src.config.settings import (
    AAPSettings,
    AWSSettings,
    GitHubSettings,
    LLMSettings,
    LoggingSettings,
    MoleculeSettings,
    OpenAISettings,
    ProcessingSettings,
    Settings,
    get_settings,
    reset_settings,
)

__all__ = [
    "AAPSettings",
    "AWSSettings",
    "GitHubSettings",
    "LLMSettings",
    "LoggingSettings",
    "MoleculeSettings",
    "OpenAISettings",
    "ProcessingSettings",
    "Settings",
    "get_settings",
    "reset_settings",
]
