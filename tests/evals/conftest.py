"""Pytest configuration and fixtures for ansible_write evaluation tests."""

import pytest


@pytest.fixture(scope="session")
def test_model():
    """Get LLM model for testing.

    Uses the same model configuration as the main application.
    """
    from src.model import get_model

    return get_model()


@pytest.fixture
def eval_workspace(tmp_path):
    """Create isolated workspace for each test.

    Args:
        tmp_path: Pytest's temporary path fixture

    Returns:
        Path to isolated test workspace
    """
    workspace = tmp_path / "eval_workspace"
    workspace.mkdir()
    return workspace
