# syntax-check

Runs `ansible-playbook --syntax-check` on all playbooks.

## Problematic code

```yaml
hosts: "{{ my_hosts }}" # <- Assumes variable is defined
tasks: []
```

## Correct code

```yaml
hosts: "{{ my_hosts | default([]) }}"
tasks: []
```

## Common error types

- `syntax-check[unknown-module]`: Module/collection not installed - ensure all dependencies are in `requirements.yml`
- `syntax-check[empty-playbook]`: Empty playbook file
- `syntax-check[missing-file]`: Referenced file not found
- `syntax-check[malformed]`: Invalid YAML or Ansible syntax

**Tip:** Use Jinja `default()` filter to provide fallback values for undefined variables. List collections in `requirements.yml` for the linter to install missing dependencies.
