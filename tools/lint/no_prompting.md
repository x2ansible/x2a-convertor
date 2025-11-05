# no-prompting

Disallows `vars_prompt` and `ansible.builtin.pause` to ensure playbooks can run unattended in CI/CD pipelines.

## Problematic code

```yaml
- name: Example playbook
  hosts: all
  vars_prompt:
    - name: username
      prompt: What is your username?
```

```yaml
- name: Pause for 5 minutes
  ansible.builtin.pause:
    minutes: 5
```

## Correct code

```yaml
- name: Example playbook
  hosts: all
  vars:
    username: "{{ lookup('env', 'USERNAME') }}"
```

```yaml
- name: Wait for condition
  ansible.builtin.wait_for:
    timeout: 300
```

**Tip:** Use environment variables or vault files for credentials instead of prompting.
