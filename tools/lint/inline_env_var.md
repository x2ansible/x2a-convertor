# inline-env-var

Do not set environment variables in the `ansible.builtin.command` module.

## Problematic code

```yaml
- name: Set environment variable
  ansible.builtin.command: MY_ENV_VAR=my_value some_command
```

## Correct code (Option 1: Use environment keyword)

```yaml
- name: Set environment variable
  ansible.builtin.command: some_command
  environment:
    MY_ENV_VAR: my_value
```

## Correct code (Option 2: Use shell module)

```yaml
- name: Set environment variable
  ansible.builtin.shell: MY_ENV_VAR=my_value some_command
```

Tip: Prefer `environment` keyword with `command` module for clarity.
