# deprecated-bare-vars

Use full variable syntax `{{ var }}` for variables or convert to a list for string literals.

## Problematic code

```yaml
- ansible.builtin.debug:
    msg: "{{ item }}"
  with_items: foo
```

## Correct code

```yaml
# If foo is a string literal:
- ansible.builtin.debug:
    msg: "{{ item }}"
  with_items:
    - foo

# If foo is a variable:
- ansible.builtin.debug:
    msg: "{{ item }}"
  with_items: "{{ foo }}"
```

Tip: Always use `{{ }}` syntax for variables to avoid ambiguity.
