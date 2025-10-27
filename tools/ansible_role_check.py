import json
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# Ansible Python API imports
from ansible import context
from ansible.errors import AnsibleError, AnsibleParserError
from ansible.inventory.manager import InventoryManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.playbook.play import Play
from ansible.playbook.role.definition import RoleDefinition
from ansible.vars.manager import VariableManager

from src.utils.logging import get_logger

logger = get_logger(__name__)


def ensure_ansible_builtin_collection():
    """
    Ensure ansible.builtin collection exists by creating symlinks if missing.

    This is needed because ansible.builtin is not a real collection in ansible-core,
    but tasks using FQCN (e.g., ansible.builtin.service) require it to exist.

    This function creates the necessary symlinks from ansible_collections/ansible/builtin
    to the core ansible modules and plugins directories.
    """
    try:
        # Find ansible_collections directory in site-packages
        import ansible_collections

        collections_path = Path(ansible_collections.__path__[0])
        builtin_path = collections_path / "ansible" / "builtin"

        # Check if builtin collection already exists
        if builtin_path.exists() and (builtin_path / "plugins").exists():
            logger.debug("ansible.builtin collection already exists")
            return

        # Create builtin collection directory
        builtin_path.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Created ansible.builtin collection directory at {builtin_path}")

        # Find ansible core modules and plugins
        import ansible

        ansible_path = Path(ansible.__path__[0])

        # Create symlinks to modules and plugins
        modules_link = builtin_path / "modules"
        plugins_link = builtin_path / "plugins"

        if not modules_link.exists():
            modules_link.symlink_to(ansible_path / "modules")
            logger.debug(f"Created modules symlink: {modules_link}")

        if not plugins_link.exists():
            plugins_link.symlink_to(ansible_path / "plugins")
            logger.debug(f"Created plugins symlink: {plugins_link}")

        # Create minimal MANIFEST.json
        manifest_file = builtin_path / "MANIFEST.json"
        if not manifest_file.exists():
            manifest = {
                "collection_info": {
                    "namespace": "ansible",
                    "name": "builtin",
                    "version": "1.0.0",
                    "authors": ["Ansible Core Team"],
                }
            }
            manifest_file.write_text(json.dumps(manifest, indent=2))
            logger.debug(f"Created MANIFEST.json at {manifest_file}")

        logger.info("ansible.builtin collection setup completed")

    except Exception as e:
        logger.warning(f"Failed to setup ansible.builtin collection: {e}")
        # Don't fail - let Ansible try to resolve modules anyway


class AnsibleRoleCheckInput(BaseModel):
    """Input schema for Ansible role validation tool."""

    ansible_role_path: str = Field(
        description="Path to Ansible role directory to validate (e.g., './ansible/nginx-multisite')"
    )


class AnsibleRoleCheckTool(BaseTool):
    """Tool to validate Ansible role using Ansible's role loading validation."""

    name: str = "ansible_role_check"
    description: str = (
        "Validates Ansible role structure and syntax using Ansible's Python API. "
        "Performs full validation without execution: YAML syntax, task structure, "
        "module parameters, handler definitions, template references, role dependencies, etc. "
        "Returns validation results with specific errors or confirmation of valid role."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleRoleCheckInput

    # pyrefly: ignore
    def _run(self, ansible_role_path: str) -> str:
        """Validate Ansible role using Ansible's role loading mechanism."""
        role_path = Path(ansible_role_path)
        logger.debug(f"AnsibleRoleCheckTool validating {ansible_role_path}")

        if not role_path.exists():
            return f"ERROR: Role path '{ansible_role_path}' does not exist"

        if not role_path.is_dir():
            return f"ERROR: Role path '{ansible_role_path}' is not a directory"

        # Ensure ansible.builtin collection exists (needed for FQCN resolution)
        ensure_ansible_builtin_collection()

        role_name = role_path.name

        try:
            # Initialize Ansible context with minimal configuration
            # This allows builtin modules to be resolved properly
            context.CLIARGS = ImmutableDict(
                check=False,  # Not executing, just validating
                verbosity=0,
                connection="local",
                module_path=None,
                become=None,
                become_method=None,
                become_user=None,
                collections_path=[],  # Use default collections paths
            )

            # Initialize Ansible components for context (no execution)
            loader = DataLoader()

            # Create minimal in-memory inventory (localhost only)
            inventory = InventoryManager(loader=loader, sources="localhost,")
            variable_manager = VariableManager(loader=loader, inventory=inventory)

            # Create a minimal play context for role loading
            # This provides the context Ansible needs to validate the role structure
            play_ds = {
                "name": f"Validate {role_name} role",
                "hosts": "localhost",
                "gather_facts": False,
                "roles": [{"role": str(role_path.absolute())}],
            }

            # Load the play - this triggers Ansible's validation
            # It will parse and validate:
            # - Role structure (tasks, handlers, defaults, vars, meta)
            # - Task syntax and module parameters
            # - Handler definitions
            # - Template references
            # - Role dependencies in meta/main.yml
            play = Play.load(
                play_ds,
                variable_manager=variable_manager,
                loader=loader,
            )

            # If we get here, the role loaded successfully
            # This means Ansible validated all the structure
            logger.info(f"Role '{role_name}' passed validation")
            return f"Role validation passed: All tasks, handlers, and role structure are valid."

        except AnsibleParserError as e:
            # YAML syntax errors, malformed tasks, etc.
            error_msg = str(e)
            logger.error(f"Parser error in role '{role_name}': {error_msg}")
            return (
                f"ERROR: Role validation failed (parser error):\n```\n{error_msg}\n```"
            )

        except AnsibleError as e:
            # General Ansible errors: undefined vars, missing files, invalid module params, etc.
            error_msg = str(e)
            logger.error(f"Validation error in role '{role_name}': {error_msg}")
            return f"ERROR: Role validation failed:\n```\n{error_msg}\n```"

        except Exception as e:
            # Catch-all for unexpected errors
            error_msg = str(e)
            logger.error(f"Unexpected error validating role '{role_name}': {error_msg}")
            return f"ERROR: Unexpected validation error:\n```\n{error_msg}\n```"
