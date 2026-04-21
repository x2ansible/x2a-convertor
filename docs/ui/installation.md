---
layout: default
title: Installation
parent: UI Documentation
nav_order: 1
---

# Installation

This guide covers deploying the X2A Backstage plugin on OpenShift using Red Hat Developer Hub.

## Prerequisites

- OpenShift cluster access (CRC or production cluster)
- Cluster-admin rights (for operator installation)
- `oc` CLI tool installed and configured([documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/cli_tools/openshift-cli-oc#cli-getting-started))
- AWS credentials with access to Bedrock (for LLM functionality)
- Ansible Automation Platform instance (optional, for publishing roles)

## Quick Start

Deploy to any namespace with these simple commands:

```bash
# 1. Git clone current x2a-ansible code
git clone https://github.com/x2ansible/x2a-convertor/
cd x2a-convertor

# 2. Install operator (cluster-scoped, one-time installation)
oc apply -f deploy/operator.yaml

# 3. Create your namespace (or use existing)
oc create namespace <your-namespace>

# 4. Configure and apply secrets
cp deploy/secrets.yaml.template deploy/secrets.yaml

# 5. Deploy application resources
oc apply -n <your-namespace> -f deploy/app.yaml

# Edit deploy/secrets.yaml with your actual credentials
oc apply -n <your-namespace> -f deploy/secrets.yaml

# 6. Get the application URL
oc get route developer-hub -n <your-namespace> -o jsonpath='https://{.spec.host}{"\n"}'
```

## Installation Files

All deployment files are located in the `deploy/` directory at the root of the repository.

### 1. Operator Installation

**File:** `deploy/operator.yaml`

This installs the Red Hat Developer Hub operator. This is cluster-scoped and only needs to be installed once.

```yaml
{% include deploy/operator.yaml %}
```

Wait for the operator to be ready:

```bash
oc get csv -n openshift-operators | grep rhdh
```

### 2. Application Deployment

**File:** `deploy/app.yaml`

This file contains all the application resources: ConfigMaps, PersistentVolumeClaim, and the Backstage Custom Resource.

All resources intentionally omit the `namespace` field - specify your desired namespace using the `-n` flag when applying.

```yaml
{% include deploy/app.yaml %}
```

Apply to your namespace:

```bash
oc apply -n <your-namespace> -f deploy/app.yaml
```

### 3. Secrets Configuration

{: .warning }
**SECURITY WARNING: Never commit real credentials to git!**

**File:** `deploy/secrets.yaml.template`

This is a template file with placeholder values. You must create your own `secrets.yaml` from this template.

```yaml
{% include deploy/secrets.yaml.template %}
```

**Steps to configure secrets:**

1. Copy the template:
   ```bash
   cp deploy/secrets.yaml.template deploy/secrets.yaml
   ```

2. Edit with your credentials:
   ```bash
   vi deploy/secrets.yaml
   ```
   Replace all `REPLACE-WITH-YOUR-*` placeholders with your actual credentials.

3. Apply to your namespace:
   ```bash
   oc apply -n <your-namespace> -f deploy/secrets.yaml
   ```

4. Restart the Backstage pod to pick up the new secrets:
   ```bash
   oc delete pod -n <your-namespace> -l app.kubernetes.io/name=developer-hub
   ```

The `secrets.yaml` file is git-ignored and will not be committed to version control.

{: .note }
**For production environments**, consider using:
- External Secrets Operator (https://external-secrets.io/)
- HashiCorp Vault integration
- OpenShift Sealed Secrets
- Your organization's secret management solution

## Customization Options

The deployment files include clear comments (marked with `# CUSTOMIZATION:`) for common customization points.

### Namespace Selection

No file editing required - just specify the namespace when applying:

```bash
oc apply -n my-custom-namespace -f deploy/app.yaml
```

### Plugin Versions

To use different plugin versions, update the OCI image references in the `dynamic-plugins` ConfigMap section of `deploy/app.yaml`.

## MCP tools (optional)
{: #mcp-tools-optional}

See also: [MCP tools]({% link ui/mcp-server.md %}) (what each X2A tool does and how clients connect).

This section describes **additional** dynamic plugins and `app-config` fragments so LLM clients can call X2A through Red Hat Developer Hub’s MCP server. The default [`deploy/app.yaml`](https://github.com/x2ansible/x2a-convertor/blob/main/deploy/app.yaml) manifest may not include these entries. Merge them into your `dynamic-plugins` ConfigMap and `app-config-rhdh` ConfigMap as needed.

### 1. Dynamic plugins

Add packages under `data.dynamic-plugins.yaml` → `plugins` (alongside your existing X2A lines). Use **OCI tags that match your Hub / Backstage version**. Published tags on GitHub Container Registry often look like `bs_<backstageVersion>__<pluginVersion>`. Confirm current images in [rhdh-plugin-export-overlays packages](https://github.com/orgs/redhat-developer/packages?repo_name=rhdh-plugin-export-overlays).

Administrators typically install:

1. **`backstage-plugin-mcp-actions-backend`** - MCP server that exposes registered tool plugins. On **Red Hat Developer Hub 1.9**, **Dynamic Client Registration (DCR)** for MCP clients requires a **later** build of this plugin than some default `bs_*` overlay pairs ship. Without that upgrade, expect **static-token** MCP auth only (see `backend.auth.externalAccess` below). Sufficient version is `pr_2236__0.1.11` or `0.1.12` and later.
2. **`red-hat-developer-hub-backstage-plugin-x2a-mcp-extras`** - registers the X2A MCP tools (`x2a-list-projects`, `x2a-create-project`, `x2a-trigger-next-phase`, `x2a-list-modules`, subject to version).
3. **`red-hat-developer-hub-backstage-plugin-x2a-dcr`** (optional) - consent UI for OAuth2 Dynamic Client Registration on Hub 1.9–style deployments. Newer RHDH versions may replace this with upstream auth behavior.

Example shape (replace image tags with values appropriate for your release):

```yaml
plugins:
  - package: "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/backstage-plugin-mcp-actions-backend:bs_<BACKSTAGE>__<MCP_ACTIONS_VERSION>"
  - package: "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-x2a:bs_<BACKSTAGE>__<X2A_VERSION>"
  - package: "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-x2a-backend:bs_<BACKSTAGE>__<X2A_BACKEND_VERSION>"
  - package: "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-scaffolder-backend-module-x2a:bs_<BACKSTAGE>__<X2A_SCAFFOLDER_VERSION>"
  - package: "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-x2a-mcp-extras:bs_<BACKSTAGE>__<X2A_MCP_EXTRAS_VERSION>"
  - package: "oci://ghcr.io/redhat-developer/rhdh-plugin-export-overlays/red-hat-developer-hub-backstage-plugin-x2a-dcr:bs_<BACKSTAGE>__<X2A_DCR_VERSION>"
```

### 2. Application configuration (`app-config-rhdh.yaml`)

Merge the following into the YAML carried by your `app-config-rhdh` ConfigMap (same file you already use for `auth`, `x2a`, and so on). Adjust values and comments for your environment.

**How to merge keys:** Keep **one** root-level `backend:` map and merge every `backend.*` fragment into it (`baseUrl`, `actions`, `auth.externalAccess` for MCP static tokens, `cors`, and so on). Do not introduce a second top-level `backend:` key. **`mcpActions`**, **top-level `auth`** (sign-in providers and `experimentalDynamicClientRegistration`), and **`dynamicPlugins`** belong at the **root** of the same YAML document as **siblings** of `backend`, not nested under `backend:`.

**Backend URL, actions source, and static MCP token**

1. Under `backend.actions.pluginSources`, add **`x2a-mcp-extras`**, keeping any entries you already rely on.
2. **If static token auth is expected** (vs the DCR, optional):
  - Generate a long random bearer token (for example `node -p 'require("crypto").randomBytes(24).toString("base64")'`), store it in an OpenShift Secret, and supply it to the Hub backend the **same way** you inject other sensitive values into `app-config-rhdh` (for example `env` / `envFrom` on the Developer Hub deployment so the token is available as a pod environment variable, or the substitution mechanism your RHDH operator documents). In the snippet below, **`token: ${MCP_TOKEN}`** is a placeholder: the name after `${` must match the environment variable (or supported config substitution) the backend resolves when it loads this file, so the secret is never committed to git.
  - Choose a **`subject`** string for the static MCP principal (the example below uses `mcp-clients`). Grant that subject roles in your RBAC CSV so it can call the X2A tools you need - see [Authorization]({% link ui/authorization.md %}).

```yaml
backend:
  baseUrl: https://<my_developer_hub_domain>
  actions:
    pluginSources:
      - "x2a-mcp-extras"
  auth:
    externalAccess:
      - type: static
        options:
          token: ${MCP_TOKEN}
          subject: mcp-clients
```

**Optional: MCP client compatibility**

Some MCP clients mis-handle namespaced tool names. If tools fail to list or invoke:

```yaml
mcpActions:
  namespacedToolNames: false
```

**Optional: Dynamic Client Registration (DCR)** for user-delegated MCP clients (vs static token)

On RHDH **1.9**, enable DCR only if **`backstage-plugin-mcp-actions-backend`** is on a **newer** version that supports this flow on your Backstage line (`pr_2236__0.1.11` or `0.1.12` or later.). Otherwise keep **static-token** MCP authentication and skip DCR and the `x2a-dcr` consent route below.

Tighten `allowedRedirectUriPatterns` for production. Wildcards such as `https://*` are convenient in labs only.

```yaml
auth:
  experimentalDynamicClientRegistration:
    enabled: true
    allowedRedirectUriPatterns:
      - "cursor://*"
      - "https://<trusted-client-callback-host>/*"
```

**Optional: DCR consent route (X2A DCR frontend plugin)**

When the `x2a-dcr` dynamic plugin is installed, register its consent page:

```yaml
dynamicPlugins:
  frontend:
    red-hat-developer-hub.backstage-plugin-x2a-dcr:
      dynamicRoutes:
        - path: /oauth2/*
          importName: DcrConsentPage
```

Keep your existing `red-hat-developer-hub.backstage-plugin-x2a` block (icons, `/x2a/` route, scaffolder extensions) alongside this entry.

**Optional: CORS** - only if you use a local MCP inspector or another origin that must call the Hub API from the browser. Merge under `backend`:

```yaml
cors:
  origin:
    - "https://<my_developer_hub_domain>"
    - "http://localhost:6274"
  credentials: true
```

### 3. Apply changes and restart

After editing the ConfigMaps:

```bash
oc apply -n <your-namespace> -f deploy/app.yaml
oc delete pod -n <your-namespace> -l app.kubernetes.io/name=developer-hub
```

Watch the dynamic-plugin installer container logs if plugins fail to load. Users can then follow [MCP tools]({% link ui/mcp-server.md %}) to point their clients at `https://<my_developer_hub_domain>/api/mcp-actions/v1` (or the `/sse` URL) with the configured token or DCR flow.

## Access the Application

Get the Developer Hub URL:

```bash
oc get route developer-hub -n <your-namespace> -o jsonpath='https://{.spec.host}{"\n"}'
```

Open the URL in your browser and navigate to the X2A menu item to start using the migration tool.

## Troubleshooting

### Check operator installation

```bash
oc get csv -n openshift-operators | grep rhdh
oc get pods -n openshift-operators
```

### Check Backstage deployment

```bash
oc get backstage -n <your-namespace>
oc get pods -n <your-namespace>
oc logs -n <your-namespace> deployment/backstage-developer-hub
```

### Verify secrets are loaded

```bash
oc get secret x2a-credentials -n <your-namespace>
oc describe secret x2a-credentials -n <your-namespace>
```

### Common Issues

**Issue:** Backstage pod fails to start

**Solution:** Check secrets are properly configured and applied:
```bash
oc get secret x2a-credentials -n <your-namespace>
oc logs -n <your-namespace> deployment/backstage-developer-hub
```
