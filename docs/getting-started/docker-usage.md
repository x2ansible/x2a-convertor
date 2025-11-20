---
layout: default
title: Docker Usage
parent: Getting Started
nav_order: 2
---

# Docker Usage

Run X2A Convertor in containers for reproducible, enterprise-grade deployments.

## Quick Reference

```bash
# Build image
docker build -t x2a-convertor:latest .

# Run init
docker run --rm \
  -v $(pwd)/input/chef-repo:/app/source:ro \
  -v $(pwd)/output:/app/output \
  -e LLM_MODEL=claude-3-5-sonnet-20241022 \
  -e AWS_BEARER_TOKEN_BEDROCK=your-token \
  x2a-convertor:latest \
  init --source-dir /app/source "Migrate to Ansible"

# Using docker-compose
docker-compose run x2a-convertor init --source-dir /app/input/chef-repo "Migrate"
```

## Docker vs. docker-compose

| Method | Use Case | Complexity |
|--------|----------|------------|
| `docker run` | One-off migrations, CI/CD pipelines | Low |
| `docker-compose` | Development, repeated migrations | Medium |
| Kubernetes | Production scale, multi-team | High |

## Using docker run

### Basic Pattern

```bash
docker run [OPTIONS] x2a-convertor:latest [COMMAND] [ARGS]
```

### Common Options

| Option | Purpose | Example |
|--------|---------|---------|
| `--rm` | Remove container after run | `docker run --rm ...` |
| `-it` | Interactive terminal | `docker run -it ...` |
| `-v` | Mount volume | `-v ./input:/app/input` |
| `-e` | Set environment variable | `-e LLM_MODEL=...` |
| `--env-file` | Load .env file | `--env-file .env` |
| `--user` | Run as specific user | `--user $(id -u):$(id -g)` |

### Volume Mounts

```mermaid
flowchart LR
    subgraph Host["Host System"]
        InputDir[input/<br/>Chef repos]
        OutputDir[output/<br/>Ansible code]
    end

    subgraph Container["x2a-convertor Container"]
        AppInput[/app/input]
        AppOutput[/app/output]
    end

    InputDir -.Read-only.-> AppInput
    AppOutput -.Read-write.-> OutputDir

    style Host fill:#e3f2fd
    style Container fill:#e8f5e9
```

**Example**:
```bash
docker run --rm \
  -v $(pwd)/input/my-chef-repo:/app/source:ro \  # Read-only source
  -v $(pwd)/output:/app/output \                   # Writable output
  -v $(pwd):/app/work \                            # Migration plans
  x2a-convertor:latest \
  init --source-dir /app/source "Migrate"
```

### Environment Variables

#### Using -e Flag

```bash
docker run --rm \
  -e LLM_MODEL=claude-3-5-sonnet-20241022 \
  -e AWS_BEARER_TOKEN_BEDROCK=ABSKQmVkcm9j... \
  -e LOG_LEVEL=DEBUG \
  x2a-convertor:latest \
  init --help
```

#### Using --env-file

Create `.env`:
```bash
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=your-token
LOG_LEVEL=INFO
MAX_EXPORT_ATTEMPTS=5
```

Run:
```bash
docker run --rm --env-file .env \
  -v $(pwd)/input:/app/input \
  x2a-convertor:latest \
  init --source-dir /app/input/chef-repo "Migrate"
```

## Using docker-compose

### docker-compose.yml

The repository includes a pre-configured `docker-compose.yml`:

```yaml
version: '3.8'

services:
  x2a-convertor:
    build: .
    image: x2a-convertor:latest
    volumes:
      - ./input:/app/input:ro
      - ./ansible:/app/ansible
      - ./examples:/app/examples:ro
    environment:
      - LLM_MODEL=${LLM_MODEL:-claude-3-5-sonnet-20241022}
      - AWS_BEARER_TOKEN_BEDROCK=${AWS_BEARER_TOKEN_BEDROCK}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    stdin_open: true
    tty: true
    command: ["--help"]

  docs:
    image: jekyll/jekyll:latest
    volumes:
      - ./docs:/srv/jekyll
    ports:
      - "4000:4000"
    command: jekyll serve --livereload
```

### Common Commands

#### Build

```bash
docker-compose build
```

#### Run Commands

```bash
# Init
docker-compose run --rm x2a-convertor \
  init --source-dir /app/input/chef-repo "Migrate to Ansible"

# Analyze
docker-compose run --rm x2a-convertor \
  analyze --source-dir /app/input/chef-repo "Analyze nginx cookbook"

# Migrate
docker-compose run --rm x2a-convertor \
  migrate \
  --source-dir /app/input/chef-repo \
  --source-technology Chef \
  --high-level-migration-plan /app/input/chef-repo/migration-plan.md \
  --module-migration-plan /app/input/chef-repo/migration-plan-nginx.md \
  "Migrate nginx"

# Validate
docker-compose run --rm x2a-convertor \
  validate "nginx"
```

#### Interactive Shell

```bash
docker-compose run --rm x2a-convertor /bin/bash
```

Inside container:
```bash
uv run app.py init --source-dir /app/input/chef-repo "Migrate"
```

### Environment Variables with docker-compose

Create `.env` in project root (loaded automatically):

```bash
# LLM Configuration
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=your-bedrock-token
AWS_REGION=eu-west-2

# Logging
LOG_LEVEL=INFO
DEBUG_ALL=false

# Migration Settings
MAX_EXPORT_ATTEMPTS=5
RECURSION_LIMIT=100
```

docker-compose will use these automatically.

## Advanced Patterns

### CI/CD Pipeline Integration

**GitHub Actions Example**:

```yaml
name: Migrate Cookbooks

on:
  workflow_dispatch:
    inputs:
      cookbook_name:
        description: 'Cookbook to migrate'
        required: true

jobs:
  migrate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Build X2A Container
        run: docker build -t x2a-convertor:latest .

      - name: Run Migration
        env:
          AWS_BEARER_TOKEN_BEDROCK: ${{ secrets.AWS_BEARER_TOKEN }}
        run: |
          docker run --rm \
            -v $(pwd)/chef-repo:/app/source:ro \
            -v $(pwd)/ansible-output:/app/ansible \
            -e LLM_MODEL=claude-3-5-sonnet-20241022 \
            -e AWS_BEARER_TOKEN_BEDROCK=$AWS_BEARER_TOKEN_BEDROCK \
            x2a-convertor:latest \
            migrate --source-dir /app/source \
              --source-technology Chef \
              --module-migration-plan /app/source/migration-plan-${{ inputs.cookbook_name }}.md \
              "Migrate ${{ inputs.cookbook_name }}"

      - name: Upload Ansible Output
        uses: actions/upload-artifact@v3
        with:
          name: ansible-${{ inputs.cookbook_name }}
          path: ansible-output/
```

### Batch Processing

Migrate multiple cookbooks in parallel:

```bash
#!/bin/bash
# migrate-all.sh

COOKBOOKS=("nginx" "mysql" "redis" "app-server")

for cookbook in "${COOKBOOKS[@]}"; do
  docker run --rm \
    -v $(pwd)/chef-repo:/app/source:ro \
    -v $(pwd)/ansible:/app/ansible \
    --env-file .env \
    x2a-convertor:latest \
    migrate \
      --source-dir /app/source \
      --source-technology Chef \
      --high-level-migration-plan /app/source/migration-plan.md \
      --module-migration-plan /app/source/migration-plan-${cookbook}.md \
      "Migrate ${cookbook}" &
done

wait
echo "All migrations complete"
```

### Air-Gapped Environments

For networks without internet access:

#### 1. Save Image

On connected system:
```bash
docker build -t x2a-convertor:latest .
docker save x2a-convertor:latest | gzip > x2a-convertor.tar.gz
```

#### 2. Transfer to Air-Gapped System

```bash
scp x2a-convertor.tar.gz target-system:
```

#### 3. Load Image

On air-gapped system:
```bash
gunzip < x2a-convertor.tar.gz | docker load
```

#### 4. Configure Local LLM

```bash
# Run Ollama locally
docker run -d -p 11434:11434 ollama/ollama
docker exec -it ollama ollama pull llama3:8b

# Configure X2A
docker run --rm \
  -e LLM_MODEL=openai:llama3:8b \
  -e OPENAI_API_BASE=http://host.docker.internal:11434/v1 \
  -e OPENAI_API_KEY=not-needed \
  --network host \
  x2a-convertor:latest \
  init --source-dir /app/source "Migrate"
```

## Podman Usage

X2A Convertor works identically with Podman:

```bash
# Build
podman build -t x2a-convertor:latest .

# Run
podman run --rm \
  -v ./input:/app/input:ro \
  -v ./output:/app/output \
  --env-file .env \
  x2a-convertor:latest \
  init --source-dir /app/input/chef-repo "Migrate"

# Using Makefile
DOCKER=podman make build
DOCKER=podman make run-init name=my-cookbook
```

### Podman-specific Considerations

**Rootless mode** (default in Podman):
- No need for sudo
- Different UID/GID mapping

**SELinux contexts**:
```bash
# Add :Z flag for volume mounts
podman run --rm \
  -v ./input:/app/input:ro,Z \
  -v ./output:/app/output:Z \
  x2a-convertor:latest ...
```

## Resource Limits

### Memory Limits

```bash
docker run --rm \
  --memory=2g \
  --memory-swap=2g \
  x2a-convertor:latest \
  migrate ...
```

### CPU Limits

```bash
docker run --rm \
  --cpus=2 \
  x2a-convertor:latest \
  migrate ...
```

### Combined in docker-compose

```yaml
services:
  x2a-convertor:
    # ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

## Debugging

### View Logs

```bash
# Run with debug logging
docker run --rm \
  -e LOG_LEVEL=DEBUG \
  -e DEBUG_ALL=true \
  x2a-convertor:latest \
  init --source-dir /app/source "Migrate"
```

### Interactive Debugging

```bash
# Get shell in container
docker run --rm -it \
  -v $(pwd)/input:/app/input \
  --env-file .env \
  x2a-convertor:latest \
  /bin/bash

# Inside container
uv run app.py --help
python -m pdb app.py init ...
```

### Inspect Container

```bash
# Run without removing
docker run -it --name x2a-debug \
  x2a-convertor:latest \
  init --source-dir /app/source "Migrate"

# Inspect after run
docker logs x2a-debug
docker exec -it x2a-debug /bin/bash

# Cleanup
docker rm x2a-debug
```

## Security Best Practices

### 1. Never Commit Secrets

```bash
# Bad
docker run -e AWS_BEARER_TOKEN_BEDROCK=ABSKQmVkcm9j... x2a-convertor

# Good
docker run --env-file .env x2a-convertor
```

Ensure `.env` is in `.gitignore`.

### 2. Use Read-Only Mounts

```bash
docker run --rm \
  -v ./chef-repo:/app/source:ro \  # Read-only
  x2a-convertor:latest \
  init --source-dir /app/source "Migrate"
```

### 3. Run as Non-Root (Podman default)

```bash
docker run --rm \
  --user $(id -u):$(id -g) \
  -v ./input:/app/input \
  x2a-convertor:latest ...
```
