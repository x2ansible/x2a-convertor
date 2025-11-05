# sanity

Only specific sanity test ignores are permitted in `tests/sanity/ignore-x.x.txt` files.

## Problematic code

```
# tests/sanity/ignore-x.x.txt
plugins/module_utils/ansible_example_module.py import-3.6!skip
```

## Correct code

```
# tests/sanity/ignore-x.x.txt
plugins/module_utils/ansible_example_module.py import-2.7!skip
```

**Allowed ignores:** `validate-modules:missing-gplv3-license`, `action-plugin-docs`, `import-2.6`, `import-2.7`, `import-3.5`, `compile-2.6`, `compile-2.7`, `compile-3.5`, `shellcheck`, `shebang`, `pylint:used-before-assignment` (and their `!skip` variants).
