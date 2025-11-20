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

| Variable | Type | Default | Required | Purpose |
|----------|------|---------|----------|---------|
| `LLM_MODEL` | string | - | Yes | Model selection |
| `AWS_BEARER_TOKEN_BEDROCK` | string | - | If using Bedrock | AWS Bedrock auth |
| `AWS_REGION` | string | `eu-west-2` | No | AWS region |
| `OPENAI_API_KEY` | string | - | If using OpenAI | OpenAI auth |
| `OPENAI_API_BASE` | string | - | If using local | Custom endpoint |
| `GOOGLE_APPLICATION_CREDENTIALS` | path | - | If using Vertex | GCP credentials |
| `LOG_LEVEL` | enum | `INFO` | No | App log level |
| `DEBUG_ALL` | boolean | `false` | No | Debug all libraries |
| `LANGCHAIN_DEBUG` | boolean | `false` | No | LangChain debug |
| `LANGCHAIN_TRACING_V2` | boolean | `false` | No | Enable tracing |
| `LANGCHAIN_API_KEY` | string | - | If tracing | LangSmith auth |
| `LANGCHAIN_PROJECT` | string | - | If tracing | Project name |
| `MAX_EXPORT_ATTEMPTS` | integer | `5` | No | Lint retry limit |
| `RECURSION_LIMIT` | integer | `100` | No | State transition limit |
| `MAX_TOKENS` | integer | `8192` | No | LLM token limit |
| `TEMPERATURE` | float | `0.1` | No | LLM randomness |
| `REASONING_EFFORT` | enum | - | No | Reasoning intensity |

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

