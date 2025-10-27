"""Value object for Ansible module/role names.

This module provides a type-safe, self-validating representation of Ansible
module names that automatically handles sanitization according to Ansible rules.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AnsibleModule:
    """Immutable value object representing an Ansible module/role name.

    Ansible role names must follow the pattern ^[a-z][a-z0-9_]*$:
    - Only lowercase letters, numbers, and underscores
    - Must start with a letter

    This class automatically sanitizes the input name to comply with these rules.

    Attributes:
        raw_name: The original, unsanitized module name
        sanitized_name: The Ansible-compliant sanitized name

    Example:
        >>> module = AnsibleModule("My-Module-Name")
        >>> str(module)
        'my_module_name'
        >>> module.sanitized_name
        'my_module_name'
    """

    raw_name: str
    sanitized_name: str

    def __init__(self, name: str):
        """Create an AnsibleModule with automatic sanitization.

        Args:
            name: Raw module name to sanitize
        """
        # Use object.__setattr__ to bypass frozen dataclass
        object.__setattr__(self, "raw_name", name)
        object.__setattr__(self, "sanitized_name", self._sanitize(name))

    @staticmethod
    def _sanitize(name: str) -> str:
        """Sanitize module name to be ansible-lint compliant.

        Args:
            name: Raw module name

        Returns:
            Sanitized name following Ansible rules
        """
        # Replace hyphens with underscores
        sanitized = name.replace("-", "_")
        # Convert to lowercase
        sanitized = sanitized.lower()
        # Remove any other invalid characters
        sanitized = "".join(c for c in sanitized if c.isalnum() or c == "_")
        # Ensure it starts with a letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = "role_" + sanitized
        return sanitized

    def __str__(self) -> str:
        """Return the sanitized module name.

        Returns:
            Sanitized Ansible-compliant name
        """
        return self.sanitized_name

    def __repr__(self) -> str:
        """Return a developer-friendly representation.

        Returns:
            String representation showing both raw and sanitized names
        """
        if self.raw_name == self.sanitized_name:
            return f"AnsibleModule('{self.sanitized_name}')"
        return f"AnsibleModule('{self.raw_name}' -> '{self.sanitized_name}')"
