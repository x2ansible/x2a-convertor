---
layout: default
title: Installation
parent: Getting Started
nav_order: 1
---

# Installation

Two installation methods: Docker (recommended) or local Python environment.

## Method 1: Docker (Recommended)

Docker provides consistent environments across different systems and is the recommended approach for enterprise deployments.

### Prerequisites

- Docker or Podman installed
- 2GB free disk space
- Internet connection (for pulling image)

### Installation Steps

#### 1. Clone Repository

```bash
git clone https://github.com/x2ansible/x2a-convertor.git
cd x2a-convertor
```

#### 2. Build Container Image

Using Docker:
```bash
docker build -t x2a-convertor:latest .
```

Using Podman:
```bash
podman build -t x2a-convertor:latest .
```

Using Makefile:
```bash
# Docker (default)
make build

# Podman
DOCKER=podman make build
```

#### 3. Verify Installation

```bash
docker run --rm x2a-convertor:latest --help
```

Expected output:
```
Usage: app.py [OPTIONS] COMMAND [ARGS]...

  X2Ansible - Infrastructure Migration Tool

Commands:
  analyze   Perform detailed analysis and create module...
  init      Initialize project with interactive message
  migrate   Based on the migration plan produced within...
  validate  Validate migrated module against original...
```

### What's Included

- Red Hat UBI 9, Python 3.12, uv package manager
- Chef Workstation CLI (for Chef analysis)
- All dependencies from `pyproject.toml`

## Method 2: Local Installation

For development or environments where containers are not available.

### Prerequisites

- Python 3.12 or higher
- uv package manager
- Chef Workstation (for Chef cookbook analysis)
- Git

### Installation Steps

#### 1. Install Python 3.12+

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install python3.12 python3.12-dev
```

**RHEL/Fedora**:
```bash
sudo dnf install python3.12 python3.12-devel
```

**macOS**:
```bash
brew install python@3.12
```

#### 2. Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Add to PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

#### 3. Install Chef Workstation (Optional for Chef migrations)

```bash
curl -L https://omnitruck.chef.io/install.sh | sudo bash -s -- -P chef-workstation
```

Verify:
```bash
chef --version
berks --version
```

#### 4. Clone and Install X2A Convertor

```bash
git clone https://github.com/x2ansible/x2a-convertor.git
cd x2a-convertor

# Install dependencies
uv sync
```

#### 5. Verify Installation

```bash
uv run app.py --help
```

## Environment Setup

Create `.env` file in project root:

```bash
# LLM Configuration
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=your-bedrock-token
LOG_LEVEL=INFO
```

See [Configuration](configuration.html) for all options.

## Verify Installation

```bash
# Docker
docker run --rm --env-file .env x2a-convertor:latest --help

# Local
uv run app.py --help
```

## Troubleshooting

**Docker build fails**: Try `docker build --network=host -t x2a-convertor .`

**uv sync fails**: Check Python version with `python3 --version` (needs 3.12+)

**Permission denied (Docker)**: Use `--user $(id -u):$(id -g)` flag

## Next Steps

- [Configuration](configuration.html) - Set up LLM providers
- [Docker Usage](docker-usage.html) - Advanced container options
