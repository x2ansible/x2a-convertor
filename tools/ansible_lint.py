from pathlib import Path

from ansiblelint.runner import Runner
from ansiblelint.rules import RulesCollection
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class AnsibleLintInput(BaseModel):
    """Input schema for Ansible linting tool."""

    ansible_path: str = Field(
        description="Path to Ansible file or directory to lint (e.g., '../chef-example/ansible/')"
    )


class AnsibleLintTool(BaseTool):
    """Tool to lint Ansible files using ansible-lint."""

    name: str = "ansible_lint"
    description: str = (
        "Lints Ansible playbooks, roles, and task files using ansible-lint. "
        "Checks for best practices, syntax issues, and potential problems. "
        "Returns a list of issues found or confirmation that no issues were detected."
    )
    args_schema = AnsibleLintInput

    # pyrefly: ignore
    def _run(self, ansible_path: str) -> str:
        """Lint Ansible files and report issues."""
        try:
            path = Path(ansible_path)
            if not path.exists():
                return f"Error: Path '{ansible_path}' does not exist"

            # Collect all YAML files
            if path.is_file():
                files = [str(path)]
            else:
                files = [str(f) for f in path.rglob("*.yml")] + [
                    str(f) for f in path.rglob("*.yaml")
                ]

            if not files:
                return f"No Ansible files found in '{ansible_path}'"

            # Create rules and run linter
            rules = RulesCollection()
            runner = Runner(*files, rules=rules)
            matches = runner.run()

            if not matches:
                return "No ansible-lint issues found. All files pass linting checks."

            issues: list[str] = []
            for match in matches:
                issue = (
                    f"{match.filename}:{match.lineno or 0} "
                    f"[{match.rule.id}] {match.message}"
                )
                issues.append(issue)

            result = f"Found {len(matches)} ansible-lint issue(s):\n\n"
            result += "\n".join(issues)
            return result

        except ImportError:
            return (
                "Error: ansible-lint is not installed. "
                "Install it with: uv add ansible-lint"
            )
        except Exception as e:
            return f"Error running ansible-lint: {str(e)}"
