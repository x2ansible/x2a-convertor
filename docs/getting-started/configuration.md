---
layout: default
title: Configuration
parent: Getting Started
nav_order: 3
---

# Configuration

Configure X2A Convertor with a `.env` file in the project root.

```bash
# .env
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=your-token
LOG_LEVEL=INFO
```

## LLM Providers

### AWS Bedrock (Recommended)

```bash
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=your-token
AWS_REGION=eu-west-2
```

Get token: AWS Console → Bedrock → Model Access

### OpenAI

```bash
LLM_MODEL=openai:gpt-4o
OPENAI_API_KEY=sk-your-key
```

Get key: https://platform.openai.com/api-keys

### Google Vertex AI

```bash
LLM_MODEL=google_vertexai:gemini-2.0-flash-exp
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
```

### Local (Ollama)

```bash
LLM_MODEL=openai:llama3:8b
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=not-needed
```

Install: `curl -fsSL https://ollama.com/install.sh | sh && ollama pull llama3:8b`

## Logging

```bash
LOG_LEVEL=INFO          # INFO, DEBUG, WARNING, ERROR
DEBUG_ALL=false         # Set true for verbose library logging
LANGCHAIN_DEBUG=false   # Set true to see agent reasoning
```

## Migration Behavior

### MAX_EXPORT_ATTEMPTS

Number of ansible-lint retry attempts during migration.

**Range**: 1-10
**Default**: 5

```bash
# Quick iteration (fewer retries)
MAX_EXPORT_ATTEMPTS=3

# Thorough validation (more retries)
MAX_EXPORT_ATTEMPTS=10
```

**Impact**:
- Higher = Better quality, longer runtime
- Lower = Faster, may have lint warnings

### RECURSION_LIMIT

Maximum LangGraph state transitions.

**Range**: 50-200
**Default**: 100

```bash
# Simple cookbooks
RECURSION_LIMIT=50

# Complex multi-file analysis
RECURSION_LIMIT=200
```

**When to Increase**:
- Large cookbooks (50+ files)
- Deep dependency trees
- Complex analysis workflows

### MAX_TOKENS

LLM response token limit.

**Range**: 1024-32768
**Default**: 8192

```bash
# Small recipes
MAX_TOKENS=4096

# Large complex recipes
MAX_TOKENS=16384
```

**Trade-offs**:
- Higher = Can handle larger files, higher cost
- Lower = Faster, cheaper, may truncate

### TEMPERATURE

LLM randomness/creativity.

**Range**: 0.0-1.0
**Default**: 0.1

```bash
# Deterministic (recommended for migrations)
TEMPERATURE=0.1

# More creative (not recommended)
TEMPERATURE=0.7
```

**Recommendation**: Keep at 0.1 for consistent, reproducible migrations.

### REASONING_EFFORT

Enable reasoning models with extended thinking.

**Values**: `low`, `medium`, `high`, (empty for standard)
**Default**: (empty)

```bash
# Use reasoning model
LLM_MODEL=openai:o1-preview
REASONING_EFFORT=high
```

**Use Cases**:
- Complex conditional logic
- Intricate dependency resolution
- Custom resource translations

**Trade-offs**:
- Much higher latency (30s-2min)
- Increased cost (10x)
- Better accuracy for complex scenarios

## AAP Integration (Optional)

Enable Ansible Automation Platform integration for collection discovery and deployment.

For the complete list of AAP environment variables, see [AAP Configuration](../configuration_options.html#ansible-automation-platform-configuration).

### Collection Discovery

When configured, the migrate phase queries your Private Automation Hub to discover reusable collections.

```bash
# Required for collection discovery
AAP_CONTROLLER_URL=https://aap.example.com
AAP_ORG_NAME=your-org
# Authentication choose OAuth token or Basic credentials
AAP_OAUTH_TOKEN=your-oauth-token           # OAuth token (recommended)

# Optional
AAP_GALAXY_REPOSITORY=published  # published, staging, or community
AAP_VERIFY_SSL=true
AAP_CA_BUNDLE=/path/to/ca-bundle.crt  # For self-signed certs
```

**How it works:**
1. Discovery agent searches Private Hub for relevant collections
2. Found collections are added to `requirements.yml`
3. Write agent uses collections in generated Ansible code

See [Human Checkpoints](../concepts/human-checkpoints.html#aap-collection-discovery-optional) for review guidance.

### AAP Project Sync

For publish phase AAP integration (creating projects in AAP Controller):

```bash
# Required
AAP_CONTROLLER_URL=https://aap.example.com
AAP_ORG_NAME=your-org
AAP_OAUTH_TOKEN=your-oauth-token  # Or use username/password

# Optional
AAP_PROJECT_NAME=my-project       # Inferred from repo if not set
AAP_SCM_CREDENTIAL_ID=1           # For private Git repos
AAP_API_PREFIX=/api/controller/v2
AAP_TIMEOUT_S=30.0
```

Get OAuth token: See [AAP Token Authentication](https://docs.redhat.com/en/documentation/red_hat_ansible_automation_platform/2.6/html/access_management_and_authentication/gw-token-based-authentication)

## Publishing Configurations

To publish a migrated cookbook, now Ansible Role, to Github, the github token is required.

```bash
GITHUB_TOKEN=<ghp_...>
```

## Complete Configuration Examples

### Production (AWS Bedrock)

```bash
# .env
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=ABSKQmVkcm9j...
AWS_REGION=eu-west-2
LOG_LEVEL=INFO
DEBUG_ALL=false
MAX_EXPORT_ATTEMPTS=5
RECURSION_LIMIT=100
MAX_TOKENS=8192
TEMPERATURE=0.1
GITHUB_TOKEN=<ghp_...>

# AAP Integration (optional)
AAP_CONTROLLER_URL=https://aap.example.com
AAP_ORG_NAME=my-org
AAP_OAUTH_TOKEN=your-oauth-token
AAP_GALAXY_REPOSITORY=published
```

### Development (OpenAI)

```bash
# .env
LLM_MODEL=openai:gpt-4o
OPENAI_API_KEY=sk-...
LOG_LEVEL=DEBUG
DEBUG_ALL=false
LANGCHAIN_DEBUG=true
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls_...
LANGCHAIN_PROJECT=x2a-dev
MAX_EXPORT_ATTEMPTS=3
MAX_TOKENS=8192
TEMPERATURE=0.1
GITHUB_TOKEN=<ghp_...>
```

### Air-Gapped (Local Ollama)

```bash
# .env
LLM_MODEL=openai:llama3:70b
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_API_KEY=not-needed
LOG_LEVEL=INFO
DEBUG_ALL=false
MAX_EXPORT_ATTEMPTS=7
RECURSION_LIMIT=150
MAX_TOKENS=16384
TEMPERATURE=0.1
```

## Environment Variable Reference

For the complete list of all environment variables, see [Configuration Options](../configuration_options.html).

## Security Best Practices

### 1. Never Commit .env Files

```bash
# Add to .gitignore
echo ".env" >> .gitignore
```

### 2. Use Secrets Management

**AWS Secrets Manager**:
```bash
export AWS_BEARER_TOKEN_BEDROCK=$(aws secretsmanager get-secret-value \
  --secret-id x2a/bedrock-token \
  --query SecretString \
  --output text)
```

**Kubernetes Secrets**:
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: x2a-config
type: Opaque
data:
  llm-model: Y2xhdWRlLTMtNS1zb25uZXQ=  # base64
  aws-token: QUJTSy4uLg==
```

### 3. Restrict File Permissions

```bash
chmod 600 .env
```

### 4. Use Environment-Specific Configs

```bash
# .env.production
LLM_MODEL=claude-3-5-sonnet-20241022
AWS_BEARER_TOKEN_BEDROCK=prod-token

# .env.development
LLM_MODEL=openai:gpt-3.5-turbo
OPENAI_API_KEY=dev-key

# Load appropriate file
docker run --env-file .env.production x2a-convertor ...
```

## Troubleshooting

### LLM Connection Fails

**Symptom**: `Error: Unable to connect to LLM provider`

**Solutions**:
```bash
# Verify token
echo $AWS_BEARER_TOKEN_BEDROCK

# Test connectivity
curl https://bedrock-runtime.eu-west-2.amazonaws.com/

# Enable debug
DEBUG_ALL=true uv run app.py init ...
```

### Rate Limiting

**Symptom**: `429 Too Many Requests`

**Solutions**:
- Reduce parallelism
- Add delays between requests
- Use local models
- Upgrade API tier

### Invalid Model Name

**Symptom**: `Model 'xyz' not found`

**Solutions**:
```bash
# Check model format
LLM_MODEL=claude-3-5-sonnet-20241022  # Correct
LLM_MODEL=claude-3.5-sonnet           # Incorrect

# Verify provider prefix
LLM_MODEL=openai:gpt-4o               # Correct for OpenAI
LLM_MODEL=gpt-4o                      # Incorrect
```

## Next Steps

- [Installation](installation.html): Install X2A Convertor
- [Docker Usage](docker-usage.html): Run with Docker

