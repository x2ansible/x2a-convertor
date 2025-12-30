---
layout: default
title: Usage
parent: Getting Started
nav_order: 1
---

# Usage

Run X2A Convertor natively for local development and quick migrations.

## Quick Reference

We're using this repository as default test project:

```
git clone https://github.com/x2ansible/chef-examples.git
cd chef-examples
```

## Requirements

This example uses the AWS Bedrock provider. You'll need to configure the following environment variables:

- **AWS_REGION**: The AWS region where the model will run
- **AWS_BEARER_TOKEN_BEDROCK**: The API key to connect to the LLM
- **LLM_MODEL**: The model to use (this guide uses `anthropic.claude-3-7-sonnet-20250219-v1:0`). Note: Some regions require the `us.` prefix

Export these variables in your shell before running commands:

```bash
export LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0
export AWS_REGION=your-aws-region
export AWS_BEARER_TOKEN_BEDROCK=your-bearer-token

# For publish command
export GITHUB_TOKEN=your-github-token
export AAP_CONTROLLER_URL=your-aap-url

# For AAP Authentication
export AAP_OAUTH_TOKEN=your-oauth-token or export AAP_USERNAME=your-username and export AAP_PASSWORD=your-password

#AAP integration extra configuration (optional)
export AAP_CA_BUNDLE=your-ca-bundle-path
export AAP_VERIFY_SSL=true
```

## Initialization

The first thing we need to do is create the migration-plan.md file which will be used as a reference file:

```bash
uv run app.py init --source-dir . "Migrate to Ansible"
```

This will create a **migration-plan.md** with a lot of details.

## Analyze:

```bash
uv run app.py analyze "please make a detailed plan for nginx-multisite" --source-dir .
```

This will make a blueprint of what the model understands about the migration of that cookbook. In this case, it will create a **migration-plan-nginx-multisite.md**

## Migrate

```bash
uv run app.py migrate --source-dir . --source-technology Chef --high-level-migration-plan migration-plan.md --module-migration-plan migration-plan-nginx-multisite.md "Convert the 'nginx-multisite' module"
```

This will generate real Ansible code, primarily in `ansible/roles/nginx_multisite` with all details

## Publish

```bash
uv run app.py publish "nginx_multisite" --source-paths ./ansible/roles/nginx_multisite --github-owner eloycoto --github-branch main
```

This will generate the deployments for the role, push it to GitHub, and (when AAP env vars are set) upsert an AAP Project and trigger a sync.

- ansible.cfg: `./ansible/deployments/nginx_multisite/ansible.cfg`
- Collections requirements: `./ansible/deployments/nginx_multisite/collections/requirements.yml`
- Inventory: `./ansible/deployments/nginx_multisite/inventory/hosts.yml`
- Role: `./ansible/deployments/nginx_multisite/roles/nginx_multisite/`
- Playbook: `./ansible/deployments/nginx_multisite/playbooks/run_nginx_multisite.yml`

## Notes

Adding `--skip-git` makes the publish step **local-only** (no repository creation/push), and therefore the AAP sync step is skipped.

example:

```bash
uv run app.py publish "nginx_multisite" --source-paths ./ansible/roles/nginx_multisite --skip-git
```

To **push to GitHub but skip the AAP sync**, run publish without `--skip-git` but do **not** set `AAP_CONTROLLER_URL` (AAP integration is enabled only when that variable is present). For
