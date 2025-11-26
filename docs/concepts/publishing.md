---
layout: default
title: Publishing
parent: Concepts
nav_order: 6
---

# Publisher

The publisher automates GitOps deployment of migrated Ansible roles to GitHub by creating new repositories and pushing deployment configurations using template-based generation and LangGraph orchestration.

## Purpose

Transforms local Ansible roles into production-ready GitOps configurations by:

- Taking roles from `<path>/ansible/roles/{role}`
- Creating deployment structure at `<path>/ansible/deployments/{role}`
- Generating playbooks, job templates, and GitHub Actions workflows from templates
- Creating a new GitOps repository and pushing the deployment to it

## Workflow

Uses a LangGraph workflow with deterministic tools (no LLM generation):

1. Create directory structure (`roles/`, `playbooks/`, `aap-config/`, `.github/workflows/`)
2. Copy role directory from source to deployment
3. Generate playbook (`{role}_deploy.yml`)
4. Generate job template (`{role}_deploy.yaml`)
5. Generate GitHub Actions workflow (`deploy.yml`)
6. Verify all files exist
7. Create GitHub repository (named `{role}-gitops`) if it doesn't exist
8. Commit changes to branch
9. Push branch to remote
10. Display summary with files created, credentials needed, and execution location

## Deployment Structure

The publisher creates a deployment directory with the following structure:

```
<path>/ansible/deployments/{role}/
├── roles/
│   └── {role}/          # Copied role source code
│       └── tasks/
├── playbooks/
│   └── {role}_deploy.yml      # Entry point playbook
├── aap-config/job-templates/
│   └── {role}_deploy.yaml     # AAP job template (Config-as-Code)
└── .github/workflows/
    └── deploy.yml              # GitHub Actions workflow
```

This entire deployment directory becomes the root of the GitOps repository when pushed.

## Idempotency Rules

The publisher follows these idempotency rules:

1. **Repository doesn't exist**: Creates new repository `{role}-gitops` and pushes to branch
2. **Repository exists, branch doesn't exist**: Creates new branch and pushes to it
3. **Repository exists, branch exists**: Fails with clear error message indicating branch already exists

## Key Features

- **Template-based**: Jinja2 templates ensure consistent output
- **Deterministic**: No LLM calls during generation for reproducible results
- **GitOps-ready**: Automatically creates repositories and pushes deployments
- **Idempotent**: Handles existing repositories and branches gracefully
- **Optional Git**: Can skip git operations for local file generation only
- **Summary Output**: Always displays summary with files created, credentials needed, and execution location

## Usage

```bash
uv run app.py publish <role-name> \
  --source-path <path>/ansible/roles/{role} \
  --github-owner <user-or-org> \
  --github-branch main \
  [--base-path <path>] \
  [--skip-git]
```

### Arguments

- `module_name`: Name of the role to publish

### Options

- `--source-path`: Path to the migrated Ansible role directory (e.g., `../chef-examples/ansible/roles/nginx_multisite`)
- `--github-owner`: GitHub user or organization name where the repository will be created
- `--github-branch`: Branch name to push to (default: `main`)
- `--base-path`: Base path for constructing deployment path. If not provided, derived from source-path (goes up 2 levels from role to get `ansible/` directory)
- `--skip-git`: Skip git steps (create repo, commit, push). Files will be created in `<base-path>/ansible/deployments/{role}/` only

### Example

```bash
uv run app.py publish nginx_multisite \
  --source-path ../chef-examples/ansible/roles/nginx_multisite \
  --github-owner elai-shalev \
  --github-branch main
```

This will:

1. Create deployment at `../chef-examples/ansible/deployments/nginx_multisite/`
2. Create repository `nginx_multisite-gitops` under `elai-shalev`
3. Push the deployment to the `main` branch

## Summary Output

The publisher always displays a summary at the end showing:

- **Files Created**: List of all generated files and directories
- **GitHub Credentials Required**: Instructions for setting up authentication (if not pushed)
- **Execution Location**: Repository URL and branch (if pushed), or local directory with push instructions

If the publish fails, the summary includes:

- **Error**: The error message
- **What Happened**: Explanation of what went wrong
- **Files Created**: Still shows what was created locally
