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


class TestVariablesAsXml:
    """variables_as_xml must list every variable with a correct secret flag."""

    def test_renders_secret_flag_and_jinja_reference(self):
        cred = _credential_with_fields(
            CredentialField(id="db_user", label="Database Username", secret=False),
            CredentialField(id="db_password", label="Database Password", secret=True),
        )
        config = CredentialConfig.from_extracted([cred], module_name="myrole")

        xml = config.variables_as_xml()

        assert '<variable name="db_user" secret="false">{{ db_user }}</variable>' in xml
        assert (
            '<variable name="db_password" secret="true">{{ db_password }}</variable>'
            in xml
        )
        assert xml.startswith("<credential_variables>")
        assert xml.endswith("</credential_variables>")

    def test_empty_config_renders_empty_block(self):
        xml = CredentialConfig.empty().variables_as_xml()
        assert xml == "<credential_variables>\n\n</credential_variables>"
