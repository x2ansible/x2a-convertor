---
layout: default
title: Publishing
parent: Concepts
nav_order: 6
---

# Publisher

The publisher automates GitOps deployment of migrated Ansible roles to GitHub using template-based generation and LangGraph orchestration.

## Purpose

Transforms local Ansible roles into production-ready GitOps configurations by generating playbooks, job templates, and GitHub Actions workflows from templates, organizing roles into standardized structures - ready to be loaded to AAP. The publisher can also create a pull request for the target GitHub repository that will store the ansible roles.

## Workflow

Uses a LangGraph workflow with deterministic tools (no LLM generation):

1. Create directory structure (`roles/`, `playbooks/`, `aap-config/`, `.github/`)
2. Copy role directory
3. Generate playbook, job template, and GitHub Actions workflow from templates
4. Verify files exist
5. Commit, push branch, and create pull request

## Key Features

- **Template-based**: Jinja2 templates ensure consistent output
- **Deterministic**: No LLM calls during generation for reproducible results
- **GitOps-ready**: Automatically creates PRs with proper structure
- **Optional Git**: Can skip git operations for local file generation

## Usage

```bash
uv run app.py publish <role-name> \
  --source-path ./ansible/my_role \
  --github-repository-url https://github.com/org/repo \
  --github-branch main
  --skip-git [optional]
```

