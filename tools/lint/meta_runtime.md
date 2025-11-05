# meta-runtime

The `requires_ansible` key must specify a currently supported ansible-core version using full version numbers (e.g., `2.17.0`), not short forms (e.g., `2.17`).

## Problematic code

```yaml
# Unsupported version
requires_ansible: ">=2.9"
```

```yaml
# Invalid - missing patch version
requires_ansible: "2.17"
```

## Correct code

```yaml
requires_ansible: ">=2.17.0"
```

**Tip:** Always use full semantic version (major.minor.patch) and ensure it's a currently supported ansible-core version (e.g., >=2.15.0, >=2.16.0, >=2.17.0, >=2.18.0).
