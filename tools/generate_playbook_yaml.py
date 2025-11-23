"""Tool for generating Ansible playbook YAML files."""

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from tools.ansible_write import AnsibleWriteTool

logger = get_logger(__name__)


class GeneratePlaybookYAMLInput(BaseModel):
    """Input schema for generating playbook YAML."""

    file_path: str = Field(description="Output file path")
    name: str = Field(description="Playbook name")
    role_name: str = Field(description="Role name to use")
    hosts: str = Field(default="all", description="Target hosts")
    become: bool = Field(default=False, description="Use privilege escalation")
    vars: dict[str, Any] = Field(
        default_factory=dict, description="Variables for role"
    )


class GeneratePlaybookYAMLTool(BaseTool):
    """Generate Ansible playbook YAML that uses a role."""

    name: str = "generate_playbook_yaml"
    description: str = (
        "Generate Ansible playbook YAML that uses a role. "
        "Creates a playbook file with the specified role."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = (
        GeneratePlaybookYAMLInput
    )

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._ansible_write = AnsibleWriteTool()

    def _run(
        self,
        file_path: str,
        name: str,
        role_name: str,
        hosts: str = "all",
        become: bool = False,
        vars: dict[str, Any] = None,
    ) -> str:
        """Generate playbook YAML file."""
        logger.info(f"Generating playbook YAML: {name}")

        if vars is None:
            vars = {}

        if not role_name:
            return "ERROR: role_name is required for playbook generation"

        try:
            playbook_lines = ["---"]
            playbook_lines.append(f"- name: {name}")
            playbook_lines.append(f"  hosts: {hosts}")

            if become:
                playbook_lines.append("  become: true")

            if vars:
                playbook_lines.append("  vars:")
                for key, value in vars.items():
                    if isinstance(value, str):
                        playbook_lines.append(f"    {key}: '{value}'")
                    else:
                        playbook_lines.append(f"    {key}: {value}")

            playbook_lines.append("  roles:")
            playbook_lines.append(f"    - {role_name}")

            playbook_content = "\n".join(playbook_lines)

            result = self._ansible_write._run(
                file_path=file_path, yaml_content=playbook_content
            )

            if result.startswith("Successfully"):
                logger.info(f"Successfully generated playbook YAML: {file_path}")
                return (
                    f"Successfully generated playbook YAML at {file_path}\n"
                    f"Playbook: {name}\n"
                    f"Role: {role_name}\n"
                    f"Hosts: {hosts}"
                )
            else:
                return f"ERROR: Failed to generate playbook: {result}"

        except Exception as e:
            error_msg = f"ERROR: Failed to generate playbook YAML: {e}"
            logger.error(error_msg)
            return error_msg

