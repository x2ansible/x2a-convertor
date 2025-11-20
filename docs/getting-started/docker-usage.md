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

```
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0 \
  -e AWS_REGION=$AWS_REGION \
  -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
  quay.io/x2ansible/x2a-convertor:latest \
  analyze "please make a detailed plan for cache"  --source-dir /app/source/
```

This will make a blueprint of what the model understands about the migration of that cookbook. In this case, it will create a **migration-plan-nginx-multisite.md**

## Migrate

```
podman run --rm -ti \
  -v $(pwd)/:/app/source:Z \
  -e LLM_MODEL=anthropic.claude-3-7-sonnet-20250219-v1:0 \
  -e AWS_REGION=$AWS_REGION \
  -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
  quay.io/x2ansible/x2a-convertor:latest \
  uv run app.py migrate --source-dir /app/source/ --source-technology Chef --high-level-migration-plan migration-plan.md --module-migration-plan migration-plan-nginx-multisite.md "Convert the 'nginx-multisite' module"
```

This will generate real Ansible code, primarily in `ansible/nginx-multisite` with all details
