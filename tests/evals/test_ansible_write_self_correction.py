"""Evaluation tests for ansible_write tool self-correction capabilities.

These tests verify that an LLM agent can:
1. Call ansible_write with invalid YAML
2. Receive structured error messages
3. Understand the error and fix the YAML
4. Retry ansible_write successfully

Each test measures the number of tool calls needed for self-correction.
"""

import os
from pathlib import Path

import pytest
import yaml
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from src.model import get_model
from tools.ansible_write import AnsibleWriteTool


def _has_valid_api_config() -> bool:
    """Check if API credentials are configured for testing."""
    # Check if we have proper API configuration
    return bool(os.getenv("OPENAI_API_BASE") and os.getenv("OPENAI_API_KEY"))


# Mark all tests in this file as eval tests AND skip if no API config
pytestmark = [
    pytest.mark.eval,  # Mark as eval test (can be skipped in CI)
    pytest.mark.skipif(
        not _has_valid_api_config(),
        reason="No valid API credentials configured. Set ANTHROPIC_API_KEY or OPENAI_API_BASE + OPENAI_API_KEY",
    ),
]


class TestAnsibleWriteToolSelfCorrection:
    """Test LLM agent's ability to self-correct ansible_write errors.

    Each test follows this pattern:
    1. Given: Agent receives prompt to write INVALID Ansible YAML
    2. When: Agent invokes ansible_write tool
    3. Then: Agent reads error, fixes YAML, retries, and succeeds

    We measure success by:
    - Total number of ansible_write calls
    - Whether final call succeeds
    - Whether output file is correct
    """

    @pytest.fixture
    def agent(self):
        """Create LangGraph ReAct agent with ansible_write tool."""
        model = get_model()
        tools = [AnsibleWriteTool()]

        # System prompt to enforce retry behavior
        system_prompt = """You are an expert at writing Ansible YAML files using the ansible_write tool.

CRITICAL RULES:
1. When ansible_write returns an ERROR, you MUST fix the YAML and call ansible_write again
2. Read error messages carefully - they contain line numbers and fix instructions
3. Keep retrying until you get "Successfully wrote" message
4. DO NOT give up after one error - errors are expected and fixable
5. Common fixes:
   - Unquoted Jinja2 variables → Add quotes: msg: "{{ item }}"
   - Colons in strings → Quote the whole value
   - Playbook wrappers in task files → Remove hosts/tasks keys

Your job is not done until the file is successfully written."""

        return create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )

    @pytest.fixture
    def temp_output_dir(self, tmp_path):
        """Create temporary directory for test outputs."""
        output_dir = tmp_path / "ansible_output"
        output_dir.mkdir()
        return output_dir

    def _create_taskfile_path(self, temp_output_dir: Path, filename: str) -> Path:
        """Create path for a taskfile and ensure parent directory exists.

        Args:
            temp_output_dir: Base temporary directory
            filename: Name of the taskfile (e.g., "debug.yml")

        Returns:
            Path object for the taskfile with parent directory created
        """
        file_path = temp_output_dir / "tasks" / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        return file_path

    def _create_write_prompt(self, file_path: Path, yaml_content: str) -> str:
        """Create standard prompt for writing Ansible YAML.

        Args:
            file_path: Path where YAML should be written
            yaml_content: YAML content to write

        Returns:
            Formatted prompt string
        """
        return f"""Your task: Write this Ansible YAML to {file_path}

```yaml
{yaml_content}
```

INSTRUCTIONS:
1. Call ansible_write with the YAML above
2. If you get an ERROR or WARNING, read it carefully, fix the YAML, and call ansible_write again
3. Keep fixing and retrying until you get "Successfully wrote" response

Start now - call ansible_write with the YAML."""

    # ========== JINJA2 QUOTING ERRORS ==========

    def test_unquoted_jinja2_variable_self_corrects(self, agent, temp_output_dir):
        """Test: Agent fixes unquoted Jinja2 variable (unhashable key error).

        Error type: YAML parser error "found unhashable key"
        Expected behavior: 2 tool calls (1 failure + 1 success)
        """
        # Given: Invalid YAML with unquoted Jinja2
        invalid_yaml = """---
- name: Print item
  ansible.builtin.debug:
    msg: {{ item }}
  loop:
    - one
    - two"""

        file_path = self._create_taskfile_path(temp_output_dir, "debug.yml")
        prompt = self._create_write_prompt(file_path, invalid_yaml)

        # When: Agent attempts to write
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})
        # Then: Verify self-correction
        ansible_write_calls = self._extract_tool_calls(result, "ansible_write")
        tool_responses = self._get_tool_responses(result, "ansible_write")

        # Should have at least 1 call (LLM might fix proactively or need retries)
        assert len(ansible_write_calls) <= 2, (
            f"Expected 2 ansible_write call, got {len(ansible_write_calls)}"
        )

        # Last call should succeed
        assert "Successfully wrote" in tool_responses[-1], (
            f"Final call should succeed, but got: {tool_responses[-1][:200]}"
        )

        # Verify file was created correctly
        assert file_path.exists(), "File should be created"
        content = file_path.read_text()
        assert '"{{ item }}"' in content or "'{{ item }}'" in content, (
            f"Jinja2 variable should be quoted in final output. Got: {content}"
        )

    def test_when_clause_with_colon_self_corrects(self, agent, temp_output_dir):
        """Test: Agent fixes when clause with unquoted colon.

        Error type: YAML parser error "mapping values are not allowed here"
        Expected behavior: 2 tool calls
        """
        # Given: when clause with colon causing "mapping values not allowed"
        invalid_yaml = """---
- name: Check firewall status
  ansible.builtin.command: ufw status
  register: fw_status
  changed_when: false

- name: Set default deny
  ansible.builtin.command: ufw default deny
  when: fw_status.stdout is not search('Default: deny')"""

        file_path = self._create_taskfile_path(temp_output_dir, "firewall.yml")
        prompt = self._create_write_prompt(file_path, invalid_yaml)

        # When
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})

        # Then
        ansible_write_calls = self._extract_tool_calls(result, "ansible_write")
        tool_responses = self._get_tool_responses(result, "ansible_write")

        assert len(ansible_write_calls) == 2, (
            f"Expected 2 tools call, got {len(ansible_write_calls)}"
        )

        # Last should succeed
        assert "Successfully wrote" in tool_responses[-1], (
            f"Final call should succeed, got: {tool_responses[-1][:200]}"
        )

        # Verify file exists and when clause is handled
        assert file_path.exists()
        content = file_path.read_text()
        assert "when:" in content

    # ========== ANSIBLE STRUCTURE ERRORS ==========

    def test_playbook_wrapper_in_taskfile_self_corrects(self, agent, temp_output_dir):
        """Test: Agent removes playbook wrapper from task file.

        Error type: Custom validation error for playbook wrapper in tasks/
        Expected behavior: 2 tool calls
        """
        # Given: Task file with playbook wrapper (hosts, tasks keys)
        invalid_yaml = """---
- hosts: all
  become: true
  tasks:
    - name: Install nginx
      ansible.builtin.apt:
        name: nginx
        state: present"""

        file_path = self._create_taskfile_path(temp_output_dir, "main.yml")
        prompt = self._create_write_prompt(file_path, invalid_yaml)

        # When
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})

        # Then
        ansible_write_calls = self._extract_tool_calls(result, "ansible_write")
        tool_responses = self._get_tool_responses(result, "ansible_write")

        assert len(ansible_write_calls) == 2, (
            f"Expected 2 tools call, got {len(ansible_write_calls)}"
        )

        # Last should succeed
        assert "Successfully wrote" in tool_responses[-1], (
            f"Final call should succeed, got: {tool_responses[-1][:200]}"
        )

        # Verify output is flat task list (no hosts/tasks wrapper)
        content = file_path.read_text()
        assert "hosts:" not in content, "Should remove hosts wrapper"
        assert "Install nginx" in content
        assert "ansible.builtin.apt:" in content

    def test_missing_fqcn_self_corrects(self, agent, temp_output_dir):
        """Test: Agent adds FQCN to modules after ARI validation warning.

        Error type: ARI validation warning (R301)
        Expected behavior: 2 tool calls (write with short name + rewrite with FQCN)
        """
        # Given: Task with non-FQCN module name
        invalid_yaml = """---
- name: Install nginx
  apt:
    name: nginx
    state: present"""

        file_path = self._create_taskfile_path(temp_output_dir, "install.yml")
        prompt = self._create_write_prompt(file_path, invalid_yaml)

        # When
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})

        # Then
        ansible_write_calls = self._extract_tool_calls(result, "ansible_write")
        tool_responses = self._get_tool_responses(result, "ansible_write")

        # Should have at least 1 call
        assert len(ansible_write_calls) == 2, (
            f"Expected 2 ansible_write call, got {len(ansible_write_calls)}"
        )

        # Last call should succeed
        assert "Successfully wrote" in tool_responses[-1], (
            f"Final call should succeed, got: {tool_responses[-1][:200]}"
        )

        # Final output should have FQCN
        assert file_path.exists(), "File should exist"
        content = file_path.read_text()
        assert "ansible.builtin.apt:" in content, (
            f"Should use FQCN in final output. Got: {content}"
        )

    # ========== COMPLEX MULTI-ERROR CASES ==========

    def test_multiple_errors_self_corrects(self, agent, temp_output_dir):
        """Test: Agent fixes multiple errors in sequence.

        Errors:
        - Missing task name
        - Unquoted Jinja2
        - Unquoted when with colon
        - Missing FQCN

        Expected behavior: 2-4 tool calls (multiple iterations)
        """
        # Given: YAML with multiple issues
        invalid_yaml = """---
- ansible.builtin.debug:
    msg: {{ message }}
  when: status is search('error: found')

- name: Install package
  package:
    name: nginx"""

        file_path = self._create_taskfile_path(temp_output_dir, "complex.yml")
        prompt = self._create_write_prompt(file_path, invalid_yaml)

        # When
        result = agent.invoke({"messages": [HumanMessage(content=prompt)]})

        # Then
        ansible_write_calls = self._extract_tool_calls(result, "ansible_write")
        tool_responses = self._get_tool_responses(result, "ansible_write")
        # Should need at least 1 attempt (multi-error might succeed quickly with improved messages)
        assert 2 <= len(ansible_write_calls) <= 3, (
            f"should get two or three tools calls, got {len(ansible_write_calls)}"
        )

        # Final call should succeed
        assert "Successfully wrote" in tool_responses[-1], (
            f"Final call should succeed with 'Successfully wrote', got: {tool_responses[-1][:200]}"
        )

        # Verify file exists and has basic fixes
        assert file_path.exists(), "File should exist"
        content = file_path.read_text()
        # At minimum, file should be valid YAML and exist
        assert len(content) > 0, "File should not be empty"

        # Parse and validate YAML structure instead of string comparison
        tasks = yaml.safe_load(content)
        assert isinstance(tasks, list), "YAML should be a list of tasks"
        assert len(tasks) == 2, f"Expected 2 tasks, got {len(tasks)}"

        # Validate debug task
        debug_task = tasks[0]
        assert "ansible.builtin.debug" in debug_task, (
            "First task should use ansible.builtin.debug"
        )
        assert "msg" in debug_task["ansible.builtin.debug"], (
            "Debug task should have msg parameter"
        )
        assert "when" in debug_task, "Debug task should have when condition"

        # Validate package install task
        package_task = tasks[1]
        assert "name" in package_task, "Second task should have a name"
        assert "Install package" in package_task["name"], (
            "Second task should be named 'Install package'"
        )
        assert "ansible.builtin.package" in package_task, (
            "Second task should use ansible.builtin.package (FQCN)"
        )
        assert package_task["ansible.builtin.package"]["name"] == "nginx", (
            "Package task should install nginx"
        )

    # ========== HELPER METHODS ==========

    def _extract_tool_calls(self, result: dict, tool_name: str) -> list:
        """Extract all calls to a specific tool from agent result.

        Args:
            result: Agent invocation result with messages
            tool_name: Name of tool to filter for

        Returns:
            List of tool call dictionaries for specified tool
        """
        messages = result["messages"]

        tool_calls = []
        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for call in msg.tool_calls:
                    if call["name"] == tool_name:
                        tool_calls.append(call)

        return tool_calls

    def _get_tool_responses(self, result: dict, tool_name: str) -> list[str]:
        """Extract all responses from a specific tool.

        Args:
            result: Agent invocation result with messages
            tool_name: Name of tool to filter for

        Returns:
            List of tool response content strings
        """
        messages = result["messages"]

        responses = []
        for msg in messages:
            if hasattr(msg, "name") and msg.name == tool_name:
                responses.append(msg.content)

        return responses
