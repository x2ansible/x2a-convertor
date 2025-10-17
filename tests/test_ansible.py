import os
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
        import shutil

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_valid_ansible_yaml(self) -> None:
        """Test writing valid Ansible YAML content."""
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
            assert content == yaml_content

    def test_ansible_yaml_with_jinja2_variables(self) -> None:
        """Test writing Ansible YAML with Jinja2 variables."""
        yaml_content = """---
- name: Configure site
  ansible.builtin.template:
    src: site.conf.j2
    dest: /etc/nginx/sites-available/{{ item }}.conf
  loop:
    - test.cluster.local
    - ci.cluster.local
"""
        file_path = os.path.join(self.temp_dir, "jinja2_vars.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
            content = f.read()
            assert "{{ item }}" in content

    def test_ansible_yaml_with_jinja2_in_dict(self) -> None:
        """Test writing Ansible YAML with Jinja2 templates in dictionary values."""
        yaml_content = """---
- name: Generate SSL certificates
  community.crypto.openssl_certificate:
    path: /etc/ssl/certs/{{ item }}.crt
    private_key_path: /etc/ssl/private/{{ item }}.key
    provider: selfsigned
  loop:
    - test.cluster.local
    - ci.cluster.local
"""
        file_path = os.path.join(self.temp_dir, "jinja2_dict.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

        with open(file_path, "r") as f:
            content = f.read()
            assert "{{ item }}" in content
            assert ".crt" in content

    def test_ansible_yaml_with_when_conditionals(self) -> None:
        """Test writing Ansible YAML with Jinja2 conditionals."""
        yaml_content = """---
- name: Configure multiple sites
  ansible.builtin.template:
    src: site.conf.j2
    dest: /etc/nginx/sites-available/{{ item.name }}.conf
  loop: "{{ sites }}"
  when: item.enabled | default(true)
"""
        file_path = os.path.join(self.temp_dir, "jinja2_when.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

    def test_ansible_yaml_with_complex_jinja2(self) -> None:
        """Test writing Ansible YAML with complex Jinja2 expressions."""
        yaml_content = """---
- name: Set fact with conditional
  ansible.builtin.set_fact:
    nginx_worker_processes: "{{ ansible_processor_vcpus | default(1) }}"

- name: Create directory
  ansible.builtin.file:
    path: "{{ item.path }}"
    state: directory
    owner: "{{ item.owner | default('root') }}"
  loop: "{{ directories }}"
"""
        file_path = os.path.join(self.temp_dir, "complex_jinja2.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

    def test_valid_ansible_playbook(self) -> None:
        """Test writing a complete Ansible playbook."""
        yaml_content = """---
- name: Configure Nginx multisite
  hosts: all
  become: yes
  tasks:
    - name: Include security tasks
      include_tasks: security.yml
    - name: Include Nginx tasks
      include_tasks: nginx.yml
"""
        file_path = os.path.join(self.temp_dir, "playbook.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

    def test_ansible_handlers(self) -> None:
        """Test writing Ansible handlers file."""
        yaml_content = """---
- name: Restart Nginx
  ansible.builtin.service:
    name: nginx
    state: restarted

- name: Reload Nginx
  ansible.builtin.service:
    name: nginx
    state: reloaded
"""
        file_path = os.path.join(self.temp_dir, "handlers.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

    def test_ansible_vars_file(self) -> None:
        """Test writing Ansible variables file."""
        yaml_content = """---
nginx_port: 80
nginx_user: www-data
document_root: /var/www/html
"""
        file_path = os.path.join(self.temp_dir, "vars.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

    def test_empty_yaml_with_comment(self) -> None:
        """Test writing empty YAML file with just a comment."""
        yaml_content = """---
# Role variables
"""
        file_path = os.path.join(self.temp_dir, "empty_vars.yml")
        result = self.tool._run(file_path, yaml_content)

        # Should succeed because it starts with a comment
        assert "Successfully wrote valid Ansible YAML" in result
        assert os.path.exists(file_path)

    def test_invalid_yaml_syntax(self) -> None:
        """Test validation of invalid YAML syntax."""
        yaml_content = """---
name: test
  invalid: indentation
    more: problems
"""
        file_path = os.path.join(self.temp_dir, "invalid.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "error" in result.lower()
        assert "File not written" in result
        assert not os.path.exists(file_path)

    def test_malformed_yaml(self) -> None:
        """Test validation of malformed YAML."""
        yaml_content = """---
key: [unclosed bracket
another: value
"""
        file_path = os.path.join(self.temp_dir, "malformed.yml")
        result = self.tool._run(file_path, yaml_content)

        assert "error" in result.lower()
        assert "File not written" in result
        assert not os.path.exists(file_path)

    def test_preserves_formatting(self) -> None:
        """Test that original formatting is preserved."""
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
            # Verify formatting is preserved
            assert "# This is a comment" in content
            assert "# Another comment" in content
            assert yaml_content == content

    def test_json_input(self) -> None:
        """Test writing Ansible YAML with JSON input."""
        yaml_content = """
{
    "json": "shall",
    "not": "pass"
}
"""
        file_path = os.path.join(self.temp_dir, "json.yml")
        result = self.tool._run(file_path, yaml_content)
        assert "error" in result.lower()
        assert "JSON input is not allowed" in result
        assert not os.path.exists(file_path)
