# partial-become

When using `become_user` to change users, you must also set `become: true` in the same location.

## Problematic code

```yaml
- name: Start httpd as apache user
  ansible.builtin.service:
    name: httpd
    state: started
  become_user: apache  # Won't work without become: true
```

## Correct code

```yaml
- name: Start httpd as apache user
  ansible.builtin.service:
    name: httpd
    state: started
  become: true
  become_user: apache  # Both must be in same location
```

**Tip**: Always define both `become` and `become_user` together at the same level (task or play) to avoid inheritance issues.
