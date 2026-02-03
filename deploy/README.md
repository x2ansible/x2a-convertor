# X2A Backstage Plugin Deployment

Quick reference for deploying the X2A Backstage plugin on OpenShift.

## Files

- `operator.yaml` - Red Hat Developer Hub operator (cluster-scoped, install once)
- `app.yaml` - Application resources (ConfigMaps, PVC, Backstage CR)
- `secrets.yaml.template` - Template for credentials (copy and customize)

## Quick Start

```bash
# 1. Install operator (one-time, cluster-scoped)
oc apply -f operator.yaml

# 2. Create your namespace
oc create namespace my-namespace

# 3. Deploy application
oc apply -n my-namespace -f app.yaml

# 4. Configure secrets
cp secrets.yaml.template secrets.yaml
vi secrets.yaml  # Edit with your credentials
oc apply -n my-namespace -f secrets.yaml

# 5. Get the route URL
oc get route developer-hub -n my-namespace -o jsonpath='https://{.spec.host}{"\n"}'
```

## Prerequisites

- OpenShift cluster access (cluster-admin for operator installation)
- oc CLI tool
- AWS Bedrock credentials (for LLM functionality)
- Ansible Automation Platform (optional, for publish feature)

## Customization

All customization points are marked with `# CUSTOMIZATION:` comments in the YAML files:

- **Namespace**: Use `-n <namespace>` flag when applying (no editing required)
- **Storage Class**: See PVC section in `app.yaml`
- **Resource Limits**: See Backstage spec in `app.yaml`
- **Plugin Versions**: See dynamic-plugins ConfigMap in `app.yaml`

## Security

The `secrets.yaml` file is git-ignored and must never be committed.

For production:
- Use External Secrets Operator, Vault, or Sealed Secrets
- Rotate credentials regularly
- Use minimal IAM permissions

## Full Documentation

See [docs/developing/ux_deployment.md](../docs/developing/ux_deployment.md) for complete documentation.

## Troubleshooting

Check operator status:
```bash
oc get csv -n openshift-operators | grep rhdh
```

Check application status:
```bash
oc get backstage -n <your-namespace>
oc get pods -n <your-namespace>
oc logs -n <your-namespace> deployment/backstage-developer-hub
```
