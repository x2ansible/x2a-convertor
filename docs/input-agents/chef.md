---
layout: default
title: Chef Agent
parent: Input Agents
nav_order: 1
---

# Chef Agent

**Location**: `src/inputs/chef.py`

The Chef Agent analyzes Chef cookbooks, recipes, templates, and attributes to create migration specifications for converting Chef infrastructure to Ansible.

## Workflow

```mermaid
stateDiagram-v2
    [*] --> FetchDependencies
    FetchDependencies --> WriteReport
    WriteReport --> CheckFiles
    CheckFiles --> CleanupSpec
    CleanupSpec --> [*]

    note right of FetchDependencies
        Resolves external cookbooks
        from Chef Supermarket using
        Berksfile
    end note

    note right of WriteReport
        Analyzes recipes, templates,
        attributes using Tree-sitter
        and LLM
    end note

    note right of CheckFiles
        Validates each file mapping
        with AI-powered review
    end note

    note right of CleanupSpec
        Refines and finalizes
        migration specification
    end note
```

## Stage 1: Fetch Dependencies

**Goal**: Resolve and download external cookbook dependencies

```bash
# Executed internally by agent
berks install
berks vendor /tmp/cookbooks
```

**Process**:
1. Read `Berksfile` or `metadata.rb`
2. Download dependencies from Chef Supermarket
3. Cache in temporary directory
4. Make available for analysis

**Tools Used**:
- Chef Workstation CLI (`berks`)
- File system operations

## Stage 2: Write Report

**Goal**: Generate initial migration specification using code analysis

**Process**:

```mermaid
flowchart TB
    Start[Start Analysis] --> List[List All Files]
    List --> Filter{File Type?}

    Filter -->|Recipe .rb| ParseRuby[Tree-sitter Parse]
    Filter -->|Template .erb| AnalyzeTemplate[Extract Variables]
    Filter -->|Attribute .rb| ParseAttributes[Extract Defaults]
    Filter -->|Other| Skip[Document Only]

    ParseRuby --> AIAnalysis[AI Analysis]
    AnalyzeTemplate --> AIAnalysis
    ParseAttributes --> AIAnalysis

    AIAnalysis --> Mapping[Generate Resource Mapping]
    Mapping --> Spec[Initial Specification]

    style ParseRuby fill:#e8f5e9
    style AIAnalysis fill:#e3f2fd
    style Spec fill:#fff3e0
```

**Tools Used**:
- **Tree-sitter**: Ruby AST parsing
- **LangChain LLM**: Semantic analysis
- **File operations**: Read recipes, templates, attributes

**Example Analysis**:

Input (Chef recipe):
```ruby
package 'nginx' do
  action :install
end

template '/etc/nginx/nginx.conf' do
  source 'nginx.conf.erb'
  variables(
    worker_processes: node['nginx']['workers'],
    worker_connections: node['nginx']['connections']
  )
  notifies :reload, 'service[nginx]'
end

service 'nginx' do
  action [:enable, :start]
end
```

Output (Specification excerpt):
```markdown
## Resource Mapping

| Chef Resource | Ansible Module | Notes |
|---------------|----------------|-------|
| package 'nginx' | package: name=nginx state=present | Direct mapping |
| template | template: src=nginx.conf.j2 dest=/etc/nginx/nginx.conf | ERB→Jinja2, extract variables |
| service 'nginx' | service: name=nginx state=started enabled=yes | Direct mapping |

## Variables

| Chef Attribute | Ansible Variable | Default |
|----------------|------------------|---------|
| node['nginx']['workers'] | nginx_worker_processes | auto |
| node['nginx']['connections'] | nginx_worker_connections | 1024 |

## Handlers

| Chef Notification | Ansible Handler | Trigger |
|-------------------|-----------------|---------|
| notifies :reload, 'service[nginx]' | Reload nginx | Template change |
```

## Stage 3: Check Files

**Goal**: Validate each file mapping for correctness

**Process**:

```mermaid
sequenceDiagram
    participant Agent
    participant LLM
    participant TreeSitter
    participant Spec

    loop For each file in cookbook
        Agent->>TreeSitter: Parse file
        TreeSitter-->>Agent: AST
        Agent->>LLM: Review mapping for this file
        LLM-->>Agent: Validation result
        Agent->>Spec: Update/refine mapping
    end

    Agent->>Spec: Mark validation complete
```

**Validation Checks**:
- All resources have Ansible equivalents
- Variables correctly extracted
- Dependencies properly identified
- Edge cases documented

## Stage 4: Cleanup Specification

**Goal**: Finalize and refine the migration specification

**Process**:
- Remove redundant entries
- Organize by logical sections
- Add implementation notes
- Flag complex conversions

**Output**: `migration-plan-<cookbook-name>.md`
