# galaxy

Collection galaxy.yml must have version >= 1.0.0, valid tags for certification, and include changelog/runtime files.

## Problematic code

```yaml
# galaxy.yml
namespace: bar
name: foo
version: 0.2.3  # Version should be >= 1.0.0
authors:
  - John
readme: README.md
description: "My collection"
# Missing required tags
```

## Correct code

```yaml
# galaxy.yml
namespace: bar
name: foo
version: 1.0.0  # Version >= 1.0.0
authors:
  - John
readme: README.md
description: "My collection"
license:
  - Apache-2.0
repository: https://github.com/ORG/REPO_NAME
tags: [networking, infrastructure]  # Required tags included
```

**Tip:** Required tags for certification: `application`, `cloud`, `database`, `infrastructure`, `linux`, `monitoring`, `networking`, `security`, `storage`, `tools`, `windows`. Include a changelog file (CHANGELOG.md/rst or changelogs/changelog.yaml) and meta/runtime.yml.
