---
layout: default
title: Getting Started
nav_order: 3
has_children: true
---

# Getting Started

Get X2A Convertor running and migrate your first cookbook.

## Prerequisites

- **Docker** (recommended) OR **Python 3.12+** with uv
- **LLM API access**: AWS Bedrock, OpenAI, or local Ollama
- **Source repository**: Chef, Puppet, or Salt code to migrate

## Quick Start

1. **Install**: See [Installation](installation.html)
2. **Configure**: See [Configuration](configuration.html)
3. **Run**: Five commands to migrate a cookbook

```bash
# 1. Initialize - scan repository and create migration plan
uv run app.py init --source-dir ./chef-repo "Migrate to Ansible"

# 2. Analyze - detailed analysis of a specific cookbook
uv run app.py analyze --source-dir ./chef-repo "Analyze nginx cookbook"

# 3. Migrate - generate Ansible code
uv run app.py migrate \
  --source-dir ./chef-repo \
  --source-technology Chef \
  --high-level-migration-plan migration-plan.md \
  --module-migration-plan migration-plan-nginx.md \
  "Convert nginx cookbook"

# 4. Validate - verify output quality
uv run app.py validate "nginx"

# 5. Publish - create Ansible project and optionally push to GitHub
# Single role
uv run app.py publish "nginx" \
  --source-paths ./ansible/roles/nginx \
  --github-owner <user-or-org> \
  --github-branch main

# Multiple roles
uv run app.py publish "nginx" "apache" "mysql" \
  --source-paths ./ansible/roles/nginx \
  --source-paths ./ansible/roles/apache \
  --source-paths ./ansible/roles/mysql \
  --github-owner <user-or-org> \
  --github-branch main

# With custom collections and inventory (local only)
uv run app.py publish "nginx" \
  --source-paths ./ansible/roles/nginx \
  --collections-file ./collections.yml \
  --inventory-file ./inventory.yml \
  --skip-git
```

## Guides

- [Installation](installation.html) - Docker or local setup
- [Docker Usage](docker-usage.html) - Container configuration
- [Configuration](configuration.html) - Environment variables and LLM setup

## Need Help?

- Enable debug logging: `LOG_LEVEL=DEBUG`
- Check GitHub issues for known problems
- Review [Concepts](../concepts/) for architecture details
