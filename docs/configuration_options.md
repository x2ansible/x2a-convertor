---
layout: default
title: Configuration Options
nav_order: 4
---

# Environment Variables
{: .no_toc }

Auto-generated from `src/config/settings.py`.
{: .fs-3 .text-grey-dk-000 }

## Table of contents
{: .no_toc .text-delta }

* TOC
{:toc}

---

## LLM Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LLM_MODEL` | string | `openai/gpt-oss-120b-maas` | Language model to use |
| `MAX_TOKENS` | integer | `8192` | Maximum tokens for LLM responses |
| `TEMPERATURE` | float | `0.1` | Model temperature (creativity) |
| `REASONING_EFFORT` | string | - | Claude reasoning effort level |
| `RATE_LIMIT_REQUESTS` | integer | - | Rate limit requests per second |

## OpenAI Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENAI_API_BASE` | string | - | OpenAI/compatible API endpoint |
| `OPENAI_API_KEY` | secret | `not-needed` | API key for OpenAI provider |

## AWS Bedrock Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AWS_BEARER_TOKEN_BEDROCK` | secret | - | AWS Bedrock bearer token |
| `AWS_ACCESS_KEY_ID` | secret | - | AWS access key ID |
| `AWS_SECRET_ACCESS_KEY` | secret | - | AWS secret access key |
| `AWS_SESSION_TOKEN` | secret | - | AWS session token (temporary credentials) |
| `AWS_REGION` | string | `eu-west-2` | AWS region for Bedrock |

## Ansible Automation Platform Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AAP_CONTROLLER_URL` | string | - | AAP Controller base URL |
| `AAP_ORG_NAME` | string | - | Organization name |
| `AAP_API_PREFIX` | string | `/api/controller/v2` | API path prefix |
| `AAP_OAUTH_TOKEN` | secret | - | OAuth token for auth |
| `AAP_USERNAME` | string | - | Username for basic auth |
| `AAP_PASSWORD` | secret | - | Password for basic auth |
| `AAP_CA_BUNDLE` | string | - | Path to CA certificate |
| `AAP_VERIFY_SSL` | boolean | `true` | SSL verification flag |
| `AAP_TIMEOUT_S` | float | `30.0` | Request timeout in seconds |
| `AAP_PROJECT_NAME` | string | - | Project name in AAP |
| `AAP_SCM_CREDENTIAL_ID` | integer | - | Credential ID for private repos |
| `AAP_GALAXY_REPOSITORY` | string | `published` | Galaxy repository to search (published, staging, community) |

## GitHub Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `GITHUB_TOKEN` | secret | - | GitHub API authentication token |
| `GITHUB_API_BASE` | string | `https://api.github.com` | GitHub API base URL |

## Processing Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RECURSION_LIMIT` | integer | `500` | Maximum recursion limit for LLM calls |
| `MAX_WRITE_ATTEMPTS` | integer | `10` | Maximum number of attempts to write all files from checklist |
| `MAX_VALIDATION_ATTEMPTS` | integer | `5` | Maximum number of attempts to fix validation errors |

## Logging Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEBUG_ALL` | boolean | `false` | Enable debug logging for all libraries |
| `LOG_LEVEL` | enum: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL' | `INFO` | Log level for x2convertor namespace |

## Molecule Testing Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MOLECULE_DOCKER_IMAGE` | string | `docker.io/geerlingguy/docker-fedora40-ansible:latest` | Docker image for Molecule tests |
