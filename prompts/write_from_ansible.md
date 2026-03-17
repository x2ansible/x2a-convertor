
## Ansible-to-Ansible Modernization Rules

These rules apply ONLY when modernizing a legacy Ansible role into a modern one.

### VALUE-TYPE PRESERVATION — CRITICAL:
Distinguish between two categories of values:

1. ANSIBLE CONTROL VALUES — Modernize these:
   - enabled: yes → enabled: true  (Ansible keyword)
   - become: yes → become: true
   - state: present, state: started (module parameters)

2. APPLICATION-DOMAIN VALUES — Preserve EXACTLY:
   - Values rendered into config files via templates ({% raw %}{{ variable }}{% endraw %})
   - Dict/list values representing application settings, not Ansible behavior
   Examples:
     WRONG: sendfile: true  (renders as "True" in nginx.conf — breaks it)
     CORRECT: sendfile: "on" (renders as "on" in nginx.conf — correct)
   Rule: If a variable's value will be rendered into a non-Ansible config
   file via {% raw %}{{ variable }}{% endraw %}, preserve its ORIGINAL string type and value.

### TASK PRESERVATION — CRITICAL:
- You MUST preserve ALL tasks from the source role. Do NOT remove tasks.
- Preserve ALL when: conditions — even if they seem redundant.
- Preserve ALL notify: directives with the EXACT handler name from the source.
- If the source has N tasks, the migrated role must have >= N equivalent tasks.

### TASK-LEVEL DIRECTIVES — PRESERVE ALL:
Preserve these directives from every source task where they appear:
- environment: — sets env vars during task execution
- register: — captures task output
- changed_when: / failed_when: — idempotency controls
- tags: — task filtering
- delegate_to: — delegation
- no_log: — security

### VARS (vars/main.yml) — PRESERVE CONTENT:
When migrating vars/main.yml, you MUST preserve ALL original variable definitions.
- Read the source vars/main.yml and copy EVERY variable name and value
- Modernize values (yes/no → true/false, unquoted octals → quoted)
- Do NOT replace actual variable definitions with placeholder comments
- If the source has OS-specific package lists, platform paths, or other concrete values, keep them

WRONG (replaces variables with comments):
```yaml
---
# OS-specific variables are defined here
# Package lists and paths should be set per environment
```

CORRECT (preserves all original variables):
```yaml
---
nginx_packages_redhat:
  - nginx
  - openssl
nginx_packages_debian:
  - nginx
  - ssl-cert
nginx_config_path: /etc/nginx/nginx.conf
```

### DEFAULTS (defaults/main.yml) — PRESERVE CONTENT:
Same rules apply to defaults/main.yml:
- Copy EVERY variable name and value from the source
- Do NOT empty data structures (do NOT change a list of items to [])
- Do NOT simplify complex default values — preserve them verbatim

### VARS vs DEFAULTS — PRESERVE SEPARATION:
- Variables in vars/main.yml MUST stay in vars/main.yml
- Variables in defaults/main.yml MUST stay in defaults/main.yml
- Do NOT move variables between these directories
- vars/ has HIGHER precedence than defaults/ — this separation is intentional

### ANTI-HALLUCINATION — VARIABLE VALUES:
- Do NOT add values that do not exist in the source
- Do NOT remove values that exist in the source
- Copy values VERBATIM from source when in doubt

### HANDLERS — PRESERVE ALL:
When migrating handlers/main.yml, preserve ALL handlers from the legacy role.
- If the legacy role has both `restart` and `reload` handlers for a service, include BOTH
- Do NOT drop handlers that exist in the source — even if they are not referenced in tasks
- Use FQCN for handler modules and `true`/`false` for booleans
- Always capitalize handler names to comply with ansible-lint's name[casing] rule
  (e.g., source `restart nginx` → `Restart nginx`). Use the same capitalized name
  in both the handler definition AND all `notify:` references in tasks.

Example — legacy role has both restart and reload handlers:
```yaml
---
- name: Restart nginx
  ansible.builtin.service:
    name: nginx
    state: restarted
  become: true

- name: Reload nginx
  ansible.builtin.service:
    name: nginx
    state: reloaded
  become: true
```

### PRIVILEGE ESCALATION — CONSOLIDATE:
When every task in a task file uses `become: true`, consolidate it:
- If ALL tasks in a file need `become: true`, add it at the play level or in the role's meta instead of repeating on each task
- Only use per-task `become: true` when some tasks need it and others don't

### META/MAIN.YML:
meta/main.yml is pre-created from the source role's metadata. Do NOT overwrite it if checklist shows "complete".

### TEMPLATE SECURITY MODERNIZATION:
When converting templates, apply generic security updates:
- TLS: Replace TLSv1/TLSv1.1 with TLSv1.2 TLSv1.3 (RFC 8996)
- Flag weak cipher configurations in notes

### REQUIREMENTS.YML:
**DO NOT include `ansible.builtin` in requirements.yml** — it is a pseudo-collection that ships with ansible-core and CANNOT be installed from Galaxy. Attempting to install it will always fail.
