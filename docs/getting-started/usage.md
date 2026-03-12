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

# For AAP Collection Discovery during migrate (optional)
# When set, migrate will search Private Hub for reusable collections
# See: /concepts/export-agents#aap-discovery-agent-optional
export AAP_CONTROLLER_URL=your-aap-url
export AAP_ORG_NAME=your-org-name
export AAP_OAUTH_TOKEN=your-oauth-token
export AAP_GALAXY_REPOSITORY=published  # published, staging, or community

# For publish-aap command (optional)
export AAP_CONTROLLER_URL=your-aap-url

# For AAP Authentication
export AAP_OAUTH_TOKEN=your-oauth-token  # or export AAP_USERNAME=your-username and export AAP_PASSWORD=your-password

# AAP integration extra configuration (optional)
export AAP_CA_BUNDLE=your-ca-bundle-path
export AAP_VERIFY_SSL=true
```

## Initialization

The first thing we need to do is create the migration-plan.md file which will be used as a reference file:

```bash
uv run app.py init \
  --source-dir . \
  "Migrate to Ansible"

```

This will create a **migration-plan.md** with a lot of details.

## Analyze:

```bash
uv run app.py analyze \
  --source-dir . \
  "please make a detailed plan for nginx-multisite"

```

This will make a blueprint of what the model understands about the migration of that cookbook. In this case, it will create a **migration-plan-nginx-multisite.md**

## Migrate

```bash
uv run app.py migrate \
  --source-dir . \
  --source-technology Chef \
  --high-level-migration-plan migration-plan.md \
  --module-migration-plan migration-plan-nginx-multisite.md \
  "Convert the 'nginx-multisite' module"

```

This will generate real Ansible code, primarily in `ansible/roles/nginx_multisite` with all details. When AAP env vars are set, it will also search your Private Automation Hub for reusable collections (see [AAP Discovery Agent]({% link concepts/export-agents.md %}#aap-discovery-agent-optional)).

## Publish Project

```bash
uv run app.py publish-project my-migration-project nginx_multisite

```

This creates (or appends to) an Ansible project under `<project-id>/ansible-project/`. On the first module it creates the full skeleton (ansible.cfg, collections, inventory). On subsequent modules it adds the role and playbook.

- ansible.cfg: `./<project-id>/ansible-project/ansible.cfg`
- Collections requirements: `./<project-id>/ansible-project/collections/requirements.yml`
- Inventory: `./<project-id>/ansible-project/inventory/hosts.yml`
- Role: `./<project-id>/ansible-project/roles/nginx_multisite/`
- Playbook: `./<project-id>/ansible-project/playbooks/run_nginx_multisite.yml`

## Publish to AAP (Optional)

```bash
uv run app.py publish-aap \
  --target-repo https://github.com/companyName/my-migration-project.git \
  --target-branch main \
  --project-id my-migration-project

```

This creates or updates an AAP Project pointing to the given repository and branch, then triggers a project sync.

## Notes

Publishing is now split into two separate commands:

- **`publish-project`** creates the local Ansible project structure. Run it once per migrated module.
- **`publish-aap`** syncs a git repository to AAP. Run it after pushing your project to a git repository.

To **skip the AAP sync**, simply omit the `publish-aap` step. The `publish-project` command is always local-only.
