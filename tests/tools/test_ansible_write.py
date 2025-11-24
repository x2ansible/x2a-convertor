import shutil
import tempfile
from pathlib import Path

from tools.ansible_write import AnsibleWriteTool


class TestAnsibleWriteTool:
    """Test cases for AnsibleWriteTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = AnsibleWriteTool()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_write_yaml_with_jinja2_templates(self) -> None:
        """Test writing YAML with Jinja2 templates (loop variables)."""
        yaml_content = """---
- name: Add several users
  ansible.builtin.user:
    name: "{{ item }}"
    state: present
    groups: "wheel"
  loop:
    - testuser1
    - testuser2
"""
        file_path = Path(self.temp_dir) / "users.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        # Should succeed
        assert "Successfully wrote" in result
        assert str(file_path) in result
        assert Path(file_path).exists()

        # Verify the file content preserves Jinja2 templates
        with Path(file_path).open() as f:
            content = f.read()

        # Check that Jinja2 template is preserved
        assert "{{ item }}" in content
        # Check that structure is maintained
        assert "ansible.builtin.user" in content
        assert "testuser1" in content
        assert "testuser2" in content
        assert "loop:" in content

    def test_write_yaml_with_multiple_jinja2_variables(self) -> None:
        """Test writing YAML with multiple Jinja2 variables."""
        yaml_content = """---
- name: Configure application
  ansible.builtin.template:
    src: "{{ template_src }}"
    dest: "{{ app_config_path }}/{{ config_file }}"
    owner: "{{ app_user }}"
    group: "{{ app_group }}"
    mode: "0644"
"""
        file_path = Path(self.temp_dir) / "configure.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()

        # All Jinja2 variables should be preserved
        assert "{{ template_src }}" in content
        assert "{{ app_config_path }}" in content
        assert "{{ config_file }}" in content
        assert "{{ app_user }}" in content
        assert "{{ app_group }}" in content

    def test_reject_json_input(self) -> None:
        """Test that JSON input is rejected."""
        json_content = """{"tasks": [{"name": "test", "debug": {"msg": "hello"}}]}"""
        file_path = Path(self.temp_dir) / "test.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=json_content)

        # Should fail with JSON error
        assert "ERROR" in result
        assert "JSON input is not allowed" in result
        # File should not be created
        assert not Path(file_path).exists()

    def test_write_valid_ansible_tasks(self) -> None:
        """Test writing a valid Ansible tasks file."""
        yaml_content = """---
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present

- name: Start nginx service
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true
"""
        file_path = Path(self.temp_dir) / "tasks.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()

        assert "ansible.builtin.package" in content
        assert "ansible.builtin.service" in content

    def test_reject_invalid_yaml(self) -> None:
        """Test that invalid YAML is rejected."""
        # This YAML has a mapping value in wrong context
        invalid_yaml = """---
- name: Test
  tasks:
    key: value: another_value
"""
        file_path = Path(self.temp_dir) / "invalid.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_yaml)

        # Should fail with YAML validation error
        assert "ERROR" in result
        assert "YAML parsing failed" in result
        # Should now have XML format
        assert "<ansible_yaml_error>" in result
        # File should not be created
        assert not Path(file_path).exists()

    def test_write_empty_vars_file_with_comments(self) -> None:
        """Test writing an empty vars file with only comments."""
        yaml_content = """---
# Variables for the application
# Currently no variables defined
"""
        file_path = Path(self.temp_dir) / "vars.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        # Should succeed
        assert "Successfully wrote" in result
        assert Path(file_path).exists()

    def test_write_handlers_file(self) -> None:
        """Test writing an Ansible handlers file."""
        yaml_content = """---
- name: Restart nginx
  ansible.builtin.service:
    name: nginx
    state: restarted

- name: Reload systemd
  ansible.builtin.systemd:
    daemon_reload: true
"""
        file_path = Path(self.temp_dir) / "handlers.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

    def test_write_defaults_with_jinja2_filters(self) -> None:
        """Test writing defaults file with Jinja2 filters."""
        yaml_content = """---
app_version: "1.0.0"
app_port: 8080
app_config_path: "/etc/{{ app_name | default('myapp') }}"
app_log_level: "{{ log_level | default('INFO') | upper }}"
"""
        file_path = Path(self.temp_dir) / "defaults.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()

        # Jinja2 filters should be preserved (quotes might be normalized)
        assert "{{ app_name | default('myapp') }}" in content
        # Check that the Jinja2 expression is there (quotes may vary)
        assert "{{ log_level | default(" in content
        assert "| upper }}" in content
        assert "INFO" in content

    def test_yaml_formatting_applied(self) -> None:
        """Test that YAML formatting is applied to normalize output."""
        # Input with inconsistent formatting
        yaml_content = """---
- name: test task
  ansible.builtin.debug:
    msg:   'hello'
  vars:   {foo:  bar,  baz:  qux}
"""
        file_path = Path(self.temp_dir) / "formatted.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()

        # Output should be properly formatted (not JSON-like)
        # AnsibleDumper should expand the inline dict to proper YAML
        assert "foo:" in content or "vars:" in content
        # Should not have compressed JSON-like formatting
        assert content.count("{") == 0  # No inline dicts in output

    def test_valid_ansible_yaml_normalized(self) -> None:
        """Test writing valid Ansible YAML content with AnsibleDumper normalization."""
        yaml_content = """---
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present
"""
        file_path = Path(self.temp_dir) / "test.yml"
        result = self.tool._run(str(file_path), yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()
            # AnsibleDumper strips the --- separator
            assert not content.startswith("---")
            # But the content structure should be preserved
            assert "name: Install nginx" in content
            assert "ansible.builtin.package:" in content
            assert "name: nginx" in content
            assert "state: present" in content

    def test_comments_removed_by_dumper(self) -> None:
        """Test that AnsibleDumper removes comments during normalization."""
        yaml_content = """---
# This is a comment
- name: Install packages
  ansible.builtin.package:
    name:
      - nginx
      - git
      - curl
    state: present

# Another comment
- name: Start service
  ansible.builtin.service:
    name: nginx
    state: started
"""
        file_path = Path(self.temp_dir) / "formatted.yml"
        result = self.tool._run(str(file_path), yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result

        with Path(file_path).open() as f:
            content = f.read()
            # Comments are removed by AnsibleDumper
            assert "# This is a comment" not in content
            assert "# Another comment" not in content
            # But structure and content should be preserved
            assert "name: Install packages" in content
            assert "name: Start service" in content
            assert "nginx" in content
            assert "git" in content
            assert "curl" in content

    def test_write_truly_empty_yaml(self) -> None:
        """Test writing completely empty YAML (just ---)."""
        yaml_content = "---\n"
        file_path = Path(self.temp_dir) / "empty.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

    def test_write_yaml_without_jinja2_variables(self) -> None:
        """Test writing valid Ansible YAML without any Jinja2 variables."""
        yaml_content = """---
- name: Install packages
  ansible.builtin.package:
    name:
      - nginx
      - git
    state: present

- name: Create directory
  ansible.builtin.file:
    path: /opt/app
    state: directory
    mode: '0755'
"""
        file_path = Path(self.temp_dir) / "no_vars.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()

        # Should not have any Jinja2 templates
        assert "{{" not in content
        assert "}}" not in content
        # But should have the expected content
        assert "nginx" in content
        assert "/opt/app" in content

    def test_write_whitespace_only_yaml(self) -> None:
        """Test writing YAML with only whitespace (should succeed as empty)."""
        yaml_content = "   \n   \n  "
        file_path = Path(self.temp_dir) / "whitespace.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        # Should succeed - whitespace-only is treated as empty
        assert "Successfully wrote" in result
        assert Path(file_path).exists()

    def test_yaml_syntax_error_returns_xml_with_line_info(self) -> None:
        """Test that YAML syntax errors return XML-formatted error with line/column info."""
        # YAML with syntax error (colon in search() filter)
        invalid_yaml = """---
- name: Check firewall
  ansible.builtin.command: ufw status
  register: fw_status
  changed_when: false

- name: Set default deny
  ansible.builtin.command: ufw default deny
  when: fw_status is not search('Default: deny')
"""
        file_path = Path(self.temp_dir) / "syntax_error.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_yaml)

        # Should return an error
        assert "ERROR" in result
        assert "YAML parsing failed" in result

        # Should have XML structure
        assert "<ansible_yaml_error>" in result
        assert "</ansible_yaml_error>" in result
        assert "<file_path>" in result
        assert str(file_path) in result

        # Should have error details
        assert "<error_details>" in result
        assert "<message>" in result
        assert "<line_number>" in result
        assert "<column_number>" in result

        # Should have problematic location
        assert "<problematic_location>" in result
        assert "<line_content>" in result
        assert "<column_pointer>" in result

        # Should include the original YAML content
        assert "<original_yaml_content>" in result
        assert "fw_status is not search" in result

        # File should not be created
        assert not Path(file_path).exists()

    def test_yaml_syntax_error_includes_line_number(self) -> None:
        """Test that syntax errors include the specific line number where error occurred."""
        # Error is on line 3 (the when clause with problematic search)
        invalid_yaml = """---
- name: Test task
  when: var is not search('value: test')
"""
        file_path = Path(self.temp_dir) / "line_error.yml"

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_yaml)

        assert "ERROR" in result
        # Should contain line number in XML
        assert "<line_number>3</line_number>" in result
        # Should show the problematic line
        assert "when: var is not search" in result

    def test_reject_playbook_wrapper_with_hosts_in_task_file(self) -> None:
        """Test that task files with playbook wrapper (hosts) are rejected."""
        playbook_yaml = """---
- hosts: all
  become: true
  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present
"""
        # File path includes /tasks/ directory
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=playbook_yaml)

        # Should fail with playbook wrapper error
        assert "ERROR" in result
        assert "Task files must be FLAT lists, not playbooks" in result
        assert "<ansible_yaml_error>" in result
        assert "Playbook wrapper detected" in result
        assert "<fix_workflow>" in result
        assert "REMOVE the playbook wrapper" in result
        # File should not be created
        assert not Path(file_path).exists()

    def test_reject_playbook_wrapper_with_tasks_key_in_task_file(self) -> None:
        """Test that task files with 'tasks:' wrapper are rejected."""
        playbook_yaml = """---
- name: Configure web server
  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present
    - name: Start nginx
      ansible.builtin.service:
        name: nginx
        state: started
"""
        file_path = Path(self.temp_dir) / "tasks" / "webserver.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=playbook_yaml)

        # Should fail with playbook wrapper error
        assert "ERROR" in result
        assert "Task files must be FLAT lists" in result
        assert "tasks" in result
        assert "<correct_format>" in result
        # File should not be created
        assert not Path(file_path).exists()

    def test_reject_playbook_wrapper_with_import_playbook_in_task_file(self) -> None:
        """Test that task files with 'import_playbook' are rejected."""
        playbook_yaml = """---
- import_playbook: common.yml
- import_playbook: webserver.yml
"""
        file_path = Path(self.temp_dir) / "tasks" / "site.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=playbook_yaml)

        # Should fail with playbook wrapper error
        assert "ERROR" in result
        assert "Playbook wrapper detected" in result
        assert not Path(file_path).exists()

    def test_accept_valid_flat_task_list_in_task_file(self) -> None:
        """Test that valid flat task lists in /tasks/ directory are accepted."""
        valid_tasks = """---
- name: Install nginx
  ansible.builtin.package:
    name: nginx
    state: present

- name: Start nginx service
  ansible.builtin.service:
    name: nginx
    state: started
    enabled: true

- name: Create config directory
  ansible.builtin.file:
    path: /etc/nginx/conf.d
    state: directory
    mode: '0755'
"""
        file_path = Path(self.temp_dir) / "tasks" / "nginx.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=valid_tasks)

        # Should succeed
        assert "Successfully wrote" in result
        assert Path(file_path).exists()

        with Path(file_path).open() as f:
            content = f.read()

        # Should have the tasks
        assert "Install nginx" in content
        assert "Start nginx service" in content
        assert "ansible.builtin.package" in content

    def test_playbook_wrapper_allowed_outside_task_directory(self) -> None:
        """Test that playbook structure is allowed in files outside /tasks/ directory."""
        playbook_yaml = """---
- hosts: all
  become: true
  tasks:
    - name: Install nginx
      ansible.builtin.package:
        name: nginx
        state: present
"""
        # File NOT in tasks directory
        file_path = Path(self.temp_dir) / "playbooks" / "site.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=playbook_yaml)

        # Should succeed - playbooks are allowed outside /tasks/
        assert "Successfully wrote" in result
        assert Path(file_path).exists()

    def test_ari_validation_passes_for_valid_taskfile(self) -> None:
        """Test that ARI validation passes for valid taskfile with FQCN."""
        valid_tasks = """---
- name: Install nginx package
  ansible.builtin.apt:
    name: nginx
    state: present

- name: Start nginx service
  ansible.builtin.systemd:
    name: nginx
    state: started
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=valid_tasks)

        # Should succeed with no warnings
        assert "Successfully wrote" in result
        assert "WARNING" not in result
        assert Path(file_path).exists()

    def test_ari_validation_detects_missing_fqcn(self) -> None:
        """Test that ARI validation detects tasks without FQCN."""
        invalid_tasks = """---
- name: Install nginx package
  apt:
    name: nginx
    state: present
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_tasks)

        # Should write file but return warning
        assert "WARNING" in result
        assert "validation issues" in result
        assert Path(file_path).exists()

        # Should have structured error format
        assert "<ansible_lint_errors>" in result
        assert "<validation_errors>" in result
        assert "R301" in result  # Non-FQCN rule
        assert "apt → ansible.builtin.apt" in result

        # Should have fix workflow
        assert "<fix_workflow>" in result
        assert "Non-FQCN" in result

    def test_ari_validation_detects_missing_task_name(self) -> None:
        """Test that ARI validation detects tasks without name."""
        invalid_tasks = """---
- ansible.builtin.apt:
    name: nginx
    state: present
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_tasks)

        # Should write file but return warning
        assert "WARNING" in result
        assert "validation issues" in result
        assert Path(file_path).exists()

        # Should have structured error format
        assert "<ansible_lint_errors>" in result
        assert "R303" in result  # Task without name rule
        assert "Task Without Name" in result or "unnamed task" in result

    def test_ari_validation_detects_multiple_issues(self) -> None:
        """Test that ARI validation detects multiple issues in one file."""
        invalid_tasks = """---
- name: Install nginx
  apt:
    name: nginx
    state: present

- service:
    name: nginx
    state: started
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_tasks)

        # Should write file but return warning
        assert "WARNING" in result
        assert "validation issues" in result
        assert Path(file_path).exists()

        # Should detect both issues
        assert "R301" in result or "R303" in result  # At least one rule violation
        assert "issue(s)" in result or "Found" in result

    def test_ari_validation_only_runs_on_taskfiles(self) -> None:
        """Test that ARI validation only runs for files in tasks/ directory."""
        # Use non-FQCN in a playbook - should not trigger ARI validation
        playbook_yaml = """---
- name: Configure web server
  hosts: webservers
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
"""
        file_path = Path(self.temp_dir) / "playbooks" / "site.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=playbook_yaml)

        # Should succeed without ARI validation warnings
        assert "Successfully wrote" in result
        assert "WARNING" not in result
        assert "<ansible_lint_errors>" not in result
        assert Path(file_path).exists()

    def test_ari_validation_skips_non_yaml_extensions(self) -> None:
        """Test that ARI validation only runs on .yml/.yaml files."""
        # File in tasks/ but without yaml extension
        tasks_content = """---
- name: Install nginx
  apt:
    name: nginx
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.txt"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=tasks_content)

        # Should succeed without ARI validation
        assert (
            "Successfully wrote" in result or "ERROR" in result
        )  # May fail on extension
        # If it writes, it should not run ARI validation
        if "Successfully wrote" in result:
            assert "WARNING" not in result

    def test_ari_validation_includes_line_numbers(self) -> None:
        """Test that ARI validation errors include line numbers."""
        invalid_tasks = """---
- name: Install nginx
  apt:
    name: nginx
    state: present
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=invalid_tasks)

        # Should include line numbers in error messages
        assert "WARNING" in result
        # Line number format: "main.yml:1" or similar
        assert "main.yml:" in result
        # Should have a line number
        assert any(char.isdigit() for char in result)
