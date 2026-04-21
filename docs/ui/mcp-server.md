---
layout: default
title: MCP tools
parent: UI Documentation
nav_order: 6
---

# MCP tools

Red Hat Developer Hub exposes a [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server. When the X2A MCP extras plugin is enabled, your MCP client (for example Cursor, Continue, or another tool-aware assistant) can call X2A-specific tools in addition to any other Hub MCP tools you have installed.

## Support scope and prerequisites

MCP integration in Red Hat Developer Hub is described as **Developer Preview** in the product documentation. Confirm that your assistant or model supports **tool calling** before relying on MCP workflows. For support scope, limitations, and general Hub MCP setup, see [Interacting with Model Context Protocol tools for Red Hat Developer Hub 1.9](https://docs.redhat.com/en/documentation/red_hat_developer_hub/1.9/html-single/interacting_with_model_context_protocol_tools_for_red_hat_developer_hub/index).

Before connecting a client, your cluster administrators must enable the MCP server plugin, the X2A MCP extras plugin, and related configuration on the Hub instance. Follow [Installation — MCP tools (optional)]({% link ui/installation.md %}#mcp-tools-optional).

The Hub’s public URL and `backend.baseUrl` must match, otherwise OAuth, consent pages, or callbacks can fail. Administrators configure that in the same installation flow.

## How to connect your MCP client

Use your Developer Hub host in place of `<my_developer_hub_domain>`.

| Transport | URL |
|-----------|-----|
| Streamable (recommended where supported) | `https://<my_developer_hub_domain>/api/mcp-actions/v1` |
| SSE (legacy, for clients without streamable support) | `https://<my_developer_hub_domain>/api/mcp-actions/v1/sse` |

Red Hat’s guide includes ready-made examples for Cursor, Continue, and other clients (headers, `Authorization: Bearer`, and so on). See the [“Configuring MCP clients to access the RHDH server”](https://docs.redhat.com/en/documentation/red_hat_developer_hub/1.9/html-single/interacting_with_model_context_protocol_tools_for_red_hat_developer_hub/index#proc-configuring-mcp-clients-to-access-the-rhdh-server) section in the same document.

## Authentication

### Static access token

Many setups use a long-lived **Bearer** token configured on the Hub (`backend.auth.externalAccess`). The token is mapped to a Backstage **`subject`** (for example `mcp-clients`). That subject must be granted the same [Authorization]({% link ui/authorization.md %}) roles and policies as a human user would need for the same actions. If the subject has no `x2a` permissions, X2A tools will deny access.

### User-delegated access (optional, DCR)

Some workflows allow the MCP client to register dynamically and act **on behalf of a signed-in user** after the user approves access in the browser. That path uses OAuth2 Dynamic Client Registration (DCR) and a consent UI. On Red Hat Developer Hub 1.9, the X2A **DCR** frontend plugin serves consent under **`/oauth2/*`**. Enabling that plugin and the related `auth.experimentalDynamicClientRegistration` settings is part of [Installation — MCP tools (optional)]({% link ui/installation.md %}#mcp-tools-optional).

On **Red Hat Developer Hub 1.9**, DCR for MCP depends on a **newer `backstage-plugin-mcp-actions-backend`** than the baseline that appears in some older overlay tags. If your Hub still runs an older MCP actions backend build, DCR flows may not work reliably. Use **[static access token](#static-access-token)** authentication for MCP instead, or upgrade the MCP actions backend image to a version your platform team confirms supports DCR on 1.9 (see [Installation — MCP tools (optional)]({% link ui/installation.md %}#mcp-tools-optional)).

## X2A MCP tools

These tools mirror capabilities you already have in the Conversion Hub UI. Names and parameters are defined by the installed plugin version.

| Tool | Purpose | Typical inputs | What you get |
|------|---------|----------------|--------------|
| `x2a-list-projects` | List migration projects you are allowed to see | Pagination or filter fields as exposed by the tool | Projects with metadata and links into the Hub UI where applicable |
| `x2a-create-project` | Start a new migration project | Project fields aligned with the create-project flow (source/target repos, owner, and so on) | Created project identifiers and next-step hints (for example running initialization) |
| `x2a-trigger-next-phase` | Start or advance a pipeline phase (for example init, analyze, migrate, publish) for a module or project | Identifiers for the project or module and the phase to run | Job or status information; errors if prerequisites are missing |
| `x2a-list-modules` | List modules belonging to a project | `projectId` | Module names, paths, status, and deep links to module detail in the Hub UI |

**Repository access:** Creating projects or advancing phases often requires the same **Git provider access** as the web UI (OAuth tokens for source and target repositories). If the assistant runs as a static service principal, it may not be able to complete steps that need your personal SCM authorization. See [Authentication]({% link ui/authentication.md %}) for how users sign in to GitHub, GitLab, or Bitbucket in Hub.

**Tool descriptions:** The plugin can expose short descriptions and structured schemas so clients know how to call each tool. Your client’s tool list is the authoritative view for the exact parameter names on your deployment.

## Permissions

X2A MCP tools enforce the same RBAC rules as the REST API and UI. Read-heavy tools (such as listing projects or modules) require permission to view those resources, write or job-starting tools require appropriate create or update access. See [Authorization]({% link ui/authorization.md %}) for `x2a.admin` and `x2a.user` and how to assign them to users, groups, or the MCP service subject.

## Further reading

- [Installation — MCP tools (optional)]({% link ui/installation.md %}#mcp-tools-optional): dynamic plugins and `app-config` for operators
- [Interacting with Model Context Protocol tools for Red Hat Developer Hub 1.9](https://docs.redhat.com/en/documentation/red_hat_developer_hub/1.9/html-single/interacting_with_model_context_protocol_tools_for_red_hat_developer_hub/index): Hub-wide MCP behavior and client examples
- Optional background on the upstream plugin sources: [rhdh-plugins workspaces/x2a](https://github.com/redhat-developer/rhdh-plugins/tree/main/workspaces/x2a)
