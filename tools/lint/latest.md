# latest

Use specific commit hashes or version tags instead of generic version references like `HEAD` or `tip`.

## Problematic code

```yaml
- name: Risky use of git module
  ansible.builtin.git:
    repo: "https://github.com/ansible/ansible-lint"
    version: HEAD # Non-deterministic
```

## Correct code

```yaml
- name: Safe use of git module
  ansible.builtin.git:
    repo: "https://github.com/ansible/ansible-lint"
    version: abcd1234ef56789... # Specific commit hash
```

**Tip:** If you intentionally want the latest version, add `# noqa: latest` to suppress the warning.
