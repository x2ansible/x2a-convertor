# literal-compare

Use `when: var` instead of `when: var == True`, and `when: not var` instead of `when: var == False`.

## Problematic code

```yaml
- name: Print environment variable
  ansible.builtin.command: echo $MY_ENV_VAR
  when: ansible_os_family == True # Unnecessarily complex
```

## Correct code

```yaml
- name: Print environment variable
  ansible.builtin.command: echo $MY_ENV_VAR
  when: ansible_os_family # Simple and clean
```

**Tip:** For negative conditions, use `when: not var` instead of `when: var == False`.
