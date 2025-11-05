# command-instead-of-shell

Use `command` module instead of `shell` unless you need shell features like pipes, redirects, or environment variable expansion.

## Problematic code

```yaml
- name: Echo a message
  ansible.builtin.shell: echo hello
  changed_when: false
```

## Correct code

```yaml
- name: Echo a message
  ansible.builtin.command: echo hello
  changed_when: false
```

Tip: Only use `shell` when you need shell-specific features like pipes (|), redirects (>), or variable expansion ($VAR).
