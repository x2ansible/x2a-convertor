# risky-shell-pipe

Always set `pipefail` when piping shell commands to avoid hiding failures in earlier commands.

## Problematic code

```yaml
- name: Pipeline without pipefail
  ansible.builtin.shell: false | cat
```

## Correct code

```yaml
- name: Pipeline with pipefail
  ansible.builtin.shell:
    cmd: set -o pipefail && false | cat
    executable: /bin/bash

- name: Pipeline with pipefail, multi-line
  ansible.builtin.shell:
    cmd: |
      set -o pipefail
      false | cat
    executable: /bin/bash
```

**Tip**: This rule does not apply to PowerShell (pwsh executable).
