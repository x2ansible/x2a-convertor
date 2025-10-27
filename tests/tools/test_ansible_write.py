import os
import shutil
import tempfile

from tools.ansible_write import AnsibleWriteTool


class TestAnsibleWriteTool:
    """Test cases for AnsibleWriteTool."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.tool = AnsibleWriteTool()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self) -> None:
        """Clean up test fixtures."""
        if os.path.exists(self.temp_dir):
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
        file_path = os.path.join(self.temp_dir, "users.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        # Should succeed
        assert "Successfully wrote" in result
        assert file_path in result
        assert os.path.exists(file_path)

        # Verify the file content preserves Jinja2 templates
        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "configure.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "test.yml")

        result = self.tool._run(file_path=file_path, yaml_content=json_content)

        # Should fail with JSON error
        assert "ERROR" in result
        assert "JSON input is not allowed" in result
        # File should not be created
        assert not os.path.exists(file_path)

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
        file_path = os.path.join(self.temp_dir, "tasks.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "invalid.yml")

        result = self.tool._run(file_path=file_path, yaml_content=invalid_yaml)

        # Should fail with YAML validation error
        assert "ERROR" in result
        assert "not valid" in result or "Fix following error" in result
        # File should not be created
        assert not os.path.exists(file_path)

    def test_write_empty_vars_file_with_comments(self) -> None:
        """Test writing an empty vars file with only comments."""
        yaml_content = """---
# Variables for the application
# Currently no variables defined
"""
        file_path = os.path.join(self.temp_dir, "vars.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        # Should succeed
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

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
        file_path = os.path.join(self.temp_dir, "handlers.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

    def test_write_defaults_with_jinja2_filters(self) -> None:
        """Test writing defaults file with Jinja2 filters."""
        yaml_content = """---
app_version: "1.0.0"
app_port: 8080
app_config_path: "/etc/{{ app_name | default('myapp') }}"
app_log_level: "{{ log_level | default('INFO') | upper }}"
"""
        file_path = os.path.join(self.temp_dir, "defaults.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "formatted.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "test.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "formatted.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "empty.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

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
        file_path = os.path.join(self.temp_dir, "no_vars.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
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
        file_path = os.path.join(self.temp_dir, "whitespace.yml")

        result = self.tool._run(file_path=file_path, yaml_content=yaml_content)

        # Should succeed - whitespace-only is treated as empty
        assert "Successfully wrote" in result
        assert os.path.exists(file_path)
