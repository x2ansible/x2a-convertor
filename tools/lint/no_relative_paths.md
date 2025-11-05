# no-relative-paths

Disallows relative paths in `ansible.builtin.copy` and `ansible.builtin.template` modules.

## Problematic code

```yaml
- name: Template a file
  ansible.builtin.template:
    src: ../my_templates/foo.j2
    dest: /etc/file.conf

- name: Copy with variable
  ansible.builtin.copy:
    src: "{{ source_path }}"  # where source_path: ../../files/foo.txt
    dest: /etc/foo.conf
```

## Correct code

```yaml
- name: Template a file
  ansible.builtin.template:
    src: foo.j2  # from templates/ directory
    dest: /etc/file.conf

- name: Copy with variable
  ansible.builtin.copy:
    src: "{{ source_path }}"  # where source_path: foo.txt
    dest: /etc/foo.conf
```

**Tip**: Store files in `files/` and templates in `templates/` directories, or use absolute paths if resources are outside your playbook directory.
