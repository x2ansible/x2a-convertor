# empty-string-compare

Use length filters instead of comparing variables to empty strings in conditionals.

## Problematic code

```yaml
- name: Shut down
  ansible.builtin.command: /sbin/shutdown -t now
  when: ansible_os_family == ""  # Empty string comparison

- name: Reboot
  ansible.builtin.command: /sbin/reboot
  when: ansible_os_family != ""  # Empty string comparison
```

## Correct code

```yaml
- name: Shut down
  ansible.builtin.command: /sbin/shutdown -t now
  when: ansible_os_family | length == 0

- name: Reboot
  ansible.builtin.command: /sbin/reboot
  when: ansible_os_family | length > 0
```

Tip: For simple existence checks, use `when: var` or `when: not var` without comparison operators.
