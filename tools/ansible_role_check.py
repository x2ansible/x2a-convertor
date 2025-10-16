from pathlib import Path
from typing import Any
import sys
import tempfile

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

# Ansible Python API imports
from ansible import context
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.inventory.manager import InventoryManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager


class AnsibleRoleCheckInput(BaseModel):
    """Input schema for Ansible role validation tool."""

    ansible_role_path: str = Field(
        description="Path to Ansible role directory to validate (e.g., './ansible/nginx-multisite')"
    )


class AnsibleRoleCheckTool(BaseTool):
    """Tool to validate Ansible role by running it in check mode using ansible-playbook."""

    name: str = "ansible_role_check"
    description: str = (
        "Validates Ansible role by running ansible-playbook in check mode (dry-run). "
        "Uses Ansible's Python API to execute the role and catch all errors: "
        "playbook syntax, undefined variables, missing handlers, deprecated modules, etc. "
        "Returns validation results with errors found."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleRoleCheckInput

    # pyrefly: ignore
    def _run(self, ansible_role_path: str) -> str:
        """Validate Ansible role by running it in check mode."""
        role_path = Path(ansible_role_path)

        if not role_path.exists():
            return f"Error: Role path '{ansible_role_path}' does not exist"

        # Phase 1: Quick syntax check on task files
        syntax_errors = self._check_task_file_syntax(role_path)
        if syntax_errors:
            return syntax_errors

        role_name = role_path.name

        # Create minimal test playbook
        test_playbook = f"""---
- name: Test {role_name} role
  hosts: localhost
  connection: local
  gather_facts: no
  roles:
    - {role_name}
"""

        # Create temporary directory with test playbook and role symlink
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Write test playbook
            playbook_file = tmpdir_path / "test.yml"
            playbook_file.write_text(test_playbook)

            # Create roles directory and symlink to actual role
            roles_dir = tmpdir_path / "roles"
            roles_dir.mkdir()
            role_link = roles_dir / role_name
            role_link.symlink_to(role_path.absolute())

            # Create minimal inventory (localhost)
            inventory_content = "localhost ansible_connection=local ansible_python_interpreter=/usr/bin/python3"
            inventory_file = tmpdir_path / "inventory"
            inventory_file.write_text(inventory_content)

            # Initialize Ansible components
            loader = DataLoader()
            inventory = InventoryManager(loader=loader, sources=[str(inventory_file)])
            variable_manager = VariableManager(loader=loader, inventory=inventory)

            # Set context for check mode
            context.CLIARGS = ImmutableDict(
                check=True,  # Check mode (dry-run)
                verbosity=0,
                connection="local",
                become=None,
                become_method=None,
                become_user=None,
                module_path=None,
                forks=1,
                syntax=False,
                start_at_task=None,
                step=False,
                diff=False,
                tags=["all"],
                skip_tags=[],
            )

            # Redirect Ansible output
            old_stdout = sys.stdout
            old_stderr = sys.stderr

            try:
                # Create and run playbook executor
                pbex = PlaybookExecutor(
                    playbooks=[str(playbook_file)],
                    inventory=inventory,
                    variable_manager=variable_manager,
                    loader=loader,
                    passwords={},
                )

                # Run the playbook
                result = pbex.run()

                # result: 0 = success, non-zero = failure
                if result == 0:
                    return "Role validation passed (check mode execution successful)"
                else:
                    # Try to extract error messages from Ansible's output
                    # pyrefly: ignore
                    return self._format_errors(result, tmpdir_path)

            except Exception as e:
                # Catch any execution errors
                error_msg = str(e)

                # Parse and enhance common Ansible errors
                if "conflicting action statements" in error_msg:
                    if "hosts" in error_msg and "tasks" in error_msg:
                        return (
                            "Validation failed: PLAYBOOK SYNTAX IN ROLE FILES\n\n"
                            "Error: Task files contain playbook-level keywords (hosts, tasks)\n\n"
                            "Issue: Role task files are using playbook syntax instead of role syntax.\n"
                            "Task files should contain ONLY task definitions, not play definitions.\n\n"
                            "Wrong (playbook syntax):\n"
                            "  ---\n"
                            "  - name: My Play\n"
                            "    hosts: all\n"
                            "    tasks:\n"
                            "      - name: Do something\n"
                            "        ...\n\n"
                            "Correct (role syntax):\n"
                            "  ---\n"
                            "  - name: Do something\n"
                            "    ansible.builtin.module:\n"
                            "      ...\n\n"
                            f"Original error: {error_msg}"
                        )
                    else:
                        return (
                            f"Validation failed: CONFLICTING STATEMENTS\n\n{error_msg}"
                        )

                elif "is not defined" in error_msg:
                    return (
                        "Validation failed: UNDEFINED VARIABLE\n\n"
                        f"A variable is referenced but not defined in defaults/main.yml or vars/main.yml\n\n"
                        f"Error details: {error_msg}\n\n"
                        "Check that all {{ variable }} references match variables defined in defaults/main.yml"
                    )

                elif "No handler named" in error_msg or "handler" in error_msg.lower():
                    return (
                        "Validation failed: UNDEFINED HANDLER\n\n"
                        f"A handler is referenced with 'notify:' but not defined in handlers/main.yml\n\n"
                        f"Error details: {error_msg}\n\n"
                        "Check that handlers/main.yml exists and defines all referenced handlers"
                    )

                elif (
                    "has been removed" in error_msg or "deprecated" in error_msg.lower()
                ):
                    module_hint = ""
                    if "include" in error_msg.lower():
                        module_hint = "\n\nHint: Replace 'include:' with 'import_tasks:' or 'include_tasks:'"
                    return (
                        "Validation failed: DEPRECATED/REMOVED MODULE\n\n"
                        f"A module or action plugin has been removed from Ansible\n\n"
                        f"Error details: {error_msg}{module_hint}"
                    )

                elif "module" in error_msg.lower() and "not found" in error_msg.lower():
                    return (
                        "Validation failed: MODULE NOT FOUND\n\n"
                        f"An Ansible module doesn't exist or isn't installed\n\n"
                        f"Error details: {error_msg}\n\n"
                        "Check module names and ensure required collections are installed"
                    )

                else:
                    return f"Validation failed:\n\n{error_msg}"
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

    def _check_task_file_syntax(self, role_path: Path) -> str:
        """Check task files for common syntax issues before running the role."""
        tasks_dir = role_path / "tasks"
        if not tasks_dir.exists():
            return ""

        loader = DataLoader()
        errors = []

        for task_file in tasks_dir.glob("*.yml"):
            try:
                data = loader.load_from_file(str(task_file))
                rel_path = task_file.relative_to(role_path)

                if not data:
                    continue

                if isinstance(data, list):
                    for idx, item in enumerate(data, 1):
                        if isinstance(item, dict):
                            # Check for playbook-level keys
                            issues = []
                            if "hosts" in item:
                                issues.append("'hosts:' (playbook syntax)")
                            if "tasks" in item:
                                issues.append("'tasks:' wrapper (playbook syntax)")
                            if "become" in item and "name" not in item:
                                issues.append("'become:' at play level")

                            if issues:
                                errors.append(
                                    f"  - {rel_path}:{idx} contains {', '.join(issues)}"
                                )

                            # Check for deprecated/removed modules
                            if "include" in item:
                                errors.append(
                                    f"  - {rel_path}:{idx} uses deprecated 'include' "
                                    "(use 'import_tasks' or 'include_tasks')"
                                )

            except Exception as e:
                errors.append(
                    f"  - {task_file.relative_to(role_path)}: Parse error - {e}"
                )

        if errors:
            return (
                "Validation failed: SYNTAX ERRORS IN TASK FILES\n\n"
                "Found the following issues:\n" + "\n".join(errors) + "\n\n"
                "Fix these issues before the role can be validated.\n\n"
                "Common fixes:\n"
                "  - Remove 'hosts:', 'become:', 'tasks:' from task files (use role syntax)\n"
                "  - Replace 'include:' with 'import_tasks:' or 'include_tasks:'\n"
                "  - Ensure task files contain only task definitions"
            )

        return ""

    def _format_errors(self, return_code: int, tmpdir: Path) -> str:
        """Format error output from playbook execution"""
        # Check for common error indicators in the playbook directory
        errors = []

        # Generic failure message based on return code
        if return_code > 0:
            errors.append(
                "Playbook execution failed in check mode. "
                "This indicates issues with the role that would prevent it from running."
            )

        if errors:
            return "Validation failed:\n\n" + "\n".join(errors)
        else:
            return f"Validation failed with return code: {return_code}"
