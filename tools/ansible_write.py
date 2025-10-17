from typing import Any
from ansible.parsing.dataloader import DataLoader
from ansible.errors import AnsibleError
from langchain_core.tools import BaseTool
from langchain_community.tools.file_management.write import WriteFileTool
from pydantic import BaseModel, Field


class AnsibleWriteInput(BaseModel):
    """Input schema for Ansible YAML write tool."""

    file_path: str = Field(description="The path to write the Ansible YAML file to")
    yaml_content: str = Field(
        description="The Ansible YAML content (with Jinja2 templates) to validate and write"
    )


class AnsibleWriteTool(BaseTool):
    """Tool to validate Ansible YAML content (with Jinja2 support) and write it to a file."""

    name: str = "ansible_write"
    description: str = (
        "Validates Ansible YAML content (including Jinja2 templates) and writes it to a file if valid. "
        "Use this for Ansible playbooks, tasks, handlers, and other Ansible YAML files that contain "
        "Jinja2 templating syntax like {{ variable }} or {% for %} loops. "
        "Returns success message if written, or an error message if validation fails."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleWriteInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._write_tool = WriteFileTool()
        self._loader = DataLoader()

    # pyrefly: ignore
    def _run(self, file_path: str, yaml_content: str) -> str:
        """Validate Ansible YAML content and write to file."""
        try:
            parsed_yaml = self._loader.load(data=yaml_content, json_only=False)

            # Allow empty/null for things like empty vars files with just comments
            # Check if content is truly empty (not just whitespace/comments)
            stripped_content = yaml_content.strip()
            if parsed_yaml is None and stripped_content:
                # If it starts with --- and only has comments, allow it
                lines_without_comments = [
                    line.strip()
                    for line in stripped_content.split("\n")
                    if line.strip()
                    and not line.strip().startswith("#")
                    and line.strip() != "---"
                ]
                if lines_without_comments:
                    return "Error: Empty or null YAML content, file not written"

            try:
                # Since YAML can be valid JSON, we need to check if the input is JSON and not allow it
                parsed_json = self._loader.load(data=yaml_content, json_only=True)
                if parsed_json is not None:
                    return "Error: JSON input is not allowed, file not written"
            except Exception:
                # expected to fail
                pass

            # Write original content to preserve Jinja2 templates and formatting
            self._write_tool.invoke({"file_path": file_path, "text": yaml_content})
            return f"Successfully wrote valid Ansible YAML to {file_path}"
        except AnsibleError as e:
            return f"Ansible YAML validation error: {str(e)}. File not written."
        except Exception as e:
            return f"Error writing Ansible YAML file: {str(e)}"
