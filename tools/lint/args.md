# args

Validates task arguments against module documentation.

## Problematic code

```yaml
- name: Clone content repository
  ansible.builtin.git:  # Missing required 'repo' argument
    dest: /home/www
    version: master

- name: Enable service httpd
  ansible.builtin.systemd:  # Missing 'name' required by 'enabled'
    enabled: true

- name: Do not use mutually exclusive arguments
  ansible.builtin.command:
    cmd: /bin/echo  # cmd and argv are mutually exclusive
    argv:
      - Hello
```

## Correct code

```yaml
- name: Clone content repository
  ansible.builtin.git:
    repo: https://github.com/ansible/ansible-examples
    dest: /home/www
    version: master

- name: Enable service httpd
  ansible.builtin.systemd:
    name: httpd
    enabled: true

- name: Use command with cmd only
  ansible.builtin.command:
    cmd: "/bin/echo Hello"
```

Tip: Use `# noqa: args[module]` to skip validation when using complex jinja expressions.
