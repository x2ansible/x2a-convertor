"""Tests for model utilities."""

from unittest.mock import patch

from src.model import DEFAULT_CONTEXT_WINDOW, get_context_window


class TestGetContextWindow:
    """Tests for get_context_window helper."""

    def test_returns_max_input_tokens_from_litellm(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o")
        with patch("src.model.litellm.get_model_info") as mock_info:
            mock_info.return_value = {"max_input_tokens": 128_000}
            assert get_context_window() == 128_000

    def test_falls_back_on_missing_key(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o")
        with patch("src.model.litellm.get_model_info") as mock_info:
            mock_info.return_value = {}
            assert get_context_window() == DEFAULT_CONTEXT_WINDOW

    def test_falls_back_on_exception(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "unknown/model")
        with patch("src.model.litellm.get_model_info", side_effect=Exception("boom")):
            assert get_context_window() == DEFAULT_CONTEXT_WINDOW

    def test_falls_back_on_none_value(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "openai/gpt-4o")
        with patch("src.model.litellm.get_model_info") as mock_info:
            mock_info.return_value = {"max_input_tokens": None}
            assert get_context_window() == DEFAULT_CONTEXT_WINDOW
