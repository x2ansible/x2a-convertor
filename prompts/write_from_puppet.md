## Puppet-to-Ansible Migration Rules

These rules apply ONLY when migrating a Puppet module to Ansible.

### EPP TEMPLATE CONVERSION (.epp → .j2):
Puppet EPP templates use different syntax from Chef ERB. Convert as follows:{% raw %}
   - `<%= $variable %>` → `{{ variable }}` (remove $ prefix)
   - `<% if $condition { %>` → `{% if condition %}`
   - `<% unless $condition { %>` → `{% if not condition %}`
   - `<% $items.each |$item| { %>` → `{% for item in items %}`
   - `<% } %>` → `{% endfor %}` or `{% endif %}`
   - `<%- ` (trim left) and ` -%>` (trim right) → `{%- ` and ` -%}`{% endraw %}

Example EPP conversion:
Source EPP (backend.conf.epp):
```
<%- | String $backend_name, Integer $port, Array $servers | -%>
backend <%= $backend_name %>
  balance roundrobin
<% $servers.each |$server| { -%>
  server <%= $server %> <%= $server %>:<%= $port %>
<% } -%>
```

Correct Jinja2 output (backend.conf.j2):
```{% raw %}
backend {{ backend_name }}
  balance roundrobin
{% for server in servers %}
  server {{ server }} {{ server }}:{{ port }}
{% endfor %}{% endraw %}
```

### VARIABLE NAMING — CRITICAL:
The migration plan maps Puppet namespaced parameters to Ansible variable names
(e.g., `profile_haproxy::stats_user` → `haproxy_stats_user`).

- Strip the Puppet namespace and use the Ansible role variable name everywhere
- In templates, ALWAYS use the Ansible variable name from the migration plan
- In defaults/main.yml, use the Ansible variable name

WRONG — bare Puppet variable name in template:{% raw %}
```
stats auth {{ stats_user }}:{{ stats_password }}
```{% endraw %}

CORRECT — Ansible role variable name:{% raw %}
```
stats auth {{ haproxy_stats_user }}:{{ haproxy_stats_password }}
```{% endraw %}

### DEFAULTS/MAIN.YML:
- Values MUST be plain values, NOT Jinja2 references to other variables
- WRONG: `haproxy_stats_user: "{% raw %}{{ stats_user | default('admin') }}{% endraw %}"`
- CORRECT: `haproxy_stats_user: admin`

### PUPPET MANIFESTS (.pp → .yml tasks):
Convert Puppet resources to Ansible modules:
- `package` → `ansible.builtin.package`
- `service` → `ansible.builtin.service` or `ansible.builtin.systemd`
- `file` with `content => template(...)` → `ansible.builtin.template`
- `file` with `source => puppet:///...` → `ansible.builtin.copy`
- `file` with `ensure => directory` → `ansible.builtin.file` with `state: directory`
- `exec` → `ansible.builtin.command` with `changed_when`/`creates`/`unless`
- `cron` → `ansible.builtin.cron`
- `each` loops → `loop:` with `dict2items` for hashes
- `if`/`unless`/`case` → `when:` conditions
- Firewall: prefer `community.general.ufw` module over raw `ansible.builtin.command: ufw`

### PUPPET FACTS → ANSIBLE FACTS:
- `$facts['os']['family']` → `ansible_os_family`
- `$facts['os']['name']` → `ansible_distribution`
- `$facts['os']['release']['major']` → `ansible_distribution_major_version`
- `$facts['networking']['ip']` → `ansible_default_ipv4.address`
- `$facts['networking']['fqdn']` → `ansible_fqdn`

### HIERA DATA → ANSIBLE VARIABLES:
- Hiera `common.yaml` → `defaults/main.yml`
- Per-OS data (`os/Debian.yaml`) → `vars/Debian.yml` loaded via `include_vars` based on `ansible_os_family`
- Per-environment/datacenter/cluster data → `vars/` files loaded via `include_vars`

### DEEP MERGE for Hiera variables:
When the migration plan marks a variable as "deep merged" (e.g., `backends: (type: hash, deep merged)`),
the variable is defined at multiple Hiera levels and values must be merged recursively, not replaced.

Pattern:
- Define the base value in `defaults/main.yml` (e.g., `haproxy_backends`)
- In each vars/ override file, use the `_override` suffix (e.g., `haproxy_backends_override`)
- In `load_vars.yml`, AFTER each `include_vars`, add a `set_fact` that merges the override into the base

Complete `load_vars.yml` example:
```yaml{% raw %}
---
- name: Load OS-specific variables
  ansible.builtin.include_vars: "{{ ansible_os_family }}.yml"
  failed_when: false

- name: Load datacenter-specific variables
  ansible.builtin.include_vars: "{{ haproxy_datacenter }}.yml"
  when: haproxy_datacenter is defined
  failed_when: false

- name: Deep merge datacenter backend overrides
  ansible.builtin.set_fact:
    haproxy_backends: "{{ haproxy_backends | default({}) | combine(haproxy_backends_override, recursive=True) }}"
  when: haproxy_backends_override is defined

- name: Load cluster-specific variables
  ansible.builtin.include_vars: "{{ haproxy_cluster }}.yml"
  when: haproxy_cluster is defined
  failed_when: false

- name: Deep merge cluster backend overrides
  ansible.builtin.set_fact:
    haproxy_backends: "{{ haproxy_backends | default({}) | combine(haproxy_backends_override, recursive=True) }}"
  when: haproxy_backends_override is defined{% endraw %}
```

The `_override` variable is loaded by `include_vars` from each level's vars file, then merged into the
base variable. Each level's merge builds on the previous result, so cluster overrides datacenter
overrides common — matching Puppet's Hiera precedence.
