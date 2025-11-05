# deprecated-local-action

Use `delegate_to: localhost` instead of the deprecated `local_action` syntax.

## Problematic code

```yaml
- name: Task example
  local_action:
    module: ansible.builtin.debug
```

## Correct code

```yaml
- name: Task example
  ansible.builtin.debug:
  delegate_to: localhost
```

Tip: This rule can be automatically fixed using ansible-lint's `--fix` option.
