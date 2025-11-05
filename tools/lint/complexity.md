# complexity

Ansible content is too complex and should be refactored for better readability and maintainability.

## complexity[tasks]

Triggered when a file has more than 100 tasks.

## Problematic code

```yaml
# playbook.yml with 150+ tasks
- name: Task 1
  ansible.builtin.debug: msg="..."
- name: Task 2
  ansible.builtin.debug: msg="..."
# ... 148 more tasks
```

## Correct code

```yaml
- name: Include web server tasks
  ansible.builtin.include_tasks: webserver_tasks.yml

- name: Include database tasks
  ansible.builtin.include_tasks: database_tasks.yml
```

## complexity[nesting]

Triggered when a block contains too many tasks (default: 20).

Tip: Break down complex playbooks into logical, reusable task files.
