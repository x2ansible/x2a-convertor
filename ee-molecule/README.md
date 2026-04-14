# Molecule Ansible Execution Environment (EE)

Custom Ansible execution environment (EE) for running molecule tests on AAP/OpenShift.

## What's inside

Extends `ee-supported-rhel9` with `molecule` and `kubernetes` Python packages, plus the `kubernetes.core` collection. See `execution-environment.yml` and `Containerfile` for details.

## Building

```bash
# Using ansible-builder (preferred)
ansible-builder build -t quay.io/x2ansible/ee-molecule:latest -f execution-environment.yml

# Or directly with podman/docker
podman build -t quay.io/x2ansible/ee-molecule:latest -f Containerfile .
```

## How it's used

The x2a pipeline publishes a molecule job template to AAP that runs inside this EE. The EE image is configured via `AAP_MOLECULE_EE_IMAGE` env var (default in `src/config/settings.py` under `AAPSettings.molecule_ee_image`).

The molecule scenario uses a **delegated driver** with local connection -- no Docker-in-Docker or nested containers. Tests run directly inside the EE container on OpenShift, validating generated role outputs under `/tmp/molecule_test/`.
