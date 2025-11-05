# meta-no-tags

Galaxy tags must use only lowercase letters and numbers.

## Problematic code

```yaml
galaxy_info:
  galaxy_tags: [MyTag#1, MyTag&^-]
```

## Correct code

```yaml
galaxy_info:
  galaxy_tags: [mytag1, mytag2]
```
