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

Creates a new GitOps repository and pushes the deployment to it.
Takes role from <base-path>/ansible/roles/{module_name} and creates
deployment at <base-path>/ansible/deployments/{module_name}.


### Usage

```bash
uv run app.py publish [OPTIONS] MODULE_NAME
```

### Arguments

- `MODULE_NAME`

### Options

- `--source-path` **[required]** (default: Sentinel.UNSET)
  Path to the migrated Ansible role directory (e.g., ./ansible/roles/my_role)

- `--base-path` (default: Sentinel.UNSET)
  Base path for constructing deployment path. If not provided, derived from source-path (parent of ansible/roles).

- `--github-owner` **[required]** (default: Sentinel.UNSET)
  GitHub user or organization name where the repository will be created

- `--github-branch` (default: main)
  GitHub branch to push to (default: main)

- `--skip-git`
  Skip git steps (create repo, commit, push). Files will be created in <base-path>/ansible/deployments/{module_name}/ only.

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
