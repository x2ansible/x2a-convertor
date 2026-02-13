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

* TOC
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
  publish   Publish migrated Ansible roles to Ansible Automation Platform...
  report    Report execution artifacts to the x2a API
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

- `--refresh`
  Skip migration plan generation if migration-plan.md exists, only regenerate metadata

### Full Help

```
Usage: init [OPTIONS] USER_REQUIREMENTS

  Initialize project with interactive message

Options:
  --source-dir DIRECTORY  Source directory to analyze
  --refresh               Skip migration plan generation if migration-plan.md
                          exists, only regenerate metadata
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

Publish migrated Ansible roles to Ansible Automation Platform
wrap the roles in an Ansible Project format,
push the project to git, and sync to AAP.

Creates a new GitOps repository and pushes the deployment to it.
For single role: creates deployment at
`<base-path>/ansible/deployments/{module_name}`.
For multiple roles: creates a consolidated project at
`<base-path>/ansible/deployments/ansible-project`.


### Usage

```bash
uv run app.py publish [OPTIONS] MODULE_NAMES
```

### Arguments

- `MODULE_NAMES`

### Options

- `--source-paths` **[required]** (default: Sentinel.UNSET)
  Path(s) to the migrated Ansible role directory(ies). Can be specified multiple times. Example: --source-paths ./ansible/roles/role1 --source-paths ./ansible/roles/role2

- `--base-path` (default: Sentinel.UNSET)
  Base path for constructing deployment path. If not provided, derived from first source-paths (parent of ansible/roles).

- `--github-owner` (default: Sentinel.UNSET)
  GitHub user or organization name where the repository will be created (required if not using --skip-git)

- `--github-branch` (default: main)
  GitHub branch to push to (default: main, ignored if --skip-git)

- `--skip-git`
  Skip git steps (create repo, commit, push). Files will be created in <base-path>/ansible/deployments/ only.

- `--collections-file` (default: Sentinel.UNSET)
  Path to YAML/JSON file containing collections list. Format: [{"name": "collection.name", "version": "1.0.0"}]

- `--inventory-file` (default: Sentinel.UNSET)
  Path to YAML/JSON file containing inventory structure. Format: {"all": {"children": {...}}}

### Full Help

```
Usage: publish [OPTIONS] MODULE_NAMES...

  Publish migrated Ansible roles to Ansible Automation Platform wrap the roles
  in an Ansible Project format, push the project to git, and sync to AAP.

  Creates a new GitOps repository and pushes the deployment to it. For single
  role: creates deployment at `<base-path>/ansible/deployments/{module_name}`.
  For multiple roles: creates a consolidated project at `<base-
  path>/ansible/deployments/ansible-project`.

Options:
  --source-paths DIRECTORY  Path(s) to the migrated Ansible role
                            directory(ies). Can be specified multiple times.
                            Example: --source-paths ./ansible/roles/role1
                            --source-paths ./ansible/roles/role2  [required]
  --base-path DIRECTORY     Base path for constructing deployment path. If not
                            provided, derived from first source-paths (parent
                            of ansible/roles).
  --github-owner TEXT       GitHub user or organization name where the
                            repository will be created (required if not using
                            --skip-git)
  --github-branch TEXT      GitHub branch to push to (default: main, ignored
                            if --skip-git)
  --skip-git                Skip git steps (create repo, commit, push). Files
                            will be created in <base-
                            path>/ansible/deployments/ only.
  --collections-file FILE   Path to YAML/JSON file containing collections
                            list. Format: [{"name": "collection.name",
                            "version": "1.0.0"}]
  --inventory-file FILE     Path to YAML/JSON file containing inventory
                            structure. Format: {"all": {"children": {...}}}
  --help                    Show this message and exit.
```

## report

Report execution artifacts to the x2a API

### Usage

```bash
uv run app.py report [OPTIONS]
```

### Options

- `--url` **[required]** (default: Sentinel.UNSET)
  Full URL to report artifacts to

- `--job-id` **[required]** (default: Sentinel.UNSET)
  UUID of the completed job

- `--error-message`
  Error message to report (sets status to error)

- `--artifacts` (default: Sentinel.UNSET)
  Artifact as type:url (e.g., migration_plan:https://storage.example/migration-plan.md)

### Full Help

```
Usage: report [OPTIONS]

  Report execution artifacts to the x2a API

Options:
  --url TEXT            Full URL to report artifacts to  [required]
  --job-id TEXT         UUID of the completed job  [required]
  --error-message TEXT  Error message to report (sets status to error)
  --artifacts TEXT      Artifact as type:url (e.g.,
                        migration_plan:https://storage.example/migration-
                        plan.md)
  --help                Show this message and exit.
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
