"""Tests for centralized configuration settings."""

from src.config import (
    AAPSettings,
    LLMSettings,
    LoggingSettings,
    MoleculeSettings,
    ProcessingSettings,
    Settings,
    get_settings,
    reset_settings,
)


class TestLLMSettings:
    """Tests for LLM configuration."""

    def test_default_values(self):
        settings = LLMSettings()
        assert settings.model == "openai/gpt-oss-120b-maas"
        assert settings.max_tokens == 8192
        assert settings.temperature == 0.1
        assert settings.reasoning_effort is None
        assert settings.rate_limit_requests is None

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "gpt-4")
        monkeypatch.setenv("MAX_TOKENS", "16384")
        monkeypatch.setenv("TEMPERATURE", "0.7")

        settings = LLMSettings()
        assert settings.model == "gpt-4"
        assert settings.max_tokens == 16384
        assert settings.temperature == 0.7


class TestAAPSettings:
    """Tests for AAP configuration."""

    def test_default_values(self):
        settings = AAPSettings()
        assert settings.controller_url is None
        assert settings.org_name is None
        assert settings.api_prefix == "/api/controller/v2"
        assert settings.verify_ssl is True
        assert settings.timeout_s == 30.0

    def test_is_enabled(self, monkeypatch):
        settings = AAPSettings()
        assert settings.is_enabled() is False

        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example.com")
        settings = AAPSettings()
        assert settings.is_enabled() is True

    def test_api_prefix_normalized(self, monkeypatch):
        monkeypatch.setenv("AAP_API_PREFIX", "/api/v2/")

        settings = AAPSettings()
        assert settings.api_prefix == "/api/v2"

    def test_validate_config_missing_org(self, monkeypatch):
        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example.com")

        settings = AAPSettings()
        errors = settings.validate_config()
        assert any("AAP_ORG_NAME" in e for e in errors)

    def test_validate_config_missing_auth(self, monkeypatch):
        monkeypatch.setenv("AAP_CONTROLLER_URL", "https://aap.example.com")
        monkeypatch.setenv("AAP_ORG_NAME", "Default")

        settings = AAPSettings()
        errors = settings.validate_config()
        assert any("Auth required" in e for e in errors)


class TestProcessingSettings:
    """Tests for processing configuration."""

    def test_default_values(self):
        settings = ProcessingSettings()
        assert settings.recursion_limit == 500
        assert settings.max_write_attempts == 10
        assert settings.max_validation_attempts == 5

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("RECURSION_LIMIT", "1000")
        monkeypatch.setenv("MAX_WRITE_ATTEMPTS", "20")

        settings = ProcessingSettings()
        assert settings.recursion_limit == 1000
        assert settings.max_write_attempts == 20


class TestLoggingSettings:
    """Tests for logging configuration."""

    def test_default_values(self):
        settings = LoggingSettings()
        assert settings.debug_all is False
        assert settings.log_level == "INFO"

    def test_log_level_uppercase(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "debug")

        settings = LoggingSettings()
        assert settings.log_level == "DEBUG"


class TestMoleculeSettings:
    """Tests for Molecule configuration."""

    def test_default_values(self):
        settings = MoleculeSettings()
        assert (
            settings.docker_image
            == "docker.io/geerlingguy/docker-fedora40-ansible:latest"
        )

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MOLECULE_DOCKER_IMAGE", "custom/image:latest")

        settings = MoleculeSettings()
        assert settings.docker_image == "custom/image:latest"


class TestSettings:
    """Tests for root Settings class."""

    def test_has_all_nested_settings(self):
        settings = Settings()
        assert isinstance(settings.llm, LLMSettings)
        assert isinstance(settings.aap, AAPSettings)
        assert isinstance(settings.processing, ProcessingSettings)
        assert isinstance(settings.logging, LoggingSettings)
        assert isinstance(settings.molecule, MoleculeSettings)

    def test_nested_values_accessible(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL", "test-model")
        monkeypatch.setenv("RECURSION_LIMIT", "999")

        settings = Settings()
        assert settings.llm.model == "test-model"
        assert settings.processing.recursion_limit == 999


class TestGetSettings:
    """Tests for the get_settings singleton function."""

    def test_returns_settings_instance(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_singleton_pattern(self):
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_reset_clears_singleton(self):
        settings1 = get_settings()
        reset_settings()
        settings2 = get_settings()
        assert settings1 is not settings2

    def test_env_changes_after_reset(self, monkeypatch):
        # Get initial settings
        settings1 = get_settings()
        original_model = settings1.llm.model

        # Change env and reset
        monkeypatch.setenv("LLM_MODEL", "changed-model")
        reset_settings()

        # New settings should reflect env change
        settings2 = get_settings()
        assert settings2.llm.model == "changed-model"
        assert settings2.llm.model != original_model
