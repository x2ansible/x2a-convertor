# galaxy-version-incorrect

Collection version in galaxy.yml must be >= 1.0.0 to follow semantic versioning standards enforced in Ansible Automation Platform.

## Problematic code

```yaml
# galaxy.yml
namespace: namespace_name
name: collection_name
version: "0.0.1"  # Version must be >= 1.0.0
readme: README.md
authors:
  - Author1
license:
  - MIT
```

## Correct code

```yaml
# galaxy.yml
namespace: namespace_name
name: collection_name
version: "1.0.0"  # Version >= 1.0.0
readme: README.md
authors:
  - Author1
license:
  - MIT
```

**Tip:** This is an opt-in rule. Enable it in your ansible-lint config with `enable_list: [galaxy-version-incorrect]`.
