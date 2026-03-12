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

## Requirements

This example uses the AWS Bedrock provider. You'll need to configure the following environment variables:

- **AWS_REGION**: The AWS region where the model will run
- **AWS_BEARER_TOKEN_BEDROCK**: The API key to connect to the LLM
- **LLM_MODEL**: The model to use (this guide uses `anthropic.claude-3-7-sonnet-20250219-v1:0`). Note: Some regions require the `us.` prefix

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
  -e AAP_CONTROLLER_URL=$AAP_CONTROLLER_URL \
  -e AAP_ORG_NAME=$AAP_ORG_NAME \
  -e AAP_OAUTH_TOKEN=$AAP_OAUTH_TOKEN \
  -e AAP_GALAXY_REPOSITORY=$AAP_GALAXY_REPOSITORY \
  quay.io/x2ansible/x2a-convertor:latest \
  migrate --source-dir /app/source/ --source-technology Chef --high-level-migration-plan migration-plan.md --module-migration-plan migration-plan-nginx-multisite.md "Convert the 'nginx-multisite' module"
```

This will generate real Ansible code, primarily in `ansible/roles/nginx_multisite` with all details. When AAP env vars are set, it will also search your Private Automation Hub for reusable collections (see [AAP Discovery Agent]({% link concepts/export-agents.md %}#aap-discovery-agent-optional)).

## Publish Project

```bash
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  quay.io/x2ansible/x2a-convertor:latest \
  publish-project my-migration-project nginx_multisite
```

This creates (or appends to) an Ansible project under `<project-id>/ansible-project/`. On the first module it creates the full skeleton (ansible.cfg, collections, inventory). On subsequent modules it adds the role and playbook.

- ansible.cfg: `./<project-id>/ansible-project/ansible.cfg`
- Collections requirements: `./<project-id>/ansible-project/collections/requirements.yml`
- Inventory: `./<project-id>/ansible-project/inventory/hosts.yml`
- Role: `./<project-id>/ansible-project/roles/nginx_multisite/`
- Playbook: `./<project-id>/ansible-project/playbooks/run_nginx_multisite.yml`

## Publish to AAP (Optional)

```bash
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e AAP_CONTROLLER_URL=$AAP_CONTROLLER_URL \
  -e AAP_ORG_NAME=$AAP_ORG_NAME \
  -e AAP_OAUTH_TOKEN=$AAP_OAUTH_TOKEN \
  quay.io/x2ansible/x2a-convertor:latest \
  publish-aap --target-repo https://github.com/companyName/my-migration-project.git --target-branch main --project-id my-migration-project
```

This creates or updates an AAP Project pointing to the given repository and branch, then triggers a project sync.
