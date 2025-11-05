# only-builtins

Restricts playbooks to use only actions from the `ansible.builtin` collection.

## Problematic code

```yaml
- name: Deploy a Helm chart
  kubernetes.core.helm:
    name: test
    chart_ref: stable/prometheus
    release_namespace: monitoring

- name: Use community module
  community.general.docker_container:
    name: myapp
    image: nginx
```

## Correct code

```yaml
- name: Run a shell command
  ansible.builtin.shell: echo Using builtin collection only

- name: Copy a file
  ansible.builtin.copy:
    src: myfile.txt
    dest: /tmp/myfile.txt
```

**Tip**: This is an opt-in rule useful for environments where only core Ansible modules are allowed or available.
