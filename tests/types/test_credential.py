"""Tests for CredentialConfig secret-variable identification."""

from src.types.credential import (
    CredentialConfig,
    CredentialField,
    ExtractedCredential,
)


def _credential_with_fields(*fields: CredentialField) -> ExtractedCredential:
    return ExtractedCredential(
        name="App Database Authentication",
        source_provider="hiera",
        fields=list(fields),
    )


class TestSecretVariableNames:
    """secret_variable_names must return only fields marked secret."""

    def test_returns_only_secret_fields(self):
        cred = _credential_with_fields(
            CredentialField(id="db_user", label="Database Username", secret=False),
            CredentialField(id="db_password", label="Database Password", secret=True),
        )
        config = CredentialConfig.from_extracted([cred], module_name="myrole")

        assert config.secret_variable_names == ("db_password",)
        # full list still carries both, secret and non-secret
        assert set(config.variable_names) == {"db_user", "db_password"}

    def test_empty_when_no_secrets(self):
        cred = _credential_with_fields(
            CredentialField(id="db_user", label="Database Username", secret=False),
        )
        config = CredentialConfig.from_extracted([cred], module_name="myrole")

        assert config.secret_variable_names == ()

    def test_empty_config_has_no_secrets(self):
        assert CredentialConfig.empty().secret_variable_names == ()
