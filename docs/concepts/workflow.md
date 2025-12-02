---
layout: default
title: Workflow
parent: Concepts
nav_order: 2
---

## Table of contents
{: .no_toc .text-delta }

<style>
.toc-h3-only ul li ul{
    display: none;
}
</style>

* TOC
{:toc .toc-h3-only}

# Migration Workflow

Complete end-to-end process for migrating infrastructure code from Chef/Puppet/Salt to Ansible.

## Overview

X2A Convertor follows a four-phase workflow with human review checkpoints at each stage:

{% raw %}

```mermaid
flowchart TB
    Start([Chef Repository]) --> P1

    subgraph P1["Phase 1: Init"]
        I1[Scan Repository]
        I2[Identify Modules]
        I3[Map Dependencies]
        I4[Generate Plan]
        I1 --> I2 --> I3 --> I4
    end

    P1 --> C1{{Checkpoint 1:<br/>Review Plan}}

    C1 -->|Approve| P2
    C1 -->|Modify| Req1[Adjust Requirements]
    Req1 --> P1

    subgraph P2["Phase 2: Analyze"]
        A1[Select Module]
        A2[Fetch Dependencies]
        A3[Parse Source Code]
        A4[Map Resources]
        A5[Generate Spec]
        A1 --> A2 --> A3 --> A4 --> A5
    end

    P2 --> C2{{Checkpoint 2:<br/>Review Spec}}

    C2 -->|Approve| P3
    C2 -->|Refine| Req2[Clarify Mappings]
    Req2 --> P2

    subgraph P3["Phase 3: Migrate"]
        M1[Load Plans]
        M2[Generate Ansible]
        M3[Convert Templates]
        M4[ansible-lint]
        M1 --> M2 --> M3 --> M4
        M4 -->|Fail| M5[Auto-Fix]
        M5 --> M2
        M5 -.->|Max 5 attempts| M4
    end

    P3 --> C3{{Checkpoint 3:<br/>Review Output}}

    C3 -->|Approve| P4
    C3 -->|Iterate| Req3[Manual Fixes]
    Req3 --> P3

    subgraph P4["Phase 4: Publish"]
        PB1[Create Deployment Structure]
        PB2[Generate GitOps Config]
        PB3[Create GitHub Repo]
        PB4[Push to Remote]
        PB1 --> PB2 --> PB3 --> PB4
    end

    P4 --> End([Production Deployment])

    style C1 fill:#fff3e0
    style C2 fill:#fff3e0
    style C3 fill:#fff3e0
    style P1 fill:#e3f2fd
    style P2 fill:#e8f5e9
    style P3 fill:#f3e5f5
    style P4 fill:#fce4ec
```

{% endraw %}

## Phase 1: Init

**Goal**: Create a strategic migration plan covering the entire repository.

### Command

```bash
uv run app.py init --source-dir ./chef-repo "Migrate to Ansible"
```

### Process

```mermaid
sequenceDiagram
    participant User
    participant Init as Init Agent
    participant FS as File System
    participant LLM

    User->>Init: Execute init command
    Init->>FS: Scan directory structure
    FS-->>Init: File tree
    Init->>FS: Read metadata.rb, Berksfile
    FS-->>Init: Cookbook metadata
    Init->>LLM: Analyze repository structure
    LLM-->>Init: Strategic recommendations
    Init->>FS: Write migration-plan.md
    Init-->>User: High-level plan ready
```

### Outputs

**File**: `migration-plan.md`

Contains:

- Repository structure overview
- List of all identified modules/cookbooks
- Dependency graph
- Recommended migration order
- Estimated complexity per module

### What to Review

- [ ] All cookbooks correctly identified
- [ ] Dependency relationships accurate
- [ ] Migration priority order makes sense
- [ ] External dependencies noted
- [ ] Complexity estimates reasonable

## Phase 2: Analyze

**Goal**: Create a detailed migration specification for a specific module.

### Command

```bash
uv run app.py analyze --source-dir ./chef-repo "Analyze nginx-multisite cookbook"
```

### Process

```mermaid
stateDiagram-v2
    [*] --> SelectModule
    SelectModule --> FetchDependencies
    FetchDependencies --> ParseSource
    ParseSource --> WriteReport
    WriteReport --> ValidateFiles
    ValidateFiles --> CleanupSpec
    CleanupSpec --> [*]

    note right of FetchDependencies
        Downloads external cookbooks
        via Chef CLI (if needed)
    end note

    note right of ParseSource
        Tree-sitter parses Ruby
        recipes and attributes
    end note

    note right of WriteReport
        AI generates initial
        resource mappings
    end note

    note right of ValidateFiles
        Reviews each file for
        correct mapping
    end note

    note right of CleanupSpec
        Refines and finalizes
        migration specification
    end note
```

### Outputs

**File**: `migration-plan-<module-name>.md`

Contains:

- Module-specific overview
- File-by-file mapping
- Template list
- Variable mapping (attributes → defaults)
- Resource translation table
- Handler and notification mappings

### What to Review

- [ ] All source files mapped
- [ ] Template variable conversions correct
- [ ] Resource mappings preserve logic
- [ ] Dependencies properly handled
- [ ] Edge cases identified

## Phase 3: Migrate

**Goal**: Generate production-ready Ansible code.

### Command

```bash
uv run app.py migrate \
  --source-dir ./chef-repo \
  --source-technology Chef \
  --high-level-migration-plan migration-plan.md \
  --module-migration-plan migration-plan-nginx-multisite.md \
  "Convert nginx-multisite cookbook"
```

### Process

```mermaid
flowchart TB
    Start([Start Migration]) --> Read[Read Migration Plans]
    Read --> Meta[Extract Source Metadata]
    Meta --> Choose{Choose<br/>Strategy}

    Choose -->|Chef| ChefMigrate[Chef Migration Agent]
    Choose -->|Puppet| PuppetMigrate[Puppet Migration Agent]
    Choose -->|Salt| SaltMigrate[Salt Migration Agent]

    ChefMigrate --> Generate[Generate Ansible Code]
    PuppetMigrate --> Generate
    SaltMigrate --> Generate

    Generate --> Lint{ansible-lint}

    Lint -->|Pass| Output[Write to ansible/]
    Lint -->|Fail| Count{Attempt<br/>< 5?}

    Count -->|Yes| Fix[AI Auto-Fix]
    Fix --> Generate
    Count -->|No| Output

    Output --> Done([Migration Complete])

    style Lint fill:#fff3e0
    style Count fill:#ffebee
    style Done fill:#e8f5e9
```

### Validation Loop

The migration agent automatically retries up to 5 times if ansible-lint fails:

```mermaid
sequenceDiagram
    participant Agent as Migration Agent
    participant Gen as Code Generator
    participant Lint as ansible-lint
    participant LLM

    Agent->>Gen: Generate Ansible playbook
    Gen-->>Agent: Generated code
    Agent->>Lint: Run validation
    Lint-->>Agent: Errors found

    loop Until pass or max attempts
        Agent->>LLM: Fix these lint errors
        LLM-->>Agent: Corrected code
        Agent->>Lint: Re-validate
        Lint-->>Agent: Result
    end

    Agent-->>Agent: Write final output
```

### Outputs

**Directory**: `ansible/roles/<module-name>/`

Structure:

```
ansible/nginx-multisite/
├── defaults/
│   └── main.yml          # Converted attributes
├── files/
│   └── ...               # Static files copied
├── handlers/
│   └── main.yml          # Converted notifyactions
├── tasks/
│   └── main.yml          # Converted recipes
├── templates/
│   └── nginx.conf.j2     # Converted .erb templates
└── meta/
    └── main.yml          # Dependencies
```

### What to Review

- [ ] Task order preserves Chef recipe logic
- [ ] Templates correctly converted to Jinja2
- [ ] Variables match expected defaults
- [ ] Handlers triggered appropriately
- [ ] No ansible-lint errors
- [ ] Idempotency maintained

## Phase 4: Publish

**Goal**: Deploy migrated Ansible role to a GitOps repository for production use.

### Process

The publisher automates GitOps deployment by creating a production-ready repository structure:

```mermaid
flowchart TB
    Start([Migrated Role]) --> Create[Create Deployment Structure]
    Create --> Copy[Copy Role to deployments/]
    Copy --> Gen1[Generate Playbook]
    Gen1 --> Gen2[Generate Job Template]
    Gen2 --> Gen3[Generate GitHub Actions]
    Gen3 --> Verify[Verify All Files]
    Verify --> Repo{GitHub<br/>Repo Exists?}

    Repo -->|No| CreateRepo[Create role-gitops]
    Repo -->|Yes| CheckBranch{Branch<br/>Exists?}

    CreateRepo --> Commit[Commit Changes]
    CheckBranch -->|No| Commit
    CheckBranch -->|Yes| Error[Fail: Branch Exists]

    Commit --> Push[Push to Remote]
    Push --> Summary[Display Summary]

    Summary --> Done([GitOps Deployment Ready])

    style Repo fill:#fff3e0
    style CheckBranch fill:#fff3e0
    style Error fill:#ffebee
    style Done fill:#e8f5e9
```

### Deployment Structure

The publisher creates a complete GitOps repository at `<path>/ansible/deployments/{role}/`:

```
deployments/{role}/
├── roles/
│   └── {role}/                  # Copied role source
├── playbooks/
│   └── {role}_deploy.yml        # Entry point playbook
├── aap-config/job-templates/
│   └── {role}_deploy.yaml       # Ansible Automation Platform config
└── .github/workflows/
    └── deploy.yml               # CI/CD pipeline
```

### Key Features

- **Template-based generation**: Uses Jinja2 templates for consistent output
- **Deterministic**: No LLM calls during generation for reproducible results
- **GitOps-ready**: Automatically creates GitHub repositories
- **Idempotent**: Handles existing repositories gracefully, fails on existing branches
- **Summary output**: Displays files created, credentials needed, and repository location

### What to Review

- [ ] Deployment structure created correctly
- [ ] Playbook references correct role
- [ ] Job template configuration valid for AAP
- [ ] GitHub Actions workflow configured properly
- [ ] Repository created and pushed successfully
- [ ] All credentials and execution instructions clear

## Parallel Workflows

For independent modules, run phases in parallel:

```mermaid
gantt
    title Parallel Migration (3 Modules)
    dateFormat X
    axisFormat %M min

    section Init
    Repo scan      :0, 5

    section Module A
    Analyze A      :5, 15
    Migrate A      :15, 30
    Publish A      :30, 35

    section Module B
    Analyze B      :5, 15
    Migrate B      :15, 30
    Publish B      :30, 35

    section Module C
    Analyze C      :5, 15
    Migrate C      :15, 30
    Publish C      :30, 35
```

This reduces total time from 120 minutes (sequential) to 35 minutes (parallel).

## Error Handling

### Common Failure Points

1. **Init fails to identify modules**

   - TBC

2. **Analyze cannot resolve dependencies**

   - TBC

3. **Migrate exceeds retry limit**

   - TBC

4. **Publish fails to create repository**
   - TBC

### Recovery Strategies

Each phase is idempotent and can be re-run:

```bash
# Re-run init with refined requirements
uv run app.py init --source-dir ./chef-repo "Focus on core cookbooks only"

# Re-run analyze with additional context
uv run app.py analyze --source-dir ./chef-repo "Analyze nginx with focus on SSL configuration"

# Re-run migrate after manual spec adjustments
uv run app.py migrate ... "Regenerate with updated specification"
```
