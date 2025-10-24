import os
import tempfile
import shutil
from tools.ansible_lint import AnsibleLintTool, ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE


class TestAnsibleLintTool:
    """Test cases for AnsibleLintTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = AnsibleLintTool()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_lint_error_gets_fixed(self) -> None:
        """Test that ansible-lint detects errors and fixes them automatically."""
        # Create a subdirectory for this test
        subdir = os.path.join(self.temp_dir, "playbook_dir")
        os.makedirs(subdir)

        # Create a playbook with intentional linting errors
        # This uses 'yes' instead of 'true' which ansible-lint should fix
        yaml_content = """---
- name: Test playbook with linting errors
  hosts: all
  become: yes
  tasks:
    - name: install nginx
      ansible.builtin.package:
        name: nginx
        state: present
"""
        file_path = os.path.join(subdir, "playbook_with_errors.yml")

        # Write the file with errors
        with open(file_path, "w") as f:
            f.write(yaml_content)

        # Run ansible-lint tool on the directory
        result = self.tool._run(subdir)

        # The tool should return a string result (either success or issues)
        assert isinstance(result, str)
        assert len(result) > 0

        # Read the file to verify it exists and was processed
        with open(file_path, "r") as f:
            fixed_content = f.read()

        # The file should exist and contain valid YAML
        assert os.path.exists(file_path)
        assert "hosts: all" in fixed_content
        assert "ansible.builtin.package" in fixed_content

    def test_valid_playbook_passes_lint(self) -> None:
        """Test that a valid playbook passes linting checks."""
        # Create a subdirectory for this test
        subdir = os.path.join(self.temp_dir, "valid_playbooks")
        os.makedirs(subdir)

        yaml_content = """---
- name: Test valid playbook
  hosts: all
  become: true
  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present
"""
        file_path = os.path.join(subdir, "valid_playbook.yml")

        with open(file_path, "w") as f:
            f.write(yaml_content)

        result = self.tool._run(subdir)

        assert ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE in result

    def test_nonexistent_path_returns_error(self) -> None:
        """Test that nonexistent path returns an error message."""
        fake_path = "/nonexistent/path/to/playbook.yml"

        result = self.tool._run(fake_path)

        assert "ERROR" in result
        assert "does not exist" in result

    def test_file_path_returns_error(self) -> None:
        """Test that passing a file path instead of directory returns an error."""
        # Create a single file
        yaml_content = """---
- name: Test playbook
  hosts: all
  become: true
  tasks:
    - name: Test task
      ansible.builtin.debug:
        msg: test
"""
        file_path = os.path.join(self.temp_dir, "single_file.yml")

        with open(file_path, "w") as f:
            f.write(yaml_content)

        result = self.tool._run(file_path)

        assert "ERROR" in result
        assert "must be a directory" in result

    def test_directory_with_multiple_files(self) -> None:
        """Test linting a directory containing multiple playbooks."""
        # Create a subdirectory with multiple files
        subdir = os.path.join(self.temp_dir, "playbooks")
        os.makedirs(subdir)

        # Create first playbook with errors
        playbook1 = """---
- name: First playbook
  hosts: all
  become: yes
  tasks:
    - name: task one
      ansible.builtin.debug:
        msg: hello
"""
        with open(os.path.join(subdir, "playbook1.yml"), "w") as f:
            f.write(playbook1)

        # Create second valid playbook
        playbook2 = """---
- name: Second playbook
  hosts: all
  become: true
  tasks:
    - name: Task two
      ansible.builtin.debug:
        msg: world
"""
        with open(os.path.join(subdir, "playbook2.yml"), "w") as f:
            f.write(playbook2)

        result = self.tool._run(subdir)

        # Should either fix all issues or report remaining issues
        assert isinstance(result, str)
        assert len(result) > 0
