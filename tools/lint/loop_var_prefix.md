# loop-var-prefix

Use unique loop variable names with proper prefixes to avoid conflicts in nested loops.

## Problematic code

```yaml
# Missing loop_var - uses implicit "item"
- name: Task without loop_var
  ansible.builtin.debug:
    var: item
  loop:
    - foo
    - bar

# Wrong prefix
- name: Task with wrong prefix
  ansible.builtin.debug:
    var: zz_item
  loop:
    - foo
    - bar
  loop_control:
    loop_var: zz_item  # zz is not the role name
```

## Correct code

```yaml
- name: Task with proper loop_var prefix
  ansible.builtin.debug:
    var: myrole_item
  loop:
    - foo
    - bar
  loop_control:
    loop_var: myrole_item  # Unique name with role prefix
```

Tip: Configure the prefix pattern in `.ansible-lint` with `loop_var_prefix: "^(__|{role}_)"` and enable with `enable_list: [loop-var-prefix]`.
