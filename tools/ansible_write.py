import structlog
from typing import Any
from ansible.parsing.dataloader import DataLoader
from ansible.errors import AnsibleError
from langchain_core.tools import BaseTool
from langchain_community.tools.file_management.write import WriteFileTool
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)


class AnsibleWriteInput(BaseModel):
    """Input schema for Ansible YAML write tool."""

    file_path: str = Field(description="The path to write the Ansible YAML file to")
    yaml_content: str = Field(
        description="The Ansible YAML content to validate and write"
    )


class AnsibleWriteTool(BaseTool):
    """Tool to validate Ansible YAML content (with Jinja2 support) and write it to a file."""

    name: str = "ansible_write"
    description: str = (
        "Validates and writes Ansible YAML files (tasks, handlers, vars, defaults, meta/main.yml). "
        "Performs YAML validation before writing the file. "
        "DO NOT use for template files (.j2). "
        "Returns success message if written, or validation error if invalid."
    )

    args_schema: dict[str, Any] | type[BaseModel] | None = AnsibleWriteInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._write_tool = WriteFileTool()
        self._loader = DataLoader()

    # pyrefly: ignore
    def _run(self, file_path: str, yaml_content: str) -> str:
        """Validate Ansible YAML content and write to file."""

        slog = logger.bind(phase="AnsibleWriteTool", file_path=file_path)
        slog.debug(f"AnsibleWriteTool called on {file_path}")

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
                    slog.debug("Failed on empty content")
                    return "ERROR: The provided yaml content is either null or empty. The file was not written."

            try:
                # Since YAML can be valid JSON, we need to check if the input is JSON and not allow it
                parsed_json = self._loader.load(data=yaml_content, json_only=True)
                if parsed_json is not None:
                    slog.debug("Failed on JSON instead of YAML")
                    return "ERROR: JSON input is not allowed, expecting yaml content instead. The file was not written."
            except Exception:
                # expected to fail
                pass

            # Write original content to preserve Jinja2 templates and formatting
            self._write_tool.invoke({"file_path": file_path, "text": yaml_content})
            return f"Successfully wrote valid Ansible YAML to {file_path}."
        except AnsibleError as e:
            slog.debug(f"Failed on YAML validation: {str(e)}\nContent: {yaml_content}")
            # TODO: The LLM gets sometimes in an infinite loop as it can not fix (understand) the validation issue and keeps writing the same incorrect file.
            # TODO: Example of a hard-to-understand issue: YAML parsing failed: Mapping values are not allowed in this context.
            # If only we can provide additional data, like the failing line number
            return f"ERROR: the provided YAML is not valid, the file was not written. Fix following error and try again:\n```{str(e)}```."
        except Exception as e:
            slog.debug(f"Failed on generic error: {str(e)}\nContent: {yaml_content}")
            return f"ERROR: when writing Ansible YAML file, the file was not written. Fix following error and try again:\n```{str(e)}```."
