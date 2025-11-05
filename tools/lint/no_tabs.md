# no-tabs

Disallows tab characters which can cause unexpected display or formatting issues.

## Problematic code

```yaml
- name: Trigger the rule
  ansible.builtin.debug:
    msg: "Using the \t character can cause formatting issues."
```

## Correct code

```yaml
- name: Do not trigger the rule
  ansible.builtin.debug:
    msg: "Using space characters avoids formatting issues."
```

**Tip**: Configure your editor to replace tabs with spaces automatically. This rule does not apply to `ansible.builtin.lineinfile` module where tabs may be intentional.
