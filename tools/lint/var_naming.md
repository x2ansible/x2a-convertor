# var-naming

Variable names must contain only lowercase alphanumeric characters and underscores, starting with an alphabetic or underscore character.

## Problematic code

```yaml
vars:
  CamelCase: true # <- Mixed case
  ALL_CAPS: bar # <- All uppercase
  v@r!able: baz # <- Special characters
  hosts: [] # <- Reserved Ansible name
  role_name: boo # <- Special magic variable
```

## Correct code

```yaml
vars:
  lowercase: true
  no_caps: bar
  variable: baz
  my_hosts: []
  my_role_name: boo
```

## Common error types

- `var-naming[pattern]`: Name doesn't match regex pattern
- `var-naming[no-reserved]`: Using Ansible reserved names
- `var-naming[read-only]`: Attempting to set read-only special variable
- `var-naming[no-role-prefix]`: Role variables should use `role_name_` prefix
- `var-naming[no-keyword]`: Cannot use Python keywords

**Tip:** Avoid Ansible magic variables. Role variables should be prefixed with the role name. Configure pattern with `var_naming_pattern` in `.ansible-lint`.
