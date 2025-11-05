# jinja

Jinja2 templates must have proper spacing and be syntactically valid; fields like `when` have implicit templating and should not use `{{ }}`.

## Problematic code

```yaml
- name: Some task
  vars:
    foo: "{{some|dict2items}}" # jinja[spacing] - no spaces
    bar: "{{ & }}" # jinja[invalid] - invalid syntax
  when: "{{ foo | bool }}" # jinja[spacing] - unnecessary braces in when
```

## Correct code

```yaml
- name: Some task
  vars:
    foo: "{{ some | dict2items }}"
    bar: "{{ '&' }}"
  when: foo | bool
```

**Tip:** Follow Black formatting rules for spacing. Fields with implicit templating (`when`, `changed_when`, `failed_when`, `until`) don't need `{{ }}`.
