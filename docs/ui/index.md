---
layout: default
title: UI Documentation
has_children: true
nav_order: 6
---

# X2Ansible UI Documentation

The X2Ansible Backstage Plugin provides a web-based user interface for managing migration projects, running conversion jobs, and integrating with Ansible Automation Platform.

## Overview

The UI is built as a Backstage plugin workspace, providing:

- **Project Management**: Create, view, and manage migration projects
- **Job Orchestration**: Run and monitor migration jobs via Kubernetes
- **Source Control Integration**: Connect to GitHub, GitLab, and Bitbucket repositories
- **Ansible Automation Platform**: Deploy migrated playbooks to AAP

## Documentation Sections

### [Installation]({% link ui/installation.md %})
Deployment guide for OpenShift and Kubernetes environments.

### [Installation (vanilla Backstage)]({% link ui/installation-backstage.md %})
Add published `@red-hat-developer-hub/*` X2A packages to a freshly generated `create-app` Backstage instance.

### [Authentication]({% link ui/authentication.md %})
OAuth setup, providers, and user management.

### [Authorization]({% link ui/authorization.md %})
RBAC permissions and access control policies.

### [MCP tools]({% link ui/mcp-server.md %})
Connect assistants to Conversion Hub via RBAC-aware MCP tools.

### [CSV Bulk Import]({% link ui/csv-bulk-import.md %})
Create multiple conversion projects at once by uploading a CSV file.

### [API Reference]({% link ui/api-reference.md %})
Swagger UI for exploring the OpenAPI specification.

## Quick Links

- **Backend Plugin**: RESTful API and Kubernetes job orchestration (see ooo/x2a/plugins/x2a-backend/)
- **Source Repository**: [X2Ansible Convertor](https://github.com/x2ansible/x2a-convertor)

## Architecture

```mermaid
flowchart TB
    UI[Backstage UI] --> Backend[X2A Backend Plugin]
    Backend --> K8s[Kubernetes Jobs]
    Backend --> DB[(Database)]
    Backend --> SCM[Git Providers]
    Backend --> AAP[Ansible Automation Platform]

    K8s --> Convertor[X2A Convertor Container]
    Convertor --> LLM[LLM Provider]

    style UI fill:#e3f2fd
    style Backend fill:#e8f5e9
    style Convertor fill:#fff3e0
```

The UI communicates with the backend plugin via REST API. The backend orchestrates Kubernetes jobs that run the X2A convertor container, which uses LLM providers to perform the actual migration analysis and code generation.

## Job Execution Flow

The following diagram illustrates how a Job runs on each phase. When a user triggers any phase (Init, Analyze, Migrate, or Publish), this is the sequence of operations that the system executes end-to-end.

{% raw %}

```mermaid
sequenceDiagram
  actor Dev as Developer
  participant UI as X2A Portal
  participant GitHub as GitHub / GitLab
  participant API as X2A Backend
  participant K8s as Kubernetes
  participant Pod as Migration Engine
  participant Source as Source Repo
  participant Target as Target Repo
  participant LLM as AI / LLM

  Dev->>UI: Click "Init Project"
  Dev->>UI: Confirm initialization

  rect rgb(227, 242, 253)
    Note over UI,GitHub: Secure Token Acquisition
    UI->>GitHub: OAuth authorization request
    GitHub-->>UI: Access token (source repo)
    UI->>GitHub: OAuth authorization request
    GitHub-->>UI: Access token (target repo)
  end

  UI->>API: Start initialization
  API->>API: Validate user permissions

  rect rgb(232, 245, 233)
    Note over API,K8s: Launch Migration Job
    API->>K8s: Create Kubernetes Job
    API->>K8s: Inject credentials securely
    K8s-->>API: Job scheduled
  end

  API-->>UI: Job started
  UI->>UI: Polling for progress...

  rect rgb(255, 243, 224)
    Note over Pod,LLM: AI-Powered Analysis
    K8s->>Pod: Start migration engine
    Pod->>Source: Clone source repository
    Pod->>Pod: Scan project structure
    Pod->>LLM: Analyze codebase
    LLM-->>Pod: Migration plan + modules discovered
  end

  rect rgb(243, 229, 245)
    Note over Pod,Target: Push Results
    Pod->>Target: Push migration plan to target repo
    Target-->>Pod: Commit confirmed
  end

  Pod->>API: Report results + artifacts

  rect rgb(255, 249, 196)
    Note over API,API: Process Results
    API->>API: Register discovered modules
    API->>API: Store migration plan
  end

  UI->>API: Poll status
  API-->>UI: Initialization complete

  UI->>Dev: Display discovered modules
  Note over Dev: Ready to Analyze, Migrate, and Publish each module
```

{% endraw %}
