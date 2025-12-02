---
layout: default
title: Docker Usage
parent: Getting Started
nav_order: 2
---

# Docker Usage

Run X2A Convertor in containers for reproducible, enterprise-grade deployments.

## Quick Reference

We're using this repository as default test project:

```
git clone https://github.com/x2ansible/chef-examples.git
cd chef-examples
```

## Initialization

The first thing we need to do is create the migration-plan.md file which will be used as a reference file:

```bash
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0 \
  -e AWS_REGION=$AWS_REGION \
  -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
  quay.io/x2ansible/x2a-convertor:latest \
  init --source-dir /app/source "Migrate to Ansible"
```

This will create a **migration-plan.md** with a lot of details.

## Analyze:

```bash
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0 \
  -e AWS_REGION=$AWS_REGION \
  -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
  quay.io/x2ansible/x2a-convertor:latest \
  analyze "please make a detailed plan for nginx-multisite"  --source-dir /app/source/
```

This will make a blueprint of what the model understands about the migration of that cookbook. In this case, it will create a **migration-plan-nginx-multisite.md**

## Migrate

```bash
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0 \
  -e AWS_REGION=$AWS_REGION \
  -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
  quay.io/x2ansible/x2a-convertor:latest \
  migrate --source-dir /app/source/ --source-technology Chef --high-level-migration-plan migration-plan.md --module-migration-plan migration-plan-nginx-multisite.md "Convert the 'nginx-multisite' module"
```

This will generate real Ansible code, primarily in `ansible/roles/nginx_multisite` with all details


## Publish

```bash
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0 \
  -e AWS_REGION=$AWS_REGION \
  -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
  quay.io/x2ansible/x2a-convertor:latest \
  publish "nginx" --source-path /app/source/ansible/roles/nginx_multisite --github-owner eloycoto --github-branch main --base-path /app/source/ansible/deployments --skip-git
```

This will generate the deployements for the role, can be found at:

- Role: `./ansible/deployments/nginx/roles/nginx/`
- Playbook: `./ansible/deployments/nginx/playbooks/nginx_deploy.yml`
- Job Template: `./ansible/deployments/nginx/aap-config/job-templates/nginx_deploy.yaml`
- GitHub Actions: `./ansible/deployments/nginx/.github/workflows/deploy.yml`

And an example report like this:

```
================================================================================
PUBLISH SUMMARY
================================================================================

Files Created:
  - Role: /app/source/ansible/deployments/nginx/roles/nginx/
  - Playbook: /app/source/ansible/deployments/nginx/playbooks/nginx_deploy.yml
  - Job Template: /app/source/ansible/deployments/nginx/aap-config/job-templates/nginx_deploy.yaml
  - GitHub Actions: /app/source/ansible/deployments/nginx/.github/workflows/deploy.yml

GitHub Credentials Required:
  To push to GitHub, you need to set up authentication:
  1. Create a Personal Access Token (PAT) with 'repo' scope:
     - Go to: https://github.com/settings/tokens
     - Click 'Generate new token (classic)'
     - Select 'repo' scope
     - Copy the token
  2. Set the token as an environment variable:
     export GITHUB_TOKEN='your_token_here'

Execution Location:
  Local directory: /app/source/ansible/deployments/nginx
```
