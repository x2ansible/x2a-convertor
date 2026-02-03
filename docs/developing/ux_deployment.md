---
layout: default
title: UX Deployment
parent: Developing
---

# X2A Backstage Plugin Deployment

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

# 4. Deploy application resources
oc apply -n <your-namespace> -f deploy/app.yaml

# 5. Configure and apply secrets
cp deploy/secrets.yaml.template deploy/secrets.yaml
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
