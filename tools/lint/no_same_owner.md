# no-same-owner

Prevents transferring owner and group across hosts, which can cause permission errors or leak sensitive information.

## Problematic code

```yaml
- name: Synchronize conf file
  ansible.posix.synchronize:
    src: /path/conf.yaml
    dest: /path/conf.yaml

- name: Extract tarball
  ansible.builtin.unarchive:
    src: "{{ file }}.tar.gz"
    dest: /my/path/
```

## Correct code

```yaml
- name: Synchronize conf file
  ansible.posix.synchronize:
    src: /path/conf.yaml
    dest: /path/conf.yaml
    owner: false
    group: false

- name: Extract tarball
  ansible.builtin.unarchive:
    src: "{{ file }}.tar.gz"
    dest: /my/path/
    extra_opts:
      - --no-same-owner
```

**Tip**: Always explicitly set `owner: false` and `group: false` for synchronize, and use `--no-same-owner` for unarchive operations.
