# no-log-password

When using loops with sensitive data like passwords, always set `no_log: true` to prevent secrets from being written to logs.

## Problematic code

```yaml
- name: Log user passwords
  ansible.builtin.user:
    name: john_doe
    password: "{{ item }}"
  with_items:
    - wow
  no_log: false
```

## Correct code

```yaml
- name: Do not log user passwords
  ansible.builtin.user:
    name: john_doe
    password: "{{ item }}"
  with_items:
    - wow
  no_log: true
```

**Tip:** This is an opt-in rule. Enable it in your ansible-lint config with `enable_list: [no-log-password]`.
