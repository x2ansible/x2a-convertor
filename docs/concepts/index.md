---
layout: default
title: Concepts
nav_order: 3
has_children: true
---

# Concepts

Understanding the architecture, agents, and workflow of X2A Convertor.

## Overview

X2A Convertor uses a multi-agent AI architecture built on LangGraph to analyze legacy infrastructure code and generate modern Ansible playbooks. The system is designed around two primary agent types:

- **Input Agents (Analysis)**: Understand and document source configurations
- **Export Agents (Migration)**: Generate and validate target Ansible code

## Topics

### [Architecture]({% link concepts/architecture.md %})
Complete system architecture with component diagrams and data flow.

### [Workflow]({% link concepts/workflow.md %})
End-to-end migration process from initialization through publishing to production.

### [Human Checkpoints]({% link concepts/human-checkpoints.md %})
Review points and decision gates throughout the migration lifecycle.

### [Input Agents]({% link concepts/input-agents.md %})
Chef, Puppet, and Salt analysis agents that parse and understand source code.

### [Export Agents]({% link concepts/export-agents.md %})
Ansible migration agents that generate production-ready playbooks and GitOps deployments.