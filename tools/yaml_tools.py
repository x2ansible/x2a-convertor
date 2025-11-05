from typing import Any

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class YamlValidateInput(BaseModel):
    """Input schema for YAML validation tool."""

    yaml_content: str = Field(description="The YAML content to validate and lint")


class YamlLintInput(BaseModel):
    """Input schema for YAML linting tool."""

    yaml_content: str = Field(description="The YAML content to lint")


class YamlValidateTool(BaseTool):
    """Tool to validate YAML content and return linted version."""

    name: str = "yaml_validate"
    description: str = (
        "Validates YAML content and returns a linted, properly formatted version. "
        "Use this when you need to ensure YAML is valid and get a clean version back. "
        "Returns the linted YAML if valid, or an error message if invalid."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = YamlValidateInput

    # pyrefly: ignore
    def _run(self, yaml_content: str) -> str:
        """Validate and lint YAML content."""
        try:
            parsed = yaml.safe_load(yaml_content)
            if parsed is None:
                return "Error: Empty or null YAML content"

            linted = yaml.dump(
                parsed,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
            # pyrefly: ignore
            return linted
        except yaml.YAMLError as e:
            return f"YAML validation error: {e!s}"
        except Exception as e:
            return f"Error validating YAML: {e!s}"


class YamlLintTool(BaseTool):
    """Tool to lint YAML content and check for issues."""

    name: str = "yaml_lint"
    description: str = (
        "Lints YAML content and reports any syntax or formatting issues. "
        "Use this to check if YAML is valid without getting the reformatted content. "
        "Returns either 'Success, the provided yaml content is valid.' if no issues found, or specific error messages if problems detected."
    )
    args_schema: dict[str, Any] | type[BaseModel] | None = YamlLintInput

    # pyrefly: ignore
    def _run(self, yaml_content: str) -> str:
        """Lint YAML content and report issues."""
        try:
            parsed = yaml.safe_load(yaml_content)
            if parsed is None:
                return "Warning: Empty or null YAML content"
            return "Success, the provided yaml content is valid."
        except yaml.YAMLError as e:
            error_msg = str(e)
            if hasattr(e, "problem_mark") and hasattr(e, "problem"):
                mark = e.problem_mark
                return (
                    f"ERROR: YAML syntax error at line {mark.line + 1}, "
                    f"column {mark.column + 1}: {e.problem}"
                )
            return (
                f"ERROR: YAML parsing failed with following error:\n```{error_msg}```"
            )
        except Exception as e:
            return f"ERROR: linting failed on provided YAML content with following error:\n```{e!s}```."
