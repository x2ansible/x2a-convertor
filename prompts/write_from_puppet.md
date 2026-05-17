
## Puppet-Specific Migration Rules

These rules apply when migrating from Puppet modules to Ansible roles.

### READING SOURCE DATA FILES — CRITICAL:

When creating defaults/main.yml or any vars/ file, you MUST:
1. Use read_file to read the ORIGINAL Hiera YAML data file (e.g., data/common.yaml,
   data/os/Debian.yaml, data/environment/production.yaml)
2. Copy values EXACTLY from the source — do not round numbers, change IP addresses,
   invent values, or "improve" anything
3. Every variable in the migration plan's mapping table MUST appear in the correct
   target file with its correct value
4. If the source has `profile_haproxy::global_maxconn: 16384`, write
   `haproxy_global_maxconn: 16384` — NOT 8000 or 10000 or any other invented number

WRONG — inventing values instead of reading the source:
```yaml
haproxy_global_maxconn: 8000  # Source actually says 16384
haproxy_log_server: 10.10.1.15  # Source actually says 10.100.1.50
```

CORRECT — reading the source file and copying exact values:
```yaml
haproxy_global_maxconn: 16384
haproxy_log_server: 10.100.1.50
```

### TEMPLATE FIDELITY — CRITICAL:

When converting ERB/EPP templates to Jinja2:
1. Use read_file to read the ORIGINAL template file
2. Convert syntax (ERB→Jinja2) but preserve the STRUCTURE faithfully
3. NEVER add features, sections, or logic that don't exist in the original template
4. NEVER hardcode values that the original template gets from variables
5. NEVER duplicate content between templates — if backends are rendered as separate
   files via a loop in the manifest, the main config template must NOT also render
   them inline
6. Every `<%= @variable %>` in ERB or `<%= $variable %>` in EPP MUST become a
   `{% raw %}{{ variable }}{% endraw %}` reference — not a hardcoded value

WRONG — hardcoding values the template reads from variables:
```
timeout connect 5000
timeout client  50000
```
When original ERB has:
```
timeout connect <%= @connect_timeout %>
timeout client  <%= @client_timeout %>
```

CORRECT:
{% raw %}
```
timeout connect {{ haproxy_connect_timeout }}
timeout client  {{ haproxy_client_timeout }}
```
{% endraw %}

### PATH SEMANTICS:

When converting Puppet file resources for certificates/keys:
- If Puppet deploys a cert FILE to `/etc/ssl/certs/service.pem`, the Ansible variable
  should point to the FILE path (e.g., `haproxy_ssl_cert_path: /etc/ssl/certs/haproxy.pem`),
  NOT a directory. Check the original manifest to see if the path is a file or directory.

### VARIABLE LOADING FROM HIERA HIERARCHY — CRITICAL:

Puppet modules use Hiera for hierarchical data lookup. Ansible only auto-loads
`defaults/main.yml` and `vars/main.yml` — all other vars files (OS-specific,
environment-specific, etc.) MUST be loaded explicitly with `include_vars`.

You MUST create `tasks/load_variables.yml` and include it in `tasks/main.yml`
BEFORE all other task includes (but after `validate_credentials.yml` if present).

The `load_variables.yml` MUST load ALL vars files that correspond to Hiera hierarchy
levels — not just OS-specific vars. This means separate `include_vars` tasks for each
level that has data files.

Pattern for `tasks/load_variables.yml`:
{% raw %}
```yaml
---
# 1. OS-specific variables (mandatory)
- name: Load OS-specific variables
  ansible.builtin.include_vars: "{{ ansible_os_family }}.yml"

# 2. Environment variables (conditional)
- name: Load environment-specific variables
  ansible.builtin.include_vars: "{{ haproxy_environment }}.yml"
  when: haproxy_environment is defined
  failed_when: false

# 3. Datacenter variables (conditional)
- name: Load datacenter-specific variables
  ansible.builtin.include_vars: "{{ haproxy_datacenter }}.yml"
  when: haproxy_datacenter is defined
  failed_when: false

# 4. Cluster variables (conditional)
- name: Load cluster-specific variables
  ansible.builtin.include_vars: "{{ haproxy_cluster }}.yml"
  when: haproxy_cluster is defined
  failed_when: false

# 5. Node-specific variables (conditional)
- name: Load node-specific variables
  ansible.builtin.include_vars: "{{ inventory_hostname }}.yml"
  failed_when: false
```
{% endraw %}

After loading override files, apply deep merge for hash variables (see Deep Merge section below).

Do NOT use `set_fact` to re-default variables that already exist in `defaults/main.yml` —
that is redundant and masks override values loaded by `include_vars`.

Pattern for `tasks/main.yml` ordering:
```yaml
---
- name: Validate credential variables
  ansible.builtin.include_tasks: validate_credentials.yml
- name: Load platform and environment variables
  ansible.builtin.include_tasks: load_variables.yml
- name: Gather facts
  ansible.builtin.include_tasks: gather_facts.yml
- name: Install packages
  ansible.builtin.include_tasks: install.yml
# ... remaining tasks
```

If `gather_facts.yml` exists (converted from a custom Puppet fact), it MUST be
included in `main.yml` — do not create it and then leave it orphaned.

### VARIABLE NAMING — CRITICAL:

ALL role variables MUST use a consistent role-name prefix to avoid collisions with
Ansible reserved words and other roles.

CORRECT — prefixed names:
```yaml
haproxy_package_name: haproxy
haproxy_ssl_enabled: false
haproxy_retries: 3
haproxy_backends: {}
haproxy_stats_port: 9000
```

WRONG — bare names that collide with Ansible or other roles:
```yaml
retries: 3          # Reserved Ansible keyword
port: 9000          # Too generic
backends: {}        # Too generic
ssl_enabled: false  # Could collide with another role
```

The "Role Variable Names" section in the task prompt lists the authoritative variable
names for this role. Use those names EXACTLY in defaults/main.yml, vars files,
templates, and tasks. If that section is present, it takes precedence over any other
naming convention.

### DEEP MERGE FOR HASH VARIABLES:

When the migration plan indicates a variable uses `merge: deep` in Hiera (common for
backend/server hashes that are overridden at multiple hierarchy levels):
{% raw %}
- Define the base hash in `defaults/main.yml`
- In override vars files (e.g., `vars/production.yml`), define overrides with an
  `_override` suffix (e.g., `haproxy_backends_override`)
- In `tasks/load_variables.yml`, add a merge task AFTER EACH `include_vars` that
  loads a level which may override the hash:

```yaml
- name: Load environment-specific variables
  ansible.builtin.include_vars: "{{ haproxy_environment }}.yml"
  when: haproxy_environment is defined
  failed_when: false

- name: Merge backend overrides from environment
  ansible.builtin.set_fact:
    haproxy_backends: >-
      {{ haproxy_backends | default({}) |
         combine(haproxy_backends_override | default({}), recursive=True) }}
  when: haproxy_backends_override is defined
```

If multiple levels (OS, environment, datacenter) can override the same hash,
include a merge task after EACH `include_vars`. Each merge accumulates into
the same target variable — this preserves overrides from all levels.
{% endraw %}

### FIREWALL RULES:

Use proper Ansible modules for firewall management — NOT raw commands:

For firewalld (RedHat):
{% raw %}
```yaml
- name: Open HTTP port in firewalld
  ansible.posix.firewalld:
    port: "{{ item }}/tcp"
    permanent: true
    immediate: true
    state: enabled
    zone: "{{ haproxy_firewall_zone }}"
  loop:
    - "80"
    - "443"
```
{% endraw %}

For ufw (Debian):
{% raw %}
```yaml
- name: Allow HTTP traffic
  community.general.ufw:
    rule: allow
    port: "{{ item }}"
    proto: tcp
  loop:
    - "80"
    - "443"
```
{% endraw %}

These modules are idempotent — no `unless` or `creates` checks needed.

### HANDLER WIRING AND CONFIG VALIDATION:

Puppet's `~>` (notification) maps to `notify:` on the task.

When Puppet validates config before service restart (e.g., `exec { 'haproxy_config_check': ... }`),
use the `validate` parameter on `ansible.builtin.template`:
{% raw %}
```yaml
- name: Deploy HAProxy configuration
  ansible.builtin.template:
    src: haproxy.cfg.j2
    dest: "{{ haproxy_config_file }}"
    owner: root
    group: "{{ haproxy_group }}"
    mode: "0640"
    validate: haproxy -c -f %s
  notify: Restart HAProxy
```
{% endraw %}

Do NOT create a separate validation task — the `validate` parameter runs the check
BEFORE writing the file, which is safer than Puppet's approach.

IMPORTANT: Only use `validate` when the service has a config validation command that
takes a file path with `%s`. Examples:
- HAProxy: `validate: haproxy -c -f %s`
- Nginx: `validate: nginx -t -c %s`
- Apache: `validate: apachectl -t -f %s`
- Sudo: `validate: visudo -cf %s`

Do NOT invent validation commands. If the service doesn't have a standard config
validation tool (e.g., Redis, simple INI files), omit the `validate` parameter entirely.

Additionally, do NOT use `validate` on template tasks that produce PARTIAL config
fragments (e.g., backend definitions in conf.d/). The `validate` parameter runs
against the single file being written — a fragment will fail validation because
it is not a complete config. Only use `validate` on the MAIN config file that
contains or includes all fragments.

### MULTILINE CONTENT:

When using `ansible.builtin.copy` with `content:` for config files (logrotate, cron, etc.),
ALWAYS use YAML block scalar (`|`) to preserve formatting:

```yaml
- name: Configure log rotation
  ansible.builtin.copy:
    dest: /etc/logrotate.d/haproxy
    content: |
      /var/log/haproxy/*.log {
          daily
          rotate 14
          missingok
          notifempty
          compress
          delaycompress
          sharedscripts
          postrotate
              /bin/kill -HUP $(cat /var/run/haproxy.pid 2>/dev/null) 2>/dev/null || true
          endscript
      }
    owner: root
    group: root
    mode: "0644"
```

NEVER put multiline content on a single line — it produces unreadable, broken config files.

### SENSITIVE VALUES:

Variables marked as `Sensitive[String]` in Puppet or encrypted with hiera-eyaml MUST:
- Use `no_log: true` on any task that references the variable
- Be stored in `vars/vault.yml` with placeholder values
- Document that `vars/vault.yml` should be encrypted with `ansible-vault encrypt`
{% raw %}
```yaml
- name: Deploy stats page configuration
  ansible.builtin.template:
    src: stats.conf.j2
    dest: /etc/haproxy/conf.d/stats.cfg
  no_log: true  # Contains haproxy_stats_password
  notify: Restart HAProxy
```
{% endraw %}

CRITICAL: When the task prompt includes an "AAP Credential Variables" section, you MUST use
the EXACT variable names listed there (e.g., `redis_password`) for vault.yml entries,
templates, and tasks — NOT any renamed variants from the migration plan's mapping table.
The AAP credential types and validate_credentials.yml already use these names. Using
different names in vault.yml or templates will cause runtime failures.

### PUPPET TEMPLATE CONVERSION (EPP/ERB → Jinja2):

In addition to the standard ERB conversion rules:
- EPP parameter declarations (`<%- | Type $param | -%>`) have no Jinja2 equivalent — remove them
  and pass variables via task-level `vars:` instead
- Puppet's `@variable` references become bare `{% raw %}{{ variable }}{% endraw %}` (remove `@`)
- Puppet's `$variable` references in EPP become `{% raw %}{{ variable }}{% endraw %}` (remove `$`)
- Ruby's `.nil?` check → Jinja2's `is defined`
- Ruby's `.empty?` check → Jinja2's `| length == 0`
- Ruby's `dig('key')` → Jinja2's `['key'] | default(omit)`

### PUPPET TEMPLATE ANTI-PATTERNS — CRITICAL:

{% raw %}
NEVER use Go template syntax (`{{ range }}`, `{{ end }}`, `{{ .variable }}`). Ansible uses
Jinja2 — the correct loop syntax is `{% for item in collection %} ... {% endfor %}`.

When converting Puppet hash iteration:
- Ruby `@hash.each do |key, value|` → Jinja2 `{% for key, value in hash.items() %}`
- Ruby `@hash['key']` or EPP `$hash['key']` → Jinja2 `{{ hash.key }}` or `{{ hash['key'] }}`
- Ruby `item[:attribute]` or `item['attribute']` → Jinja2 `{{ item.attribute }}`

WRONG — Go template syntax:
```
{{ range $backend := .backends }}
{{ end }}
```

CORRECT — Jinja2 syntax:
```
{% for name, backend in haproxy_backends.items() %}
{% endfor %}
```

When converting templates with hash/dict access, preserve the ORIGINAL key names from
the Puppet source. If the source uses `server['address']`, the Jinja2 MUST use
`{{ server.address }}` — NOT `{{ server.host }}` or any other invented key name.
{% endraw %}

### STATIC FILES FROM PUPPET MODULE — CRITICAL:

Puppet modules often include static files in the `files/` directory (error pages, scripts,
certificates). These MUST be copied byte-for-byte using the `copy_file` tool:

```
copy_file(source="/path/to/puppet/module/files/503.http",
          destination="/path/to/ansible/role/files/503.http")
```

NEVER use `write_file` to recreate static files. The source file IS the content —
there is nothing to convert. Use `copy_file` to preserve the exact bytes.

### PUPPETDB QUERIES → ANSIBLE INVENTORY:

Puppet modules may use `puppetdb_query()` to dynamically discover nodes. In Ansible, this
is handled by inventory groups. When the migration plan mentions a PuppetDB query:

1. Add a comment in `tasks/main.yml` noting that the original Puppet module used PuppetDB
   for node discovery, and that Ansible inventory groups should be used instead
2. If the query discovers nodes for clustering (e.g., Redis cluster members), add a variable
   like `<service>_cluster_members` to `defaults/main.yml` with default `[]` and a comment
   explaining it should be populated from inventory groups or defined explicitly
3. Do NOT try to replicate PuppetDB queries — Ansible's inventory system is the equivalent

### REQUIREMENTS.YML FROM PUPPET DEPENDENCIES:

If the migration plan includes a "Dependency Mapping" table listing Ansible collections:
1. Create `requirements.yml` in the role directory listing those collections
2. Only include collections that are actually needed (not ansible.builtin modules)
3. If no external collections are needed, do NOT create an empty requirements.yml

### META/MAIN.YML — DO NOT OVERWRITE:

meta/main.yml is pre-generated from Puppet `metadata.json` by the pipeline before
the write agent runs. It is already marked "complete" in the checklist.
Do NOT recreate, overwrite, or modify it.
