---
layout: default
title: Getting Started
nav_order: 3
has_children: true
---

# Getting Started

Get X2A Convertor running and migrate your first cookbook or modernize a legacy Ansible role.

## Prerequisites

- **Docker** (recommended) OR **Python 3.12+** with uv
- **LLM API access**: AWS Bedrock, OpenAI, or local Ollama
- **Source repository**: Chef, PowerShell, or legacy Ansible code to migrate/modernize

## Quick Start

1. **Install**: See [Installation](installation.html)
2. **Configure**: See [Configuration](configuration.html)
3. **Run**: Migrate or modernize a module step by step

```bash
# 1. Initialize - scan repository and create migration plan
uv run app.py init --source-dir ./chef-repo "Migrate to Ansible"

# 2. Analyze - detailed analysis of a specific module
uv run app.py analyze --source-dir ./chef-repo "Analyze nginx module"

# 3. Migrate - generate Ansible code (set --source-technology to Chef, Ansible, or PowerShell)
uv run app.py migrate \
  --source-dir ./chef-repo \
  --source-technology Chef \
  --high-level-migration-plan migration-plan.md \
  --module-migration-plan migration-plan-nginx.md \
  "Convert nginx cookbook"


# 4. Publish - create Ansible project structure
# First module (creates full project skeleton)
uv run app.py publish-project my-migration-project nginx

# Additional modules (appends role and playbook)
uv run app.py publish-project my-migration-project apache
uv run app.py publish-project my-migration-project mysql

# With custom collections and inventory (first module only)
uv run app.py publish-project my-migration-project nginx \
  --collections-file ./collections.yml \
  --inventory-file ./inventory.yml

# 5. (Optional) Sync to AAP - after pushing project to git
uv run app.py publish-aap \
  --target-repo https://github.com/<org>/my-migration-project.git \
  --target-branch main \
  --project-id my-migration-project
```

## Guides

- [Installation](installation.html) - Docker or local setup
- [Usage](usage.html) - CLI usage and examples
- [Docker Usage](docker-usage.html) - Container configuration
- [Configuration](configuration.html) - Environment variables and LLM setup

## Need Help?

- Enable debug logging: `LOG_LEVEL=DEBUG`
- Check GitHub issues for known problems
- Review [Concepts](../concepts/) for architecture details
