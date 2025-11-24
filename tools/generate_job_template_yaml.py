"""Tool for generating AAP job template YAML files."""

from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)


class GenerateJobTemplateYAMLInput(BaseModel):
    """Input schema for generating job template YAML."""

    file_path: str = Field(description="Output file path")
    name: str = Field(description="Job template name")
    playbook_path: str = Field(description="Path to playbook file")
    inventory: str = Field(description="Inventory name or path")
    role_name: str = Field(default="", description="Role name (optional)")
    description: str = Field(default="", description="Description (optional)")
    extra_vars: str = Field(default="", description="Extra vars YAML (optional)")


class GenerateJobTemplateYAMLTool(BaseTool):
    """Generate AAP job template YAML configuration."""

    name: str = "generate_job_template_yaml"
    description: str = (
        "Generate AAP job template YAML configuration. "
        "Creates a job template that references a playbook."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = GenerateJobTemplateYAMLInput

    def _run(self, *args: Any, **kwargs: Any) -> str:
        """Generate job template YAML file."""
        file_path = kwargs.get("file_path", "")
        name = kwargs.get("name", "")
        playbook_path = kwargs.get("playbook_path", "")
        inventory = kwargs.get("inventory", "")
        role_name = kwargs.get("role_name", "")
        description = kwargs.get("description", "")
        extra_vars = kwargs.get("extra_vars", "")

        logger.info(f"Generating job template YAML: {name}")

        if not playbook_path:
            return "ERROR: playbook_path is required for job_template generation"
        if not inventory:
            return "ERROR: inventory is required for job_template generation"

        try:
            job_template: dict[str, Any] = {
                "apiVersion": "tower.ansible.com/v1beta1",
                "kind": "JobTemplate",
                "metadata": {"name": name},
                "spec": {
                    "name": name,
                    "job_type": "run",
                    "playbook": playbook_path,
                    "inventory": inventory,
                },
            }

            if description:
                job_template["spec"]["description"] = description

            if role_name:
                job_template["spec"]["role_name"] = role_name

            if extra_vars:
                try:
                    parsed_vars = yaml.safe_load(extra_vars)
                    job_template["spec"]["extra_vars"] = parsed_vars
                except yaml.YAMLError:
                    job_template["spec"]["extra_vars"] = extra_vars

            file_path_obj = Path(file_path)
            file_path_obj.parent.mkdir(parents=True, exist_ok=True)

            with file_path_obj.open("w") as f:
                yaml.dump(
                    job_template,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )

            logger.info(f"Successfully generated job template YAML: {file_path}")
            return (
                f"Successfully generated job template YAML at {file_path}\n"
                f"Job template: {name}\n"
                f"Playbook: {playbook_path}\n"
                f"Inventory: {inventory}"
            )

        except Exception as e:
            error_msg = f"ERROR: Failed to generate job template YAML: {e}"
            logger.error(error_msg)
            return error_msg
