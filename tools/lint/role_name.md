# role-name

Role names must contain only lowercase alphanumeric characters and underscores, starting with an alphabetic character.

## Problematic code

```yaml
roles:
  - 1myrole # <- Does not start with an alphabetic character
  - myrole2[*^ # <- Contains invalid special characters
  - myRole_3 # <- Contains uppercase characters
```

## Correct code

```yaml
roles:
  - myrole1 # <- Starts with an alphabetic character
  - myrole2 # <- Only alphanumeric characters
  - myrole_3 # <- Only lowercase with underscores
```

**Tip:** Use `role-name[path]` to avoid using paths when importing roles - use fully qualified names instead.
