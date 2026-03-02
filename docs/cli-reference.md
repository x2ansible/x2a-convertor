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
  analyze          Perform detailed analysis and create module migration...
  init             Initialize project with interactive message
  migrate          Migrate project based on migration plan from analysis
  publish-aap      Sync a git repository to Ansible Automation Platform.
  publish-project  Create or append to an Ansible project for a migrated...
  report           Report execution artifacts to the x2a API
  validate         Validate migrated module against original configuration
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

## publish-aap

Sync a git repository to Ansible Automation Platform.

Creates or updates an AAP Project pointing to the given repository URL
and branch, then triggers a project sync.

Requires AAP environment variables to be configured
(AAP_CONTROLLER_URL, AAP_ORG_NAME, and authentication credentials).


### Usage

```bash
uv run app.py publish-aap [OPTIONS]
```

### Options

- `--target-repo` **[required]** (default: Sentinel.UNSET)
  Git repository URL for the AAP project (e.g., https://github.com/org/repo.git).

- `--target-branch` **[required]** (default: Sentinel.UNSET)
  Git branch for the AAP project.

- `--project-id` **[required]** (default: Sentinel.UNSET)
  Migration project ID, used for AAP project naming and subdirectory reference.

### Full Help

```
Usage: publish-aap [OPTIONS]

  Sync a git repository to Ansible Automation Platform.

  Creates or updates an AAP Project pointing to the given repository URL and
  branch, then triggers a project sync.

  Requires AAP environment variables to be configured (AAP_CONTROLLER_URL,
  AAP_ORG_NAME, and authentication credentials).

Options:
  --target-repo TEXT    Git repository URL for the AAP project (e.g.,
                        https://github.com/org/repo.git).  [required]
  --target-branch TEXT  Git branch for the AAP project.  [required]
  --project-id TEXT     Migration project ID, used for AAP project naming and
                        subdirectory reference.  [required]
  --help                Show this message and exit.
```

## publish-project

Create or append to an Ansible project for a migrated module.

PROJECT_ID is the migration project ID.
MODULE_NAME is the module/role to add.

On the first module, creates the full skeleton (ansible.cfg, collections,
inventory). On subsequent modules, appends the role and playbook.

Role names are sanitized to comply with Ansible standards: hyphens are
replaced with underscores (e.g., fastapi-tutorial becomes fastapi_tutorial).


### Usage

```bash
uv run app.py publish-project [OPTIONS] PROJECT_ID MODULE_NAME
```

### Arguments

- `PROJECT_ID`
- `MODULE_NAME`

### Options

- `--collections-file` (default: Sentinel.UNSET)
  Path to YAML/JSON file containing collections list. Format: [{"name": "collection.name", "version": "1.0.0"}]

- `--inventory-file` (default: Sentinel.UNSET)
  Path to YAML/JSON file containing inventory structure. Format: {"all": {"children": {...}}}

### Full Help

```
Usage: publish-project [OPTIONS] PROJECT_ID MODULE_NAME

  Create or append to an Ansible project for a migrated module.

  PROJECT_ID is the migration project ID. MODULE_NAME is the module/role to
  add.

  On the first module, creates the full skeleton (ansible.cfg, collections,
  inventory). On subsequent modules, appends the role and playbook.

  Role names are sanitized to comply with Ansible standards: hyphens are
  replaced with underscores (e.g., fastapi-tutorial becomes fastapi_tutorial).

Options:
  --collections-file FILE  Path to YAML/JSON file containing collections list.
                           Format: [{"name": "collection.name", "version":
                           "1.0.0"}]
  --inventory-file FILE    Path to YAML/JSON file containing inventory
                           structure. Format: {"all": {"children": {...}}}
  --help                   Show this message and exit.
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

- `--commit-id`
  Git commit SHA from the job's push to target repo

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
  --commit-id TEXT      Git commit SHA from the job's push to target repo
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
