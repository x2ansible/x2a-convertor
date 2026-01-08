# X2A Convertor

**AI-powered Chef-to-Ansible migration tool that reduces migration time**

## What It Does

Converts legacy Chef, Puppet, Salt infrastructure code to modern Ansible playbooks with intelligent analysis, automatic validation, and zero manual translation.

```mermaid
flowchart LR
    subgraph Input["📦 Chef Infrastructure"]
        Chef[Cookbooks<br/>Recipes<br/>Templates]
    end

    subgraph Tool["🤖 X2Ansible"]
        P1["1️⃣ Plan"]
        P2["2️⃣ Analyze"]
        P3["3️⃣ Migrate"]
        P1 --> P2 --> P3
    end

    subgraph Output["✅ Production-Ready Ansible"]
        Ansible[Roles<br/>Playbooks<br/>Validated]
    end

    Chef --> Tool --> Ansible

    style Input fill:#ffebee
    style Tool fill:#e3f2fd
    style Output fill:#e8f5e9
```

## Key Benefits

- **Automated Migration**: AI agents handle code conversion, not humans
- **Risk Reduction**: Incremental module-by-module migration approach
- **Quality Assurance**: Built-in ansible-lint validation with auto-retry (up to 5 attempts)
- **Maintainable Output**: Clean, idiomatic Ansible code following best practices

## How It Works

| Phase          | What It Does                                                    | Output                                                  | Time    |
| -------------- | --------------------------------------------------------------- | ------------------------------------------------------- | ------- |
| **1️⃣ Init**    | Scans entire Chef repo, identifies cookbooks, maps dependencies | Strategic migration plan (`migration-plan.md`)          | ~5 min  |
| **2️⃣ Analyze** | Deep-dive analysis of specific cookbook/module                  | Detailed conversion spec (`migration-plan-<module>.md`) | ~10 min |
| **3️⃣ Migrate** | Converts Chef code to Ansible with validation                   | Production-ready Ansible role                           | ~15 min |

**Total time per module: ~30 minutes** (vs. days/weeks of manual conversion)

## Quick Start

```bash
# 1. Plan the migration
uv run app.py init --source-dir ./chef-repo "Migrate to Ansible"

# 2. Analyze a specific cookbook
uv run app.py analyze --source-dir ./chef-repo "Analyze nginx-multisite"

# 3. Generate Ansible code
uv run app.py migrate --source-dir ./chef-repo \
  --source-technology Chef \
  --high-level-migration-plan migration-plan.md \
  --module-migration-plan migration-plan-nginx-multisite.md \
  "Convert nginx-multisite"
```

---

## Technical Details

<details>
<summary><b>Click to expand detailed architecture</b></summary>

### Agent Architecture

```mermaid
flowchart LR
    %% The render order is reversed on the rendering, this is why I started with migrate

    subgraph Migrate["Migrate & Validation Agent"]
        MigrateAgent["Migrate AGENT<br/>Create Ansible playbook output"]
    end

    subgraph MigrateTools["Migrate Tools"]
        AnsibleMigrateer["ANSIBLE Migrate Agent<br/>MCP with collections<br/>+ Ansible lint"]
    end

    MigrateAgent <-.-> AnsibleMigrateer

    subgraph ChefTools["Chef Tools"]
        ChefT["LIST/READ/GREP<br/>+ TREESITTER<br/>CHEF-COMMANDS"]
    end

    subgraph PuppetTools["Puppet Tools"]
        PuppetT["LIST/READ/GREP<br/>+ TREESITTER<br/>PUPPET-COMMANDS"]
    end

    subgraph SaltTools["Salt Tools"]
        SaltT["LIST/READ/GREP<br/>+ TREESITTER<br/>SALT-COMMANDS"]
    end

    subgraph Input["Input Analysis Agents"]
        Chef["CHEF AGENT"]
        Puppet["PUPPET AGENT"]
        Salt["SALT AGENT"]
    end

    subgraph Planning["Planning Agent"]
        InputAgent["INPUT AGENT<br/>Creates migration plan:<br/>- MIGRATION-MODULE-PLAN.md"]
    end

    Chef <-.-> ChefT
    Puppet <-.-> PuppetT
    Salt <-.-> SaltT
    InputAgent <--> Chef
    InputAgent <--> Puppet
    InputAgent <--> Salt

    subgraph InitTools["Init Tools"]
        InitT["FileSearch<br/>ListDirectory<br/>ReadFile<br/>WriteFile"]
    end

    subgraph Init["Init Agent"]
        InitAgent["INIT AGENT<br/>Creates:<br/>- MIGRATION-PLAN.md"]
    end
    InitAgent <-.-> InitT

    style Init fill:#e3f2fd
    style Input fill:#e8f5e9
    style Planning fill:#e3f2fd
    style Migrate fill:#fff3e0
    style InitTools fill:#f5f5f5
    style ChefTools fill:#f5f5f5
    style PuppetTools fill:#f5f5f5
    style SaltTools fill:#f5f5f5
    style MigrateTools fill:#f5f5f5
```

### Technical Workflow

```mermaid
flowchart TB
    Start([Chef Repository]) --> Init

    subgraph Init["1️⃣ INIT: Strategic Planning"]
        I1["Scan Repository"] --> I2["Identify Cookbooks"] --> I3["Map Dependencies"] --> I4["migration-plan.md"]
    end

    Init --> Analyze

    subgraph Analyze["2️⃣ ANALYZE: Deep-Dive"]
        A1["Select Module"] --> A2["Parse Recipes/Templates"] --> A3["Analyze Dependencies"] --> A4["migration-plan-MODULE.md"]
    end

    Analyze --> Migrate

    subgraph Migrate["3️⃣ MIGRATE: Code Generation"]
        M1["Read Plans"] --> M2["Convert .erb → .j2"] --> M3["Convert .rb → .yml"] --> M4["Validate"] --> M5["Ansible Role"]
    end

    Migrate --> Output["Production-Ready Ansible"]

    style Init fill:#e3f2fd
    style Analyze fill:#fff3e0
    style Migrate fill:#e8f5e9
```

### What Gets Converted

| Chef Artifact      | Ansible Equivalent             |
| ------------------ | ------------------------------ |
| Recipes (`.rb`)    | Tasks (`.yml`)                 |
| Templates (`.erb`) | Templates (`.j2`)              |
| Attributes         | Defaults (`defaults/main.yml`) |
| Resources          | Modules + Tasks                |
| Files              | Files (copied)                 |

</details>

## Development

#### AWS Bedrock Authentication

AWS Bedrock supports two authentication methods (use one, not both):

**Option 1: IAM Credentials (Recommended)**

```bash
export LLM_MODEL="us.anthropic.claude-3-7-sonnet-20250219-v1:0"
export AWS_REGION="us-east-2"
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
```

**Option 2: Bearer Token (API Key)**

```bash
export LLM_MODEL="us.anthropic.claude-3-7-sonnet-20250219-v1:0"
export AWS_REGION="us-east-2"
export AWS_BEARER_TOKEN_BEDROCK="ABSKQmVkcm9j..."
```

**Important:** Do NOT set `AWS_BEARER_TOKEN_BEDROCK` if using IAM credentials, as bearer tokens take precedence.

#### AAP (Ansible Automation Platform) Integration

AAP integration is optional and used for publishing migrated roles. Two authentication methods are supported:

**Option 1: OAuth Token (Recommended)**

```bash
export AAP_CONTROLLER_URL="https://aap.example.com"
export AAP_ORG_NAME="Default"
export AAP_OAUTH_TOKEN="your-oauth-token"
```

**Option 2: Username/Password**

```bash
export AAP_CONTROLLER_URL="https://aap.example.com"
export AAP_ORG_NAME="Default"
export AAP_USERNAME="admin"
export AAP_PASSWORD="your-password"
```

**For private PKI or self-signed certificates:**

```bash
export AAP_CA_BUNDLE="/path/to/ca-bundle.crt"
# Or disable SSL verification (not recommended for production)
export AAP_VERIFY_SSL="false"
```

Optionally, a `.env` file with these settings for development purposes can be created.

### Development Commands

```bash
# Format code
make format
make check

# Checks
make ci-check

# Run application
uv run app.py
```

### Logging

The project uses a custom logging setup with structlog to ensure clean, consistent logging across the codebase.

#### Using Loggers

**Always use `get_logger()` instead of `logging.getLogger()`:**

```python
from src.utils.logging import get_logger

logger = get_logger(__name__)

logger.info("Migration started")
logger.debug("Processing file", file_path="/path/to/file")
```

**Ruff enforcement:** The project uses Ruff to automatically prevent incorrect logging usage:

```bash
# Check for logging violations
uv run ruff check --select TID .
```

If you accidentally use `logging.getLogger()`, Ruff will fail with:

```
TID251 `logging.getLogger` is banned: Use get_logger() from src.utils.logging instead of logging.getLogger()
```

#### Log Levels

| Setting           | x2convertor.\* logs | Third-party logs | Use Case                   |
| ----------------- | ------------------- | ---------------- | -------------------------- |
| Default           | INFO                | WARNING          | Normal operation           |
| `LOG_LEVEL=DEBUG` | DEBUG               | WARNING          | Debug your code only       |
| `DEBUG_ALL=true`  | DEBUG               | DEBUG            | Debug everything (verbose) |

**Examples:**

```bash
# Normal operation (INFO level for app, WARNING for libraries)
uv run app.py init --source-dir ./chef-repo "Migrate to Ansible"

# Debug your application code only
LOG_LEVEL=DEBUG uv run app.py migrate ...

# Debug everything including HTTP requests, LangChain internals
DEBUG_ALL=true uv run app.py analyze ...
```

#### Best Practices

1. Use appropriate log levels:

   - `logger.debug()` - Detailed diagnostic info
   - `logger.info()` - General informational messages
   - `logger.warning()` - Warning messages
   - `logger.error()` - Error messages

2. Add context with structured logging:

   ```python
   logger.info("File processed", file_path=path, line_count=100)
   ```

3. Never use `logging.getLogger()` directly - use `get_logger()` instead
