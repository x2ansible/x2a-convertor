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
        assert "YAML validation failed" in result
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

    def test_valid_ansible_yaml_written_verbatim(self) -> None:
        """Test writing valid Ansible YAML content preserves original formatting."""
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
            # Content is written verbatim, so the --- separator is preserved
            assert content.startswith("---")
            assert "name: Install nginx" in content
            assert "ansible.builtin.package:" in content
            assert "name: nginx" in content
            assert "state: present" in content

    def test_comments_preserved(self) -> None:
        """Test that comments are preserved since content is written verbatim."""
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
            # Comments are preserved because the file is written verbatim
            assert "# This is a comment" in content
            assert "# Another comment" in content
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

    def test_write_non_fqcn_module_succeeds(self) -> None:
        """Test that non-FQCN modules are written without warnings (ARI removed)."""
        yaml_content = """---
- name: Install package
  apt:
    name: nginx
    state: present
"""
        file_path = Path(self.temp_dir) / "tasks" / "main.yml"
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        result = self.tool._run(file_path=str(file_path), yaml_content=yaml_content)

        assert "Successfully wrote" in result
        assert "WARNING" not in result
        assert Path(file_path).exists()
