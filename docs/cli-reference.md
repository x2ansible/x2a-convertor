---
layout: default
title: CLI Reference
nav_order: 5
---

# CLI Reference

{: .no_toc }

## Table of contents

{: .no_toc .text-delta }

<style>
.toc-h2-only ul {
    display: none;
}
</style>

- TOC
  {:toc .toc-h2-only}

---

Complete command-line interface reference for X2A Convertor.

## Main Command

```
Usage:  [OPTIONS] COMMAND [ARGS]...

  X2Ansible - Infrastructure Migration Tool

Options:
  --help  Show this message and exit.

Commands:
  analyze   Perform detailed analysis and create module migration plans
  init      Initialize project with interactive message
  migrate   Migrate project based on migration plan from analysis
  publish   Publish migrated Ansible role to GitHub using GitOps approach.
  validate  Validate migrated module against original configuration
```

## analyze

Perform detailed analysis and create module migration plans

### Usage

```bash
uv run app.py analyze [OPTIONS] USER_REQUIREMENTS
```

### Arguments

- `USER_REQUIREMENTS`

### Options

- `--source-dir` (default: .)
  Source directory to analyze

### Full Help

```
Usage: analyze [OPTIONS] USER_REQUIREMENTS

  Perform detailed analysis and create module migration plans

Options:
  --source-dir DIRECTORY  Source directory to analyze
  --help                  Show this message and exit.
```

## init

Initialize project with interactive message

### Usage

```bash
uv run app.py init [OPTIONS] USER_REQUIREMENTS
```

### Arguments

- `USER_REQUIREMENTS`

### Options

- `--source-dir` (default: .)
  Source directory to analyze

### Full Help

```
Usage: init [OPTIONS] USER_REQUIREMENTS

  Initialize project with interactive message

Options:
  --source-dir DIRECTORY  Source directory to analyze
  --help                  Show this message and exit.
```

## migrate

Migrate project based on migration plan from analysis

### Usage

```bash
uv run app.py migrate [OPTIONS] USER_REQUIREMENTS
```

### Arguments

- `USER_REQUIREMENTS`

### Options

- `--source-dir` (default: .)
  Source directory to migrate

- `--source-technology` (default: Chef)
  Source technology to migrate from [Chef, Puppet, Salt]

- `--module-migration-plan` (default: Sentinel.UNSET)
  Module migration plan file produced by the analyze command. Must be in the format: migration-plan-<module_name>.md. Path is relative to the --source-dir. Example: migration-plan-nginx.md

- `--high-level-migration-plan` (default: Sentinel.UNSET)
  High level migration plan file produced by the init command. Path is relative to the --source-dir. Example: migration-plan.md

### Full Help

```
Usage: migrate [OPTIONS] USER_REQUIREMENTS

  Migrate project based on migration plan from analysis

Options:
  --source-dir DIRECTORY          Source directory to migrate
  --source-technology TEXT        Source technology to migrate from [Chef,
                                  Puppet, Salt]
  --module-migration-plan FILE    Module migration plan file produced by the
                                  analyze command. Must be in the format:
                                  migration-plan-<module_name>.md. Path is
                                  relative to the --source-dir. Example:
                                  migration-plan-nginx.md
  --high-level-migration-plan FILE
                                  High level migration plan file produced by
                                  the init command. Path is relative to the
                                  --source-dir. Example: migration-plan.md
  --help                          Show this message and exit.
```

## publish

Publish migrated Ansible role to GitHub using GitOps approach.

Creates a complete Ansible project structure and optionally pushes it to a new GitHub repository.

### Usage

```bash
# Single role
uv run app.py publish <role-name> \
  --source-paths <path>/ansible/roles/{role} \
  --github-owner <user-or-org> \
  [--github-branch main] \
  [--skip-git] \
  [--collections-file <path>] \
  [--inventory-file <path>]

# Multiple roles
uv run app.py publish <role1> <role2> \
  --source-paths <path>/ansible/roles/{role1} \
  --source-paths <path>/ansible/roles/{role2} \
  --github-owner <user-or-org>
```

### Arguments

- `module_names`: One or more role names to publish (space-separated)

### Options

- `--source-paths`: Path(s) to the migrated Ansible role directory(ies). Can be specified multiple times. Number must match the number of module names.
- `--github-owner`: GitHub user or organization name where the repository will be created (required if not using `--skip-git`)
- `--github-branch`: Branch name to push to (default: `main`, ignored if `--skip-git`)
- `--base-path`: Base path for constructing deployment path. If not provided, derived from first source-path (parent of ansible/roles)
- `--skip-git`: Skip git steps (create repo, commit, push). Files will be created in `<base-path>/ansible/deployments/` only
- `--collections-file`: Path to YAML/JSON file containing collections list. Format: `[{"name": "collection.name", "version": "1.0.0"}]`
- `--inventory-file`: Path to YAML/JSON file containing inventory structure. Format: `{"all": {"children": {...}}}`

### Examples

```bash
# Single role with GitHub push
uv run app.py publish nginx_multisite \
  --source-paths ./ansible/roles/nginx_multisite \
  --github-owner myorg \
  --github-branch main

# Multiple roles
uv run app.py publish nginx apache \
  --source-paths ./ansible/roles/nginx \
  --source-paths ./ansible/roles/apache \
  --github-owner myorg

# Local only (skip git)
uv run app.py publish nginx_multisite \
  --source-paths ./ansible/roles/nginx_multisite \
  --collections-file ./collections.yml \
  --inventory-file ./inventory.yml \
  --skip-git
```

### File Formats

**Collections file** (`--collections-file`): YAML or JSON list of collections:

```yaml
- name: community.general
  version: ">=1.0.0"
- name: ansible.posix
```

**Inventory file** (`--inventory-file`): YAML or JSON inventory structure:

```yaml
all:
  children:
    web_servers:
      hosts:
        web1:
          ansible_host: 10.0.0.1
```

If not provided, default empty collections and localhost inventory are generated.

### Full Help

```
Usage: publish [OPTIONS] MODULE_NAME

  Publish migrated Ansible role to GitHub using GitOps approach.

  Creates a new GitOps repository and pushes the deployment to it. Takes role
  from <base-path>/ansible/roles/{module_name} and creates deployment at
  <base-path>/ansible/deployments/{module_name}.

Options:
  --source-path DIRECTORY  Path to the migrated Ansible role directory (e.g.,
                           ./ansible/roles/my_role)  [required]
  --base-path DIRECTORY    Base path for constructing deployment path. If not
                           provided, derived from source-path (parent of
                           ansible/roles).
  --github-owner TEXT      GitHub user or organization name where the
                           repository will be created  [required]
  --github-branch TEXT     GitHub branch to push to (default: main)
  --skip-git               Skip git steps (create repo, commit, push). Files
                           will be created in <base-
                           path>/ansible/deployments/{module_name}/ only.
  --help                   Show this message and exit.
```

## validate

Validate migrated module against original configuration

### Usage

```bash
uv run app.py validate [OPTIONS] MODULE_NAME
```

### Arguments

- `MODULE_NAME`

### Full Help

```
Usage: validate [OPTIONS] MODULE_NAME

  Validate migrated module against original configuration

Options:
  --help  Show this message and exit.
```
