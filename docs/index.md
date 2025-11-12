---
layout: default
title: Home
nav_order: 1
---

# X2A Convertor Documentation

AI-powered infrastructure migration tool that converts Chef, Puppet, and Salt configurations to Ansible playbooks.

## Quick Navigation

### [Project Goals](goals.html)
Understand the enterprise value proposition and migration benefits.

### [Concepts](concepts/)
Deep-dive into the architecture, agents, and AI-powered workflow.

### [Getting Started](getting-started/)
Installation, configuration, and hands-on migration guides.

---

## What is X2A Convertor?

X2A Convertor is an enterprise-grade tool designed to automate the migration of legacy infrastructure-as-code (Chef, Puppet, Salt) to modern Ansible playbooks. Built specifically for organizations managing complex infrastructure at scale, it reduces migration time from weeks to hours while maintaining quality through AI-validated output and human checkpoints.

## Key Features

- **AI-Powered Analysis**: LangGraph-based agents analyze source configurations
- **Human-in-the-Loop**: Review checkpoints at each migration phase
- **Automated Validation**: ansible-lint integration with auto-retry
- **Incremental Migration**: Module-by-module approach reduces risk
- **Enterprise Ready**: Docker deployment, AWS Bedrock support, audit trails

## Migration Workflow

```mermaid
flowchart LR
    Chef[Chef/Puppet/Salt] --> Init[1. Init]
    Init --> Review1[Review Plan]
    Review1 --> Analyze[2. Analyze]
    Analyze --> Review2[Review Spec]
    Review2 --> Migrate[3. Migrate]
    Migrate --> Review3[Review Output]
    Review3 --> Validate[4. Validate]
    Validate --> Ansible[Production Ansible]

    style Review1 fill:#fff3e0
    style Review2 fill:#fff3e0
    style Review3 fill:#fff3e0
```

Each step includes a human checkpoint for quality assurance and decision-making.
