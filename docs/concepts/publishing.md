---
layout: default
title: Publishing
parent: Concepts
nav_order: 6
---

# Publisher

The publisher automates GitOps deployment of migrated Ansible roles to GitHub by creating new repositories and pushing deployment configurations using template-based generation and LangGraph orchestration.

## Purpose

Transforms local Ansible roles into production-ready Ansible project structures by:

- Taking one or more roles from `<path>/ansible/roles/{role}`
- Creating a complete Ansible project structure with standard directories
- Generating wrapper playbooks for each role
- Creating configuration files (ansible.cfg, collections/requirements.yml, inventory/hosts.yml)
- Optionally creating a new GitOps repository and pushing the deployment to it

## Workflow

Uses a LangGraph workflow with deterministic tools (no LLM generation):

1. **Create ansible project**: Creates complete project structure in one step:
   - Directory structure (`collections/`, `inventory/`, `roles/`, `playbooks/`)
   - Copies all role directories
   - Generates wrapper playbooks for each role (`run_{role}.yml`)
   - Generates `ansible.cfg` with project-specific configuration
   - Generates `collections/requirements.yml` (with optional collections data)
   - Generates `inventory/hosts.yml` (with optional inventory data)
2. **Verify files exist**: Validates all required files were created
3. **Create GitHub repository** (if not `--skip-git`): Creates repository named `{role}-gitops` (single role) or `ansible-project-gitops` (multiple roles)
4. **Commit changes** (if not `--skip-git`): Commits all project files to the branch
5. **Push branch** (if not `--skip-git`): Pushes the branch to the remote repository
6. **Display summary**: Shows files created, credentials needed, and execution location

## Ansible Project Structure

The publisher creates a complete Ansible project with the following structure:

```
<path>/ansible/deployments/{role}/  (or ansible-project for multiple roles)
├── ansible.cfg                     # Project-specific Ansible configuration
├── collections/
│   └── requirements.yml            # Collections requirements (can be customized)
├── inventory/
│   └── hosts.yml                   # Inventory file (can be customized)
├── roles/
│   ├── migrated_role_A/            # Copied role source code
│   │   ├── tasks/
│   │   ├── meta/
│   │   └── ...
│   └── migrated_role_B/            # Additional roles for multi-role projects
│       ├── tasks/
│       ├── meta/
│       └── ...
└── playbooks/
    ├── run_migrated_role_A.yml     # Wrapper playbook for Role A
    └── run_migrated_role_B.yml     # Wrapper playbook for Role B
```

This entire project directory becomes the root of the GitOps repository when pushed.

### Key Files

- **`ansible.cfg`**: Configures roles path, collections path, inventory location, and other Ansible settings
- **`collections/requirements.yml`**: Defines required Ansible collections (can be customized via `--collections-file`)
- **`inventory/hosts.yml`**: Defines target hosts and groups (can be customized via `--inventory-file`)
- **`playbooks/run_{role}.yml`**: Wrapper playbooks that execute each role
- **`roles/{role}/`**: Complete Ansible role directories copied from source

## Idempotency Rules

The publisher follows these idempotency rules:

1. **Repository doesn't exist**: Creates new repository `{role}-gitops` and pushes to branch
2. **Repository exists, branch doesn't exist**: Creates new branch and pushes to it
3. **Repository exists, branch exists**: Fails with clear error message indicating branch already exists

## Key Features

- **Complete Ansible Project**: Creates standard Ansible project structure with all required directories and files
- **Multi-Role Support**: Can publish single or multiple roles in one project
- **Template-based**: Jinja2 templates ensure consistent output for playbooks, configs, and inventory
- **Customizable**: Supports custom collections and inventory via file inputs
- **Deterministic**: No LLM calls during generation for reproducible results
- **GitOps-ready**: Automatically creates repositories and pushes deployments
- **Idempotent**: Handles existing repositories and branches gracefully
- **Optional Git**: Can skip git operations for local file generation only
- **Summary Output**: Always displays summary with files created, credentials needed, and execution location

## Usage

### Single Role

```bash
uv run app.py publish <role-name> \
  --source-paths <path>/ansible/roles/{role} \
  --github-owner <user-or-org> \
  --github-branch main \
  [--skip-git] \
  [--collections-file <path>] \
  [--inventory-file <path>]
```

### Multiple Roles

```bash
uv run app.py publish <role1> <role2> <role3> \
  --source-paths <path>/ansible/roles/{role1} \
  --source-paths <path>/ansible/roles/{role2} \
  --source-paths <path>/ansible/roles/{role3} \
  --github-owner <user-or-org> \
  --github-branch main \
  [--skip-git] \
  [--collections-file <path>] \
  [--inventory-file <path>]
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

#### Single Role

```bash
uv run app.py publish nginx_multisite \
  --source-paths ../chef-examples/ansible/roles/nginx_multisite \
  --github-owner elai-shalev \
  --github-branch main
```

This will:

1. Create Ansible project at `../chef-examples/ansible/deployments/nginx_multisite/`
2. Create repository `nginx_multisite-gitops` under `elai-shalev`
3. Push the project to the `main` branch

#### Multiple Roles

```bash
uv run app.py publish nginx apache mysql \
  --source-paths ../chef-examples/ansible/roles/nginx \
  --source-paths ../chef-examples/ansible/roles/apache \
  --source-paths ../chef-examples/ansible/roles/mysql \
  --github-owner elai-shalev \
  --github-branch main
```

This will:

1. Create consolidated Ansible project at `../chef-examples/ansible/deployments/ansible-project/`
2. Include all three roles in the project
3. Create repository `ansible-project-gitops` under `elai-shalev`
4. Push the project to the `main` branch

#### With Custom Collections and Inventory

```bash
uv run app.py publish nginx_multisite \
  --source-paths ../chef-examples/ansible/roles/nginx_multisite \
  --github-owner elai-shalev \
  --collections-file ./collections.yml \
  --inventory-file ./inventory.yml \
  --skip-git
```

This creates the project locally with custom collections and inventory without pushing to GitHub.

### Collections File Format

The `--collections-file` accepts a YAML or JSON file with a list of collections:

**YAML format (`collections.yml`):**

```yaml
- name: community.general
  version: ">=1.0.0"
- name: ansible.posix
  version: ">=1.5.0"
- name: community.docker
```

**JSON format (`collections.json`):**

```json
[
  { "name": "community.general", "version": ">=1.0.0" },
  { "name": "ansible.posix", "version": ">=1.5.0" },
  { "name": "community.docker" }
]
```

If not provided, an empty collections list is generated.

### Inventory File Format

The `--inventory-file` accepts a YAML or JSON file with inventory structure:

**YAML format (`inventory.yml`):**

```yaml
all:
  children:
    web_servers:
      hosts:
        web1:
          ansible_host: 10.0.0.1
        web2:
          ansible_host: 10.0.0.2
      vars:
        ansible_user: ubuntu
    db_servers:
      hosts:
        db1:
          ansible_host: 10.0.1.1
```

**JSON format (`inventory.json`):**

```json
{
  "all": {
    "children": {
      "web_servers": {
        "hosts": {
          "web1": { "ansible_host": "10.0.0.1" },
          "web2": { "ansible_host": "10.0.0.2" }
        },
        "vars": {
          "ansible_user": "ubuntu"
        }
      }
    }
  }
}
```

If not provided, a sample inventory with localhost connections is generated.

## Summary Output

The publisher always displays a summary at the end showing:

- **Files Created**: List of all generated files and directories
- **GitHub Credentials Required**: Instructions for setting up authentication (if not pushed)
- **Execution Location**: Repository URL and branch (if pushed), or local directory with push instructions

If the publish fails, the summary includes:

- **Error**: The error message
- **What Happened**: Explanation of what went wrong
- **Files Created**: Still shows what was created locally
