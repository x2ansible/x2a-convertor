# risky-octal

File permissions must be strings with a leading zero or symbolic modes to avoid decimal interpretation.

## Problematic code

```yaml
- name: Set file permissions
  ansible.builtin.file:
    path: /etc/foo.conf
    mode: 644  # Interpreted as decimal 644, not octal!
```

## Correct code

```yaml
- name: Set file permissions with quoted octal
  ansible.builtin.file:
    path: /etc/foo.conf
    mode: "0644"  # Quoted with leading zero

- name: Set file permissions with symbolic mode
  ansible.builtin.file:
    path: /etc/foo.conf
    mode: u=rw,g=r,o=r  # Symbolic notation also works
```

**Tip**: YAML interprets `0644` as decimal 420. Always quote octal values: `"0644"` or `"0o644"`.
