# no-jinja-when

Conditional statements are already processed as Jinja expressions, so do not wrap them in `{{ }}`.

## Problematic code

```yaml
- name: Shut down Debian systems
  ansible.builtin.command: /sbin/shutdown -t now
  when: "{{ ansible_facts['os_family'] == 'Debian' }}"
```

## Correct code

```yaml
- name: Shut down Debian systems
  ansible.builtin.command: /sbin/shutdown -t now
  when: ansible_facts['os_family'] == "Debian"
```

**Tip:** The rule is to always use `{{ }}` except with `when`, `failed_when`, and `changed_when` keys.
