"""Tests for deterministic Hiera-to-Ansible vars file generator."""

import json

import yaml

from src.exporters.hiera_vars_generator import HieraVarsGenerator


class TestTargetPath:
    """Test _target_path routing logic."""

    def test_common_level_goes_to_defaults(self, tmp_path):
        result = HieraVarsGenerator._target_path(
            "Common defaults", "data/common.yaml", tmp_path
        )
        assert result == tmp_path / "defaults" / "main.yml"

    def test_global_level_goes_to_defaults(self, tmp_path):
        result = HieraVarsGenerator._target_path(
            "Global settings", "data/global.yaml", tmp_path
        )
        assert result == tmp_path / "defaults" / "main.yml"

    def test_default_level_goes_to_defaults(self, tmp_path):
        result = HieraVarsGenerator._target_path(
            "Default values", "data/default.yaml", tmp_path
        )
        assert result == tmp_path / "defaults" / "main.yml"

    def test_os_level_goes_to_vars(self, tmp_path):
        result = HieraVarsGenerator._target_path(
            "OS family", "data/os/RedHat.yaml", tmp_path
        )
        assert result == tmp_path / "vars" / "RedHat.yml"

    def test_environment_level_goes_to_vars(self, tmp_path):
        result = HieraVarsGenerator._target_path(
            "Environment", "data/environment/production.yaml", tmp_path
        )
        assert result == tmp_path / "vars" / "production.yml"

    def test_node_level_goes_to_vars(self, tmp_path):
        result = HieraVarsGenerator._target_path(
            "Per-node data", "data/nodes/lb01.fra.example.com.yaml", tmp_path
        )
        assert result == tmp_path / "vars" / "lb01.fra.example.com.yml"


class TestDefaultRename:
    """Test _default_rename key transformation."""

    def test_strips_module_prefix(self):
        result = HieraVarsGenerator._default_rename(
            "profile_haproxy::package_name", "profile_haproxy", "profile_haproxy"
        )
        assert result == "haproxy_package_name"

    def test_strips_profile_prefix_from_module(self):
        result = HieraVarsGenerator._default_rename(
            "profile_haproxy::ssl_enabled", "profile_haproxy", "profile_haproxy"
        )
        assert result == "haproxy_ssl_enabled"

    def test_strips_role_prefix_from_module(self):
        result = HieraVarsGenerator._default_rename(
            "role_webserver::port", "role_webserver", "role_webserver"
        )
        assert result == "webserver_port"

    def test_different_prefix(self):
        result = HieraVarsGenerator._default_rename(
            "other_module::setting", "other_module", "other_module"
        )
        assert result == "other_module_setting"

    def test_nested_namespace(self):
        result = HieraVarsGenerator._default_rename(
            "some::deeply::nested::key", "some", "mymod"
        )
        assert result == "mymod_deeply::nested::key"

    def test_nested_namespace_no_prefix_match(self):
        result = HieraVarsGenerator._default_rename(
            "other::deeply::nested::key", "some", "mymod"
        )
        assert result == "mymod_key"

    def test_no_namespace(self):
        result = HieraVarsGenerator._default_rename("simple_key", "", "mymod")
        assert result == "mymod_simple_key"

    def test_hyphen_in_module_name(self):
        result = HieraVarsGenerator._default_rename(
            "my_mod::setting", "my_mod", "my-mod"
        )
        assert result == "my_mod_setting"


class TestDetectPrefix:
    """Test _detect_prefix."""

    def test_detects_puppet_prefix(self):
        data = {
            "profile_haproxy::package_name": "haproxy",
            "profile_haproxy::config_dir": "/etc/haproxy",
        }
        assert HieraVarsGenerator._detect_prefix(data) == "profile_haproxy"

    def test_no_prefix(self):
        data = {"simple_key": "value"}
        assert HieraVarsGenerator._detect_prefix(data) == ""

    def test_empty_dict(self):
        assert HieraVarsGenerator._detect_prefix({}) == ""


class TestTransform:
    """Test the _transform method (key renaming + filtering)."""

    def _make_generator(self):
        return HieraVarsGenerator.__new__(HieraVarsGenerator)

    def test_basic_transform(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()

        raw = str(
            yaml.dump(
                {
                    "profile_haproxy::package_name": "haproxy",
                    "profile_haproxy::config_dir": "/etc/haproxy",
                }
            )
        )
        mappings = [
            {
                "puppet_key": "profile_haproxy::package_name",
                "ansible_variable_name": "haproxy_package_name",
            },
            {
                "puppet_key": "profile_haproxy::config_dir",
                "ansible_variable_name": "haproxy_config_dir",
            },
        ]

        result = gen._transform(raw, mappings, "profile_haproxy")
        assert result is not None
        parsed = yaml.safe_load(result)
        assert parsed["haproxy_package_name"] == "haproxy"
        assert parsed["haproxy_config_dir"] == "/etc/haproxy"

    def test_skips_encrypted_values(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()

        raw = str(
            yaml.dump(
                {
                    "profile_haproxy::package_name": "haproxy",
                    "profile_haproxy::secret": "ENC[PKCS7,MIIBygExample]",
                }
            )
        )
        mappings = [
            {
                "puppet_key": "profile_haproxy::package_name",
                "ansible_variable_name": "haproxy_package_name",
            },
            {
                "puppet_key": "profile_haproxy::secret",
                "ansible_variable_name": "haproxy_secret",
            },
        ]

        result = gen._transform(raw, mappings, "profile_haproxy")
        parsed = yaml.safe_load(result)
        assert "haproxy_package_name" in parsed
        assert "haproxy_secret" not in parsed

    def test_skips_lookup_options(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()

        raw = str(
            yaml.dump(
                {
                    "profile_haproxy::package_name": "haproxy",
                    "lookup_options": {"profile_haproxy::backends": {"merge": "deep"}},
                }
            )
        )
        mappings = [
            {
                "puppet_key": "profile_haproxy::package_name",
                "ansible_variable_name": "haproxy_package_name",
            },
        ]

        result = gen._transform(raw, mappings, "profile_haproxy")
        parsed = yaml.safe_load(result)
        assert "haproxy_package_name" in parsed
        assert "lookup_options" not in parsed

    def test_empty_content_returns_none(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()
        assert gen._transform("", [], "mod") is None
        assert gen._transform("   \n  ", [], "mod") is None

    def test_non_dict_content_returns_none(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()
        assert gen._transform("- item1\n- item2\n", [], "mod") is None

    def test_all_encrypted_returns_none(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()

        raw = str(
            yaml.dump(
                {
                    "mod::secret1": "ENC[PKCS7,abc]",
                    "mod::secret2": "ENC[PKCS7,def]",
                }
            )
        )
        result = gen._transform(raw, [], "mod")
        assert result is None

    def test_fallback_rename_when_no_mapping(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()

        raw = str(yaml.dump({"profile_haproxy::unmapped_key": "value"}))
        result = gen._transform(raw, [], "profile_haproxy")
        parsed = yaml.safe_load(result)
        assert "haproxy_unmapped_key" in parsed

    def test_preserves_complex_values(self):
        gen = self._make_generator()
        gen._log = type("Log", (), {"warning": lambda self, msg: None})()

        raw = str(
            yaml.dump(
                {
                    "profile_haproxy::backends": {
                        "web": {"balance": "roundrobin", "port": 8080},
                        "api": {"balance": "leastconn", "port": 3000},
                    },
                }
            )
        )
        mappings = [
            {
                "puppet_key": "profile_haproxy::backends",
                "ansible_variable_name": "haproxy_backends",
            },
        ]

        result = gen._transform(raw, mappings, "profile_haproxy")
        parsed = yaml.safe_load(result)
        assert isinstance(parsed["haproxy_backends"], dict)
        assert parsed["haproxy_backends"]["web"]["balance"] == "roundrobin"
        assert parsed["haproxy_backends"]["api"]["port"] == 3000


class TestNormalizePath:
    def test_strips_dot_slash(self):
        assert (
            HieraVarsGenerator._normalize_path("./ansible/roles/foo")
            == "ansible/roles/foo"
        )

    def test_preserves_na(self):
        assert HieraVarsGenerator._normalize_path("N/A") == "N/A"

    def test_preserves_empty(self):
        assert HieraVarsGenerator._normalize_path("") == ""

    def test_no_dot_slash(self):
        assert (
            HieraVarsGenerator._normalize_path("ansible/roles/foo")
            == "ansible/roles/foo"
        )


class TestHieraVarsGeneratorIntegration:
    """Integration test using the full execute method with a real JSON file."""

    def test_generates_vars_files(self, tmp_path):
        module_path = tmp_path / "profile_haproxy"
        module_path.mkdir()

        hiera_data = [
            {
                "file_path": "data/common.yaml",
                "hierarchy_level": "Common defaults",
                "raw_content": yaml.dump(
                    {
                        "profile_haproxy::package_name": "haproxy",
                        "profile_haproxy::config_dir": "/etc/haproxy",
                    }
                ),
                "mappings": [
                    {
                        "puppet_key": "profile_haproxy::package_name",
                        "ansible_variable_name": "haproxy_package_name",
                        "ansible_target": "defaults/main.yml",
                        "value_type": "string",
                        "is_encrypted": False,
                    },
                    {
                        "puppet_key": "profile_haproxy::config_dir",
                        "ansible_variable_name": "haproxy_config_dir",
                        "ansible_target": "defaults/main.yml",
                        "value_type": "string",
                        "is_encrypted": False,
                    },
                ],
                "merge_behavior": {},
            },
            {
                "file_path": "data/os/RedHat.yaml",
                "hierarchy_level": "OS family",
                "raw_content": yaml.dump(
                    {
                        "profile_haproxy::firewall_provider": "firewalld",
                    }
                ),
                "mappings": [
                    {
                        "puppet_key": "profile_haproxy::firewall_provider",
                        "ansible_variable_name": "haproxy_firewall_provider",
                        "ansible_target": "vars/RedHat.yml",
                        "value_type": "string",
                        "is_encrypted": False,
                    },
                ],
                "merge_behavior": {},
            },
        ]

        json_path = tmp_path / "hiera-data-profile_haproxy.json"
        json_path.write_text(json.dumps(hiera_data))

        ansible_path = tmp_path / "ansible" / "roles" / "profile_haproxy"
        ansible_path.mkdir(parents=True)

        from unittest.mock import MagicMock

        state = MagicMock()
        state.module = "profile_haproxy"
        state.path = str(module_path)
        state.checklist = None

        def get_ansible_path():
            return str(ansible_path)

        state.get_ansible_path = get_ansible_path

        gen = HieraVarsGenerator.__new__(HieraVarsGenerator)
        gen._log = type(
            "Log",
            (),
            {
                "info": lambda self, msg: None,
                "warning": lambda self, msg: None,
            },
        )()

        gen.execute(state, metrics=None)

        defaults = ansible_path / "defaults" / "main.yml"
        assert defaults.exists()
        defaults_data = yaml.safe_load(defaults.read_text())
        assert defaults_data["haproxy_package_name"] == "haproxy"
        assert defaults_data["haproxy_config_dir"] == "/etc/haproxy"

        redhat_vars = ansible_path / "vars" / "RedHat.yml"
        assert redhat_vars.exists()
        redhat_data = yaml.safe_load(redhat_vars.read_text())
        assert redhat_data["haproxy_firewall_provider"] == "firewalld"
