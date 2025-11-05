# deprecated-module

Avoid using deprecated modules as they are not maintained and may pose security risks.

## Problematic code

```yaml
- name: Configure VLAN ID
  ansible.netcommon.net_vlan:  # Deprecated module
    vlan_id: 20
```

## Correct code

```yaml
- name: Configure VLAN ID
  dellemc.enterprise_sonic.sonic_vlans:  # Platform-specific replacement
    config:
      - vlan_id: 20
```

Tip: Check the [Ansible module index](https://docs.ansible.com/ansible/latest/collections/index_module.html) for replacement modules and deprecation timelines.
