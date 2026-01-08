"""Pytest configuration and shared fixtures."""

import pytest

from src.config import reset_settings


@pytest.fixture(autouse=True)
def reset_config_settings():
    """Reset the settings singleton before and after each test.

    This ensures that environment variable changes made by monkeypatch
    are properly reflected in the settings, since pydantic-settings
    reads env vars at instantiation time.
    """
    reset_settings()
    yield
    reset_settings()
