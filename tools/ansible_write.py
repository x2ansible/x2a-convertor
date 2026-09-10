import yaml
from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader
from ansible.parsing.yaml.dumper import AnsibleDumper
from langchain_community.tools.file_management.write import WriteFileTool
from langchain_core.tools.base import ArgsSchema
from pydantic import BaseModel, Field

from tools.base_tool import X2ATool


class AnsibleWriteInput(BaseModel):
    """Input schema for Ansible YAML write tool."""

    file_path: str = Field(description="The path to write the Ansible YAML file to")
    yaml_content: str = Field(
        description="YAML-formatted string (NOT JSON). Example: '---\\n- name: Task\\n  ansible.builtin.apt:\\n    name: nginx'"
    )


class AnsibleWriteTool(X2ATool):
    """Validates Ansible YAML with AnsibleDumper and writes the original content to file."""

    name: str = "ansible_write"
    description: str = (
        "Validates Ansible YAML content (.yml, .yaml) and writes the original "
        "yaml_content verbatim to disk (comments preserved). "
        "yaml_content must be YAML, NOT JSON. "
        "If validation fails, fix the YAML issue and call ansible_write again."
    )

    args_schema: ArgsSchema | None = AnsibleWriteInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._write_tool = WriteFileTool()
        self._loader = DataLoader()

    # pyrefly: ignore
    def _run(self, file_path: str, yaml_content: str) -> str:
        """Validate Ansible YAML content and write the original content to file."""
        slog = self.log.bind(file_path=file_path)

        yaml_content = yaml_content.replace("\\n", "\n")

        try:
            parsed_yaml = self._loader.load(data=yaml_content, json_only=False)
            yaml.dump(parsed_yaml, Dumper=AnsibleDumper)
        except AnsibleError as e:
            slog.info(f"YAML validation failed for '{file_path}': {e!s}")
            return f"ERROR: YAML validation failed. The file was not written.\n{e!s}"
        except Exception as e:
            slog.info(f"YAML validation failed for '{file_path}': {e!s}")
            return f"ERROR: YAML validation failed. The file was not written.\n{e!s}"

        self._write_tool.invoke({"file_path": file_path, "text": yaml_content})
        slog.info("Successfully wrote valid Ansible YAML")
        return f"Successfully wrote valid Ansible YAML to {file_path}."
