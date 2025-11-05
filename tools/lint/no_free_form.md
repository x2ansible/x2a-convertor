# no-free-form

Free-form (inline) module syntax can produce subtle bugs and prevents proper IDE validation.

## Problematic code

```yaml
- name: Create a placeholder file
  ansible.builtin.command: chdir=/tmp touch foo

- name: Use raw to echo
  ansible.builtin.raw: executable=/bin/bash echo foo
```

## Correct code

```yaml
- name: Create a placeholder file
  ansible.builtin.command:
    cmd: touch foo
    chdir: /tmp

- name: Use raw to echo
  ansible.builtin.raw: echo foo
  args:
    executable: /bin/bash
```

**Tip:** Always pass a dictionary to modules instead of strings containing `=` to avoid triggering free-form parsing.
