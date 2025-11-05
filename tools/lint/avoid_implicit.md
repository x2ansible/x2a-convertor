# avoid-implicit

Use explicit jinja templates instead of relying on undocumented automatic conversions.

## Problematic code

```yaml
- name: Write file content
  ansible.builtin.copy:
    content: { "foo": "bar" }  # Implicit conversion
    dest: /tmp/foo.txt
```

## Correct code

```yaml
- name: Write file content
  vars:
    content: { "foo": "bar" }
  ansible.builtin.copy:
    content: "{{ content | to_json }}"  # Explicit conversion
    dest: /tmp/foo.txt
```

Tip: Always use explicit jinja filters like `to_json`, `to_yaml` for data conversion.
