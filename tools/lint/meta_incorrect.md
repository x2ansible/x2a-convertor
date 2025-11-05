# meta-incorrect

Set meaningful values for `author`, `description`, `company`, and `license` in `meta/main.yml`, not defaults.

## Problematic code

```yaml
galaxy_info:
  author: your name
  description: your role description
  company: your company (optional)
  license: license (GPL-2.0-or-later, MIT, etc)
```

## Correct code

```yaml
galaxy_info:
  author: Leroy Jenkins
  description: This role will set you free.
  company: Red Hat
  license: Apache
```
