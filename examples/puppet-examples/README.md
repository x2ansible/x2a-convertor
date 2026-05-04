# Puppet Example Modules

Synthetic Puppet modules designed to exercise the full range of Puppet-to-Ansible migration edge cases. Each module targets specific patterns that the Puppet input agent must handle correctly.

## Modules

### `profile_haproxy` — Loops, Maps, and 21-Level Hiera

An HAProxy load balancer profile that configures multiple backends from a data-driven hash, with configuration spread across a 21-level Hiera hierarchy.

**Edge cases tested:**

| Pattern | Where | Details |
|---------|-------|---------|
| 21-level Hiera hierarchy | `hiera.yaml` | All 21 levels defined (node, role, cluster, app tier, app, team, BU, lifecycle, env, network zone, DC, region, country, arch, OS release, OS family+major, OS family, kernel, container, virtual, common). Data files only exist for 6 levels — tests sparse resolution. |
| Hiera deep merge | `data/common.yaml`, `data/datacenter/`, `data/cluster/` | `backends` hash is defined at common level and overridden/extended at datacenter and cluster levels with `merge: deep` |
| Hiera eyaml (encrypted) | `data/common.yaml` | `stats_password` uses `ENC[PKCS7,...]` — maps to Ansible Vault or secret lookup |
| Data-driven loops | `manifests/config.pp` | `$backends.each` iterates a Hiera hash to create N backend config files |
| ERB template | `templates/haproxy.cfg.erb` | Loops, conditionals (`if @ssl_enabled`), variable interpolation |
| EPP template | `templates/backend.conf.epp` | Typed parameters, `Optional` types, iteration over arrays |
| Class composition with ordering | `manifests/init.pp` | `contain` + `->` and `~>` chains between 4 classes |
| OS-conditional logic | `manifests/firewall.pp` | `case $firewall_provider` — firewalld (RHEL) vs ufw (Debian) |
| Hiera-driven OS differences | `data/os/RedHat.yaml`, `data/os/Debian.yaml` | Different packages, SELinux setting, firewall provider per OS |
| Custom fact | `lib/facter/haproxy_version.rb` | Extracts installed HAProxy version |
| SELinux exec guard | `manifests/install.pp` | `exec` with `unless` for `setsebool` |
| Sensitive type | `manifests/init.pp` | `Sensitive[String]` parameter for passwords |

---

### `profile_redis_cluster` — External Dependencies, PuppetDB, Exported Resources

A Redis cluster profile where replicas discover the primary node via PuppetDB queries, and sentinel nodes coordinate via exported resources.

**Edge cases tested:**

| Pattern | Where | Details |
|---------|-------|---------|
| Puppetfile (Forge deps) | `Puppetfile` | `mod 'puppet-redis'`, `mod 'puppetlabs-stdlib'`, etc. |
| Puppetfile (Git deps) | `Puppetfile` | `mod 'example-monitoring', :git => '...', :tag => '...'` and `:branch => '...'` |
| `puppetdb_query()` | `manifests/replica.pp`, `manifests/sentinel.pp` | PQL queries to discover primary node and count sentinel nodes for quorum |
| Exported resources (`@@`) | `manifests/primary.pp`, `manifests/sentinel.pp` | Primary exports its identity; sentinel exports host entries |
| Resource collectors (`<<\| \|>>`) | `manifests/replica.pp`, `manifests/sentinel.pp` | Replicas collect primary identity; sentinels collect all sentinel hosts |
| Custom type | `lib/puppet/type/redis_health.rb` | `redis_health` type with typed params, validation, `sensitive` |
| Custom provider | `lib/puppet/provider/redis_health/cli.rb` | Provider using `redis-cli` commands |
| Custom facts (2) | `lib/facter/redis_role.rb`, `lib/facter/redis_cluster_size.rb` | Determine node role and cluster size at runtime |
| External module usage | `manifests/install.pp` | `class { 'redis': ... }` from `puppet-redis` |
| `ruby_block` workaround | `manifests/install.pp` | Marked as HACK — cleans up config entries from external module |
| `case` on custom fact | `manifests/init.pp` | Routes to `primary` or `replica` class based on `$facts['redis_role']` |
| `fail()` | `manifests/init.pp`, `manifests/replica.pp` | Fails catalog if role unknown or primary not found |
| Heredoc strings | `manifests/primary.pp`, `manifests/replica.pp` | `@("EOF")` heredocs for inline config |

---

### `profile_app_stack` — Inter-Dependencies, Service Chain, Systemd

A full application stack (Python + PostgreSQL + systemd) with a strict 5-class dependency chain, database provisioning with idempotent guards, and virtual resources.

**Edge cases tested:**

| Pattern | Where | Details |
|---------|-------|---------|
| Strict dependency chain | `manifests/init.pp` | `python -> database -> app ~> service -> monitoring` (5 classes) |
| Database provisioning | `manifests/database.pp` | `exec` with `unless` guards for user, database, and privilege creation |
| Conditional local vs remote DB | `manifests/database.pp` | PostgreSQL only installed if `$db_host == 'localhost'` |
| Virtual resources (`@`) | `manifests/monitoring.pp` | `@package`, `@service`, `@cron` declared but not applied |
| `realize` pattern | `manifests/monitoring.pp` | Resources only realized when `$facts['environment'] == 'production'` |
| EPP systemd unit | `templates/app.service.epp` | Typed params, expression evaluation (`$graceful_timeout + 5`), security hardening directives |
| ERB with conditional blocks | `templates/app.env.erb` | Different CORS/debug settings per environment |
| Custom Puppet function | `lib/puppet/functions/app_db_url.rb` | `profile_app_stack::app_db_url()` builds PostgreSQL connection URL |
| `vcsrepo` resource | `manifests/app.pp` | Git clone with revision tracking |
| `refreshonly` exec | `manifests/app.pp` | DB migrations only run when repo changes (via `subscribe`) |
| Cron jobs | `manifests/database.pp`, `manifests/monitoring.pp` | Backup schedule and health check interval |
| Hiera eyaml (2-level) | `data/common.yaml`, `data/environment/production.yaml` | Simpler hierarchy to contrast with profile_haproxy's 21-level |
| Package array | `manifests/python.pp` | Installing multiple packages from a variable list |
| `creates` guard | `manifests/python.pp` | Virtualenv only created if activate script doesn't exist |

---

## Coverage Summary

| Category | profile_haproxy | profile_redis_cluster | profile_app_stack |
|----------|:-:|:-:|:-:|
| Hiera hierarchy | 21-level | - | 2-level |
| Hiera deep merge | x | - | - |
| Hiera eyaml secrets | x | - | x |
| Loops / iteration | x | - | x |
| ERB templates | x | x | x |
| EPP templates | x | - | x |
| Class ordering (`->`, `~>`) | x | x | x |
| OS-conditional logic | x | - | - |
| Puppetfile (Forge + Git) | - | x | - |
| PuppetDB queries | - | x | - |
| Exported resources (`@@`) | - | x | - |
| Collectors (`<<\| \|>>`) | - | x | - |
| Custom types/providers | - | x | - |
| Custom facts | x | x | - |
| Custom functions | - | - | x |
| Virtual resources / realize | - | - | x |
| Exec with guards | x | - | x |
| External module usage | - | x | - |
| Systemd services | - | - | x |
| Database provisioning | - | - | x |
| Cron jobs | - | - | x |
| Sensitive types | x | - | - |
