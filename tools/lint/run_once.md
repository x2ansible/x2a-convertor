# run-once

Using `run_once` with `strategy: free` behaves unpredictably.

## Problematic code

```yaml
strategy: free # <- Avoid with run_once
tasks:
  - name: Task with run_once
    ansible.builtin.debug:
      msg: "Test"
    run_once: true # <- May not work as expected
```

## Correct code

```yaml
strategy: linear
tasks:
  - name: Task with run_once
    ansible.builtin.debug:
      msg: "Test"
    run_once: true
```

Or suppress if intentional:

```yaml
- name: Task with run_once # noqa: run-once[task]
  ansible.builtin.debug:
    msg: "Test"
  run_once: true
```

**Tip:** This rule always triggers as a warning because runtime strategy can differ from the file value. Use `# noqa: run-once[task]` to acknowledge and ignore.
