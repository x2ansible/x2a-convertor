# package-latest

Avoid using `state: latest` with package managers as it can install additional packages and cause unexpected updates.

## Problematic code

```yaml
- name: Install Ansible
  ansible.builtin.dnf:
    name: ansible
    state: latest  # Installs latest and may add new packages

- name: Update sudo
  ansible.builtin.dnf:
    name: sudo
    state: latest
    update_only: false  # Updates AND installs packages
```

## Correct code

```yaml
- name: Install Ansible with pinned version
  ansible.builtin.dnf:
    name: ansible-2.12.7.0
    state: present

- name: Update sudo only (no new installs)
  ansible.builtin.dnf:
    name: sudo
    state: latest
    update_only: true  # Updates only, won't install additional packages
```

**Tip**: In production, always pin package versions with `state: present` to ensure predictable deployments.
