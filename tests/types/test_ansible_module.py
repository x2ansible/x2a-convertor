"""Tests for AnsibleModule value object."""

import pytest

from src.types import AnsibleModule


class TestAnsibleModule:
    """Tests for AnsibleModule value object."""

    def test_simple_lowercase_name(self):
        """Test that simple lowercase names pass through unchanged."""
        module = AnsibleModule("mymodule")
        assert str(module) == "mymodule"
        assert module.sanitized_name == "mymodule"
        assert module.raw_name == "mymodule"

    def test_uppercase_converted_to_lowercase(self):
        """Test that uppercase letters are converted to lowercase."""
        module = AnsibleModule("MyModule")
        assert str(module) == "mymodule"
        assert module.sanitized_name == "mymodule"
        assert module.raw_name == "MyModule"

    def test_hyphens_converted_to_underscores(self):
        """Test that hyphens are converted to underscores."""
        module = AnsibleModule("my-module-name")
        assert str(module) == "my_module_name"
        assert module.sanitized_name == "my_module_name"

    def test_mixed_case_with_hyphens(self):
        """Test combined uppercase and hyphen sanitization."""
        module = AnsibleModule("My-Module-Name")
        assert str(module) == "my_module_name"

    def test_invalid_characters_removed(self):
        """Test that invalid characters are removed."""
        module = AnsibleModule("my@module#name!")
        assert str(module) == "mymodulename"

    def test_numbers_allowed(self):
        """Test that numbers are allowed in module names."""
        module = AnsibleModule("mymodule123")
        assert str(module) == "mymodule123"

    def test_underscores_preserved(self):
        """Test that underscores are preserved."""
        module = AnsibleModule("my_module_name")
        assert str(module) == "my_module_name"

    def test_starts_with_number_adds_prefix(self):
        """Test that names starting with numbers get 'role_' prefix."""
        module = AnsibleModule("123module")
        assert str(module) == "role_123module"
        assert module.sanitized_name.startswith("role_")

    def test_starts_with_underscore_adds_prefix(self):
        """Test that names starting with underscore get 'role_' prefix."""
        module = AnsibleModule("_module")
        assert str(module) == "role__module"

    def test_complex_sanitization(self):
        """Test complex sanitization with multiple issues."""
        module = AnsibleModule("My-Complex@Module#123!")
        assert str(module) == "my_complexmodule123"

    def test_immutability(self):
        """Test that AnsibleModule is immutable (frozen dataclass)."""
        from dataclasses import FrozenInstanceError

        module = AnsibleModule("test")
        with pytest.raises(FrozenInstanceError):
            module.sanitized_name = "changed"  # pyrefly: ignore

    def test_str_returns_sanitized_name(self):
        """Test that str() returns the sanitized name."""
        module = AnsibleModule("My-Module")
        assert str(module) == "my_module"
        assert str(module) == module.sanitized_name

    def test_repr_shows_transformation(self):
        """Test that repr() shows both raw and sanitized names when different."""
        module = AnsibleModule("My-Module")
        repr_str = repr(module)
        assert "My-Module" in repr_str
        assert "my_module" in repr_str
        assert "->" in repr_str

    def test_repr_simple_when_no_change(self):
        """Test that repr() is simple when no sanitization needed."""
        module = AnsibleModule("mymodule")
        repr_str = repr(module)
        assert repr_str == "AnsibleModule('mymodule')"
        assert "->" not in repr_str

    def test_empty_string_handling(self):
        """Test handling of empty string."""
        module = AnsibleModule("")
        assert str(module) == ""

    def test_only_invalid_characters(self):
        """Test string with only invalid characters."""
        module = AnsibleModule("@#$%")
        assert str(module) == ""

    def test_real_world_chef_cookbook_name(self):
        """Test real-world Chef cookbook name conversion."""
        module = AnsibleModule("chef-server")
        assert str(module) == "chef_server"

    def test_real_world_complex_name(self):
        """Test real-world complex module name."""
        module = AnsibleModule("AWS-EC2-Instance-123")
        assert str(module) == "aws_ec2_instance_123"

    def test_equality(self):
        """Test that two modules with same name are equal."""
        module1 = AnsibleModule("my-module")
        module2 = AnsibleModule("my_module")  # Different raw, same sanitized
        # Both should have same sanitized name
        assert str(module1) == str(module2)
        assert module1.sanitized_name == module2.sanitized_name

    def test_use_in_string_formatting(self):
        """Test that module can be used in f-strings."""
        module = AnsibleModule("My-Module")
        result = f"Role name: {module}"
        assert result == "Role name: my_module"

    def test_use_in_path_construction(self):
        """Test that module works well in path construction."""
        module = AnsibleModule("My-Module")
        path = f"./ansible/{module}"
        assert path == "./ansible/my_module"
