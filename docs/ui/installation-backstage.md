---
layout: default
title: Installation (vanilla Backstage)
parent: UI Documentation
nav_order: 2
---

# Installation (vanilla Backstage)

This guide adds the X2A plugins to a stock Backstage app created with the upstream wizard, not Red Hat Developer Hub on OpenShift. For RHDH deployment, use [Installation]({% link ui/installation.md %}) instead.

Reference implementation and deeper notes live in the Red Hat plugin workspace: [rhdh-plugins/workspaces/x2a](https://github.com/redhat-developer/rhdh-plugins/tree/main/workspaces/x2a) ([`packages/app`](https://github.com/redhat-developer/rhdh-plugins/tree/main/workspaces/x2a/packages), [`packages/backend`](https://github.com/redhat-developer/rhdh-plugins/tree/main/workspaces/x2a/packages)).

## Prerequisites

Follow [Standalone Installation](https://backstage.io/docs/getting-started/), but create the app with the **legacy** stack so the X2A plugins work with the current APIs:

```bash
npx @backstage/create-app@latest --legacy
```

The X2A plugins are not yet adapted to [Backstage’s new frontend system](https://backstage.io/docs/frontend-system/) - that migration is in progress.
Until it lands, you must use `--legacy` when generating the app.

Additionally, for X2A you need:

- A Kubernetes API the backend can reach (local `~/.kube/config` or in-cluster config) so migration jobs can run.
- LLM credentials and optional Ansible Automation Platform settings (see the [X2A backend plugin README](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/plugins/x2a-backend/README.md) for `x2a.credentials` and related environment variables).


## Install packages

From the **repository root** of your generated app (where `packages/app` and `packages/backend` live):

```bash
yarn --cwd packages/app add @red-hat-developer-hub/backstage-plugin-x2a
yarn --cwd packages/backend add @red-hat-developer-hub/backstage-plugin-x2a-backend
yarn --cwd packages/backend add @red-hat-developer-hub/backstage-plugin-scaffolder-backend-module-x2a
```

Published packages (verify versions before pinning in production):

- [@red-hat-developer-hub/backstage-plugin-x2a](https://www.npmjs.com/package/@red-hat-developer-hub/backstage-plugin-x2a) - frontend UI and scaffolder field extension exports.
- [@red-hat-developer-hub/backstage-plugin-x2a-backend](https://www.npmjs.com/package/@red-hat-developer-hub/backstage-plugin-x2a-backend) - backend API and job orchestration ([install instructions in source README](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/plugins/x2a-backend/README.md)).
- [@red-hat-developer-hub/backstage-plugin-scaffolder-backend-module-x2a](https://www.npmjs.com/package/@red-hat-developer-hub/backstage-plugin-scaffolder-backend-module-x2a) - scaffolder module and bundled conversion template.

### Optional components

Only if you need OAuth Dynamic Client Registration UI and/or MCP tool wiring similar to production RHDH overlays:

```bash
yarn --cwd packages/app add @red-hat-developer-hub/backstage-plugin-x2a-dcr
yarn --cwd packages/backend add @backstage/plugin-mcp-actions-backend
yarn --cwd packages/backend add @red-hat-developer-hub/backstage-plugin-x2a-mcp-extras
```

For `backend.actions.pluginSources`, `mcpActions`, and related `app-config` fragments, see [Installation - MCP actions and related app-config (optional)]({% link ui/installation.md %}#mcp-actions-app-config) (same content as the `app-config-rhdh` entry in the rendered `deploy/app.yaml` on that page).
Core X2A conversion flows do not require these packages.

## Register backend plugins

In `packages/backend/src/index.ts`, register the scaffolder module and X2A backend after the base scaffolder backend ([reference `index.ts`](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/packages/backend/src/index.ts)):

```typescript
// ... existing backend.add(...) calls ...
backend.add(import('@backstage/plugin-scaffolder-backend'));
// Add GitHub / GitLab / Bitbucket scaffolder modules to match the auth providers you enable.
backend.add(import('@backstage/plugin-scaffolder-backend-module-github'));
backend.add(import('@backstage/plugin-scaffolder-backend-module-gitlab'));
backend.add(import('@backstage/plugin-scaffolder-backend-module-bitbucket'));
backend.add(
  import('@red-hat-developer-hub/backstage-plugin-scaffolder-backend-module-x2a'),
);
backend.add(import('@red-hat-developer-hub/backstage-plugin-x2a-backend'));
```

If you added the optional MCP packages:

```typescript
backend.add(import('@backstage/plugin-mcp-actions-backend'));
backend.add(import('@red-hat-developer-hub/backstage-plugin-x2a-mcp-extras'));
```

## Register frontend routes and scaffolder extension

In `packages/app/src/App.tsx` (adjust imports to match your existing `create-app` layout):

1. Import the X2A page, translations, and repo field extension:

```tsx
import {
  X2APage,
  x2aPluginTranslations,
  RepoAuthenticationExtension,
} from '@red-hat-developer-hub/backstage-plugin-x2a';
```

2. If you use **OAuth DCR** and installed `backstage-plugin-x2a-dcr`:

```tsx
import { DcrConsentPage } from '@red-hat-developer-hub/backstage-plugin-x2a-dcr';
```

3. Pass plugin strings into `createApp`:

```tsx
const app = createApp({
  // ...apis, bindRoutes, components, etc.
  __experimentalTranslations: {
    availableLanguages: ['en'], // add more if you use them elsewhere
    resources: [x2aPluginTranslations],
  },
});
```

4. Add a route for the portal (path is `/x2a`, not `/x2a/`):

```tsx
<Route path="/x2a" element={<X2APage />} />
```

5. Wrap the scaffolder page so the conversion template can use the **Repo authentication** custom field (same pattern as the [reference `App.tsx`](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/packages/app/src/App.tsx)):

```tsx
import { ScaffolderFieldExtensions } from '@backstage/plugin-scaffolder-react';

<Route path="/create" element={<ScaffolderPage />}>
  <ScaffolderFieldExtensions>
    <RepoAuthenticationExtension />
  </ScaffolderFieldExtensions>
</Route>
```

6. Optional DCR consent route:

```tsx
<Route path="/oauth2/*" element={<DcrConsentPage />} />
```

If repository OAuth behaves oddly, compare `packages/app/src/apis.ts` with the [reference `apis.ts`](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/packages/app/src/apis.ts) (`ScmIntegrationsApi`, `ScmAuth`).

### Sidebar: Conversion Hub

Static routes do not add a sidebar label by themselves (RHDH injects menu text via dynamic plugin metadata). In `packages/app/src/components/Root.tsx`, add an item next to your other `SidebarItem` entries (adjust the icon import if your app uses `@mui/icons-material` instead of `@material-ui/icons`):

```tsx
import { SidebarItem } from '@backstage/core-components';
import ExtensionIcon from '@material-ui/icons/Extension';

// Inside the main <SidebarGroup label="Menu" ...> (or equivalent).
<SidebarItem icon={ExtensionIcon} to="x2a" text="Conversion Hub" />
```

`to="x2a"` matches the `/x2a` route registered in `App.tsx`.

## Catalog: register the conversion template

In the root `app-config.yaml` (next to `packages/`), register the template shipped inside the scaffolder module. Paths are relative to this file. After `yarn install`, confirm the file exists under `node_modules`.

```yaml
catalog:
  locations:
    - type: file
      # Tweak following path based on your actual directory structure. It's relative from the perspective of `packages/backend`.
      target: ../../node_modules/@red-hat-developer-hub/backstage-plugin-scaffolder-backend-module-x2a/templates/conversion-project-template.yaml
      rules:
        - allow: [Template]
```

CSV-driven bulk flows and the `RepoAuthentication` extension are described in [CSV Bulk Import]({% link ui/csv-bulk-import.md %}).

## Configuration (pointers only)

| Topic | Where it is documented |
|--------|-------------------------|
| OAuth providers, env vars, sign-in | [Authentication]({% link ui/authentication.md %}) |
| RBAC / permissions for the `x2a` plugin | [Authorization]({% link ui/authorization.md %}) |
| `x2a:` Kubernetes image, job resources, LLM and AAP credentials | [X2A backend plugin README](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/plugins/x2a-backend/README.md) and [reference app-config.yaml](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/app-config.yaml) |
| SCM host detection (GitHub Enterprise, self-hosted GitLab, etc.) | [Workspace README — SCM Provider Detection](https://github.com/redhat-developer/rhdh-plugins/blob/main/workspaces/x2a/README.md) (`integrations:` host entries; tokens there are not used for X2A repo auth; OAuth applies.) |

If the backend API base URL seen by clients or integrations is not the default, you may need `x2a.callbackBaseUrl` (see in-cluster example in [deploy/app.yaml](https://github.com/x2ansible/x2a-convertor/blob/main/deploy/app.yaml)); local `yarn start` often works without it.

## Run and verify

```bash
yarn start
```

Open `http://localhost:3000/x2a` for the Conversion Hub.
In the catalog, confirm the **conversion project** template appears (might take some time to load after start-up).

## API exploration

Use [API Reference]({% link ui/api-reference.md %}) for the REST surface once the backend plugin is running.
