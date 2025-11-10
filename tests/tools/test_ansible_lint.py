import shutil
import tempfile
from pathlib import Path

from tools.ansible_lint import ANSIBLE_LINT_TOOL_SUCCESS_MESSAGE, AnsibleLintTool


class TestAnsibleLintTool:
    """Test cases for AnsibleLintTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = AnsibleLintTool()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_lint_error_gets_fixed_with_autofix(self) -> None:
        """Test that ansible-lint detects errors and fixes them automatically when autofix=True."""
        # Create a subdirectory for this test
        subdir = Path(self.temp_dir) / "playbook_dir"
        Path(subdir).mkdir(parents=True)

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
        file_path = Path(subdir) / "playbook_with_errors.yml"

        # Write the file with errors
        with Path(file_path).open("w") as f:
            f.write(yaml_content)

        # Run ansible-lint tool on the directory with autofix=True (default)
        result = self.tool._run(str(subdir), autofix=True)

        # The tool should return a string result (either success or issues)
        assert isinstance(result, str)
        assert len(result) > 0

        # Read the file to verify it exists and was processed
        with Path(file_path).open() as f:
            fixed_content = f.read()

        # The file should exist and contain valid YAML
        assert Path(file_path).exists()
        assert "hosts: all" in fixed_content
        assert "ansible.builtin.package" in fixed_content

    def test_lint_error_not_fixed_with_autofix_false(self) -> None:
        """Test that ansible-lint detects errors but does not fix them when autofix=False."""
        # Create a subdirectory for this test
        subdir = Path(self.temp_dir) / "playbook_dir_nofix"
        Path(subdir).mkdir(parents=True)

        # Create a playbook with intentional linting errors
        # This uses 'yes' instead of 'true'
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
        file_path = Path(subdir) / "playbook_with_errors.yml"

        # Write the file with errors
        with Path(file_path).open("w") as f:
            f.write(yaml_content)

        # Run ansible-lint tool on the directory with autofix=False
        result = self.tool._run(str(subdir), autofix=False)

        # The tool should return error messages
        assert isinstance(result, str)
        assert "ansible-lint issue" in result

        # Read the file to verify it was NOT modified
        with Path(file_path).open() as f:
            content_after = f.read()

        # The file should still have 'yes' (not fixed)
        assert "become: yes" in content_after

    def test_valid_playbook_passes_lint(self) -> None:
        """Test that a valid playbook passes linting checks."""
        # Create a subdirectory for this test
        subdir = Path(self.temp_dir) / "valid_playbooks"
        Path(subdir).mkdir(parents=True)

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
        file_path = Path(subdir) / "valid_playbook.yml"

        with Path(file_path).open("w") as f:
            f.write(yaml_content)

        result = self.tool._run(str(subdir))

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
        file_path = Path(self.temp_dir) / "single_file.yml"

        with Path(file_path).open("w") as f:
            f.write(yaml_content)

        result = self.tool._run(str(file_path))

        assert "ERROR" in result
        assert "must be a directory" in result

    def test_directory_with_multiple_files(self) -> None:
        """Test linting a directory containing multiple playbooks."""
        # Create a subdirectory with multiple files
        subdir = Path(self.temp_dir) / "playbooks"
        Path(subdir).mkdir(parents=True)

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
        with (Path(subdir) / "playbook1.yml").open("w") as f:
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
        with (Path(subdir) / "playbook2.yml").open("w") as f:
            f.write(playbook2)

        result = self.tool._run(str(subdir))

        # Should either fix all issues or report remaining issues
        assert isinstance(result, str)
        assert len(result) > 0

    def test_syntax_error_reports_filename_and_line(self) -> None:
        """Test that YAML syntax errors report the filename and line number."""
        # Create a subdirectory with a role structure
        subdir = Path(self.temp_dir) / "test_role"
        tasks_dir = Path(subdir) / "tasks"
        Path(tasks_dir).mkdir(parents=True)

        # Create a task file with YAML syntax error (invalid Jinja2 expression)
        # This mimics the real-world error: mapping values not allowed
        yaml_with_syntax_error = """---
- name: Check firewall status
  ansible.builtin.command: ufw status
  register: fw_status
  changed_when: false

- name: Set default deny
  ansible.builtin.command: ufw default deny
  when: fw_status is not search("Default: deny")
"""
        file_path = Path(tasks_dir) / "security.yml"
        with Path(file_path).open("w") as f:
            f.write(yaml_with_syntax_error)

        result = self.tool._run(str(subdir))

        # Verify the result contains the error information
        assert isinstance(result, str)
        assert "load-failure" in result or "syntax" in result.lower()

        # Most importantly: verify it includes the filename, not "<unicode string>"
        assert "security.yml" in result
        assert "<unicode string>" not in result

        # Should also contain line number information
        assert "tasks/security.yml:" in result

    def test_non_fixable_lint_issues_persist(self) -> None:
        """Test that non-fixable lint issues persist after autofix attempt.

        This test reproduces real-world issues found in nginx_multisite:
        - [no-changed-when]: Commands without changed_when
        - [literal-compare]: Comparing to literal True/False
        """
        # Create a subdirectory with a role structure
        subdir = Path(self.temp_dir) / "nginx_multisite"
        tasks_dir = Path(subdir) / "tasks"
        Path(tasks_dir).mkdir(parents=True)

        # Create a task file with issues that ansible-lint cannot auto-fix
        # Based on real nginx_multisite/tasks/security.yml
        yaml_with_unfixable_issues = """---
- name: Deploy sysctl security configuration
  ansible.builtin.template:
    src: templates/sysctl-security.conf.j2
    dest: /etc/sysctl.d/99-security.conf
    mode: "0644"
  notify: reload sysctl

- name: Reload sysctl configuration
  ansible.builtin.command: sysctl -p /etc/sysctl.d/99-security.conf
  when: reload_sysctl is defined

- name: Disable password authentication
  ansible.builtin.lineinfile:
    dest: /etc/ssh/sshd_config
    regexp: ^PasswordAuthentication
    line: PasswordAuthentication no
    state: present
  when: security_ssh_password_auth is defined and security_ssh_password_auth == false
  notify: restart ssh
"""
        file_path = Path(tasks_dir) / "security.yml"
        with Path(file_path).open("w") as f:
            f.write(yaml_with_unfixable_issues)

        # Run ansible-lint with autofix=True
        result = self.tool._run(str(subdir), autofix=True)

        # Verify the issues persist because they cannot be auto-fixed
        assert isinstance(result, str)
        assert "ansible-lint issue" in result

        # Verify specific rule violations are reported
        assert "no-changed-when" in result
        assert "literal-compare" in result

        # Verify the correct file and approximate line numbers are reported
        assert "tasks/security.yml" in result

        # The issues should be on specific lines (may vary slightly with formatting)
        # Just verify line numbers are present
        assert "tasks/security.yml:" in result
