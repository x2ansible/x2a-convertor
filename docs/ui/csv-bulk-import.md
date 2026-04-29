---
layout: default
title: CSV Bulk Import
parent: UI Documentation
nav_order: 6
---

# CSV Bulk Import

The CSV bulk import lets users create multiple conversion projects at once by uploading a single CSV file.

## How to Access

1. Open the Backstage instance and navigate to `/create`.
2. Select the **Chef-to-Ansible Conversion Project** template (`chef-conversion-project-template`).
3. On the first page, choose **CSV upload** as the input method.
4. Upload the CSV file and proceed through the wizard.

The wizard asks for authentication with each SCM provider (GitHub, GitLab, Bitbucket) referenced in the CSV. Projects are created sequentially with the same permission checks as if the user had created each one individually.

## CSV File Format

The file must be UTF-8 encoded with a header row. Column order does not matter, but header names must match exactly.

### Required Columns

| Column | Description |
|---|---|
| `name` | Unique project name |
| `abbreviation` | Short project identifier, 1-5 alphanumeric characters matching `^([a-zA-Z][a-zA-Z0-9]*)(-[a-zA-Z0-9]+)*$` |
| `sourceRepoUrl` | URL of the repository containing the Chef cookbook to convert |
| `sourceRepoBranch` | Branch to read from in the source repository |
| `targetRepoBranch` | Branch to write converted Ansible output to |

### Optional Columns

| Column | Description |
|---|---|
| `description` | Project description (defaults to empty) |
| `ownedByGroup` | Backstage group that owns the project. When empty, the signed-in user becomes the owner. |
| `targetRepoUrl` | Repository for converted output. Defaults to `sourceRepoUrl` when empty. |

No extra columns are allowed -- the import rejects unknown headers.

### Example

```
name,abbreviation,sourceRepoUrl,sourceRepoBranch,targetRepoUrl,targetRepoBranch,description,ownedByGroup
web-app,wapp,https://github.com/myorg/web-app-chef,main,https://github.com/myorg/web-app-ansible,main,Convert web app cookbook,team-platform
db-setup,dbset,gitlab.com?owner=myorg&repo=db-chef,develop,gitlab.com?owner=myorg&repo=db-ansible,main,,
cache-svc,cache,bitbucket.org?workspace=myws&project=x2a&repo=cache-chef,main,,main,Cache service conversion,
```

- **Row 1** (`web-app`): uses plain HTTPS URLs.
- **Row 2** (`db-setup`): uses RepoUrlPicker-style URLs for GitLab. `description` and `ownedByGroup` are left empty.
- **Row 3** (`cache-svc`): uses RepoUrlPicker-style URL for Bitbucket. `targetRepoUrl` is empty, so the source repository is used as the target.

### CSV File Template

A [sample CSV file](https://raw.githubusercontent.com/redhat-developer/rhdh-plugins/refs/heads/main/workspaces/x2a/plugins/x2a-backend/public/sample-projects.csv) with all supported headers is available for download. At runtime, it is also served at `/x2a/download/sample-projects.csv` via the frontend plugin route.

## Repository URL Formats

Both `sourceRepoUrl` and `targetRepoUrl` accept two formats. All URLs are normalized to HTTPS clone URLs before being stored.

### Plain HTTPS URLs

Standard clone URLs:

| Provider | Format |
|---|---|
| GitHub | `https://github.com/owner/repo` |
| GitLab | `https://gitlab.com/owner/repo` |
| Bitbucket | `https://bitbucket.org/workspace/repo` |

### Backstage RepoUrlPicker Format

Query-parameter style, without `https://`:

| Provider | Format |
|---|---|
| GitHub | `github.com?owner=myuser&repo=myrepo` |
| GitLab | `gitlab.com?owner=myuser&repo=myrepo` |
| Bitbucket | `bitbucket.org?workspace=myworkspace&project=myproj&repo=myrepo` |

For Bitbucket, the `project` parameter is organizational metadata and is not part of the clone URL. Only `workspace` and `repo` are used.

For self-hosted instances (e.g. GitHub Enterprise, self-hosted GitLab), use the corresponding host in place of the public domain. The host must be listed in the `integrations:` section of `app-config.yaml` so the plugin can detect the correct SCM provider. See [Authentication]({% link ui/authentication.md %}) for provider configuration details.

## Repeatable Import

The CSV import is designed to be run repeatedly with the same or an updated file. Projects whose name already exists are **skipped** (not duplicated) and counted as "skipped" in the results summary.

A typical workflow for a large import:

1. Upload the CSV. Some projects succeed, some may fail (e.g. due to a missing repository or a typo).
2. Review the results. The summary shows how many succeeded, failed, and were skipped.
3. Fix the issues -- correct the CSV rows that failed and, if a partially-created project needs to be recreated, delete it from the application first.
4. Re-upload the corrected CSV. Already-created projects are skipped automatically. Only the new or corrected rows are processed.

