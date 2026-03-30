# Ansible Molecule Integration Plan

## Context

The x2a-convertor migrates infrastructure code (Chef, PowerShell, legacy Ansible) to modern Ansible roles. Each migration plan already contains **"Pre-flight checks"** — bash commands to verify services are running correctly (e.g., `systemctl status`, `psql -c "SELECT version();"`, port checks). These checks are currently documentation-only.

This plan integrates Ansible Molecule so that:
1. Each migrated role gets its own `molecule/` directory with proper test scenarios
2. The `verify.yml` playbook translates the migration plan's pre-flight checks into Ansible tasks
3. Molecule tests can run on the AAP instance (OpenShift cluster)
4. The publish command includes molecule files in the published project

## Stage 1: Prove Molecule Works on AAP (Manual Validation)

**Goal**: Create a test role and run `molecule test` against the AAP/OpenShift cluster.

### 1.1 Create a test role with molecule scenario
Create a minimal test role at `tests/fixtures/molecule-test-role/` with:
- `tasks/main.yml` — installs a package or creates a file
- `molecule/default/molecule.yml` — using **delegated driver** (not podman — AAP uses delegated/default driver per Molecule 6)
- `molecule/default/create.yml` — provisions a pod on OpenShift using `kubernetes.core.k8s`
- `molecule/default/destroy.yml` — tears down the pod
- `molecule/default/converge.yml` — runs the role
- `molecule/default/verify.yml` — checks the role applied correctly

### 1.2 Molecule config for AAP/OpenShift
The `molecule.yml` will use the **delegated driver** (aliased as "default"), which is the only driver in Molecule 6 for AAP:

```yaml
---
driver:
  name: default

platforms:
  - name: molecule-test-instance
    groups:
      - all

provisioner:
  name: ansible
  inventory:
    hosts:
      all:
        hosts:
          molecule-test-instance:
            ansible_connection: local

verifier:
  name: ansible
```

For OpenShift, `create.yml` will use `kubernetes.core.k8s` to spin up a test pod, and `destroy.yml` will remove it. The `KUBECONFIG` env var will be set to `~/.kube/aap/config`.

### 1.3 Check AAP Execution Environments
Before running molecule, check what EEs are available on the AAP instance:
```bash
kubectl --kubeconfig ~/.kube/aap/config get pods -n aap -o wide
# Check AAP Controller API for available EEs
```
We need an EE with `molecule` installed. If none exists, we'll document what's needed.

### 1.4 Manual validation steps
- Run `uv run molecule test -s default` from the test role directory
- Verify all phases pass: dependency → create → converge → verify → destroy
- Confirm the pod appears/disappears on the OpenShift cluster

**Decisions confirmed:**
- **Driver**: Delegated (default) with OpenShift pods via `kubernetes.core.k8s`
- **EE**: Check existing EEs, document requirements if molecule isn't available

**Files to create:**
- `tests/fixtures/molecule-test-role/tasks/main.yml`
- `tests/fixtures/molecule-test-role/meta/main.yml`
- `tests/fixtures/molecule-test-role/molecule/default/molecule.yml`
- `tests/fixtures/molecule-test-role/molecule/default/create.yml`
- `tests/fixtures/molecule-test-role/molecule/default/destroy.yml`
- `tests/fixtures/molecule-test-role/molecule/default/converge.yml`
- `tests/fixtures/molecule-test-role/molecule/default/verify.yml`

## Stage 2: Migration Agent Creates Molecule Files

**Goal**: The WriteAgent generates `molecule/` directory contents as part of each role migration, with `verify.yml` derived from the migration plan's pre-flight checks.

### 2.1 Add "molecule" to the checklist categories
**File**: `src/exporters/types.py` (MigrationCategory enum)

Add a new category `MOLECULE = "molecule"` for molecule-related files.

### 2.2 Update PlanningAgent to add molecule checklist items
**File**: `prompts/export_ansible_planning_system.md`

Add a new checklist category section:

```
Molecule Testing:
- molecule/default/molecule.yml — Molecule scenario configuration
- molecule/default/converge.yml — Playbook that applies the role
- molecule/default/verify.yml — Verification tasks from pre-flight checks
- molecule/default/create.yml — Instance provisioning (OpenShift pod)
- molecule/default/destroy.yml — Instance teardown
```

The planning agent will add these as checklist items with category `molecule`.

### 2.3 Update WriteAgent to generate molecule files
**File**: `prompts/export_ansible_write_task.j2` or `prompts/export_ansible_write_system.j2`

Add instructions for the write agent to generate molecule files:
- `molecule.yml` — delegated driver config with platform definition
- `converge.yml` — standard role inclusion playbook
- `verify.yml` — **translate pre-flight checks from the migration plan into Ansible tasks**:
  - `systemctl status X` → `ansible.builtin.service_facts` + assert service is running
  - `curl` checks → `ansible.builtin.uri` module
  - Port checks → `ansible.builtin.wait_for` on port
  - File existence → `ansible.builtin.stat` + assert
  - DB queries → appropriate module (e.g., `community.postgresql.postgresql_query`)
- `create.yml` — create OpenShift pod using `kubernetes.core.k8s`
- `destroy.yml` — destroy the pod

### 2.4 Update AnsibleMolecule class to support delegated driver
**File**: `src/exporters/ansible_molecule.py`

The existing class hardcodes podman driver. Update to:
- Support delegated driver mode (for AAP/OpenShift)
- Accept `create.yml`/`destroy.yml` paths for delegated scenarios
- Remove podman dependency check when using delegated driver
- Keep podman as a fallback for local testing

### 2.5 Key files to modify:
- `src/exporters/types.py` — add MOLECULE category
- `prompts/export_ansible_planning_system.md` — molecule checklist section
- `prompts/export_ansible_write_system.j2` — molecule file generation rules
- `src/exporters/ansible_molecule.py` — delegated driver support
- `src/exporters/write_agent.py` — ensure molecule files go through standard write flow (likely no changes needed since WriteAgent is tool-driven)

## Stage 3: Publish Command Includes Molecule Files

**Goal**: When publishing to AAP, include molecule directories so tests can run on the AAP instance.

### 3.1 Update publish_project to copy molecule files
**File**: `src/publishers/publish.py`

Currently `copy_role_directory()` copies the entire role directory. Since molecule files live under `roles/{role_name}/molecule/`, they should already be copied. Verify this and ensure:
- `molecule/` directory is included in the copy
- Required files verification includes molecule files

### 3.2 Update verify_files_exist check
**File**: `src/publishers/tools.py`

Add molecule directory to the required files verification:
```python
f"{publish_dir}/roles/{role_name}/molecule/default/molecule.yml",
```

### 3.3 AAP Job Template integration (future)
This is more exploratory — understand how AAP can trigger `molecule test` as a job template. This may require:
- An EE (Execution Environment) with molecule installed
- A playbook wrapper that runs `molecule test` on the published roles
- Investigation into whether AAP Controller can natively run molecule

**Files to modify:**
- `src/publishers/publish.py` — verify molecule inclusion
- `src/publishers/tools.py` — add molecule to verification

## Verification Plan

1. **Stage 1 verification**: Run `uv run molecule test` on test fixture role, confirm all phases pass on OpenShift
2. **Stage 2 verification**: Run a migration (e.g., test fixtures) and confirm molecule files are generated with meaningful verify.yml tasks derived from pre-flight checks
3. **Stage 3 verification**: Run publish command and confirm molecule files appear in the published project
4. **Unit tests**: Add tests for molecule file generation in the write pipeline
