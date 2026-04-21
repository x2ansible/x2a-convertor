# x2a Execution Environment (EE)

Ansible execution environment (EE) for running molecule tests and migrated roles on AAP/OpenShift.

## What's inside

Extends `creator-ee` with `molecule` and `kubernetes` Python packages. See `Containerfile` for details.

## Building

```bash
podman build -t quay.io/x2ansible/ee-x2a:latest -f Containerfile .
```

## How it's used

The x2a pipeline publishes job templates to AAP that run inside this EE. The EE image is configured via `AAP_EE_IMAGE` env var (default in `src/config/settings.py` under `AAPSettings.ee_image`).

This single EE serves two purposes:
- **Molecule tests**: Delegated driver with local connection, validating generated role outputs under `/tmp/molecule_test/`
- **Role execution**: Acts as the Ansible controller, connecting to target hosts over SSH to run migrated roles
