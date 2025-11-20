# Running x2a-convertor on OpenShift

Deploy x2a-convertor as Kubernetes Jobs on OpenShift to run migrations at scale. This approach allows you to run multiple migrations against different Chef/Puppet/Salt repositories without installing dependencies locally.

> **Quick Start**: All operations can be done using the provided Makefile.
> ```bash
> cd openshift
> make help        # View all available commands
> make deploy-infra # Deploy infrastructure
> make run-init    # Run migrations
> ```

## Quick Start

### 1. Deploy Infrastructure (One Time)

```bash
cd openshift

# Deploy all infrastructure
make deploy-infra

# Configure LLM credentials
oc create secret generic x2a-secrets \
  --from-literal=OPENAI_API_KEY='your-api-key' \
  -n x2a-convertor

# Or edit and apply secret.yaml
vim secret.yaml  # Update with your credentials
make deploy-secret
```

### 2. Upload Source Repositories

Create a helper pod to copy files:

```bash
oc run upload --image=registry.access.redhat.com/ubi9/ubi-minimal \
  --restart=Never -n x2a-convertor -- sleep 3600

# Wait for pod to be ready
oc wait --for=condition=ready pod/upload -n x2a-convertor --timeout=60s

oc exec upload -n x2a-convertor -- microdnf install -y tar

# Upload your cookbook (it will be at /data/source in the job)
oc rsync ./my-chef-cookbook/ upload:/data/ -n x2a-convertor

oc delete pod upload -n x2a-convertor
```

**Important for Chef cookbooks**: The analyze step requires `Policyfile.lock.json` in your cookbook directory. If your cookbook doesn't have one, create it with your cookbook dependencies. See the `examples/hello_world/Policyfile.lock.json` for a minimal example.

Note: The jobs are configured to use `/data/source` as the source directory, so upload your cookbook files directly to `/data/`.

### 3. Run Migrations

**Option A: Using the helper script (Recommended)**

```bash
cd openshift

# Run the complete workflow for your cookbook
./run-job.sh /data/source init "Migrate to Ansible"
./run-job.sh /data/source analyze "Analyze cookbook"
./run-job.sh /data/source migrate "Migrate"
./run-job.sh /data/source validate "chef_to_ansible"

# For multiple cookbooks, just change the path
./run-job.sh /data/nginx init "Migrate to Ansible"
./run-job.sh /data/nginx analyze "Analyze nginx cookbook"
./run-job.sh /data/nginx migrate "Migrate nginx"
```

**Option B: Using Makefile (uses hardcoded job YAMLs)**

```bash
cd openshift

# Edit job YAML files first to customize paths
vim job-init.yaml  # Update --source-dir if needed

# Run the workflow
make run-init      # Creates high-level migration plan
make run-analyze   # Analyzes modules in detail
make run-migrate   # Generates Ansible playbooks
make run-validate  # Validates the migration

# Check status anytime
make status
```

## Configuration

### LLM Providers

The ConfigMap controls which LLM to use. Update it based on your provider:

**OpenAI:**
```bash
oc patch configmap x2a-config -n x2a-convertor --type merge \
  -p '{"data":{"LLM_MODEL":"gpt-4o","OPENAI_API_BASE":"https://api.openai.com/v1"}}'

oc create secret generic x2a-secrets \
  --from-literal=OPENAI_API_KEY='sk-...' \
  -n x2a-convertor --dry-run=client -o yaml | oc apply -f -
```

**AWS Bedrock:**
```bash
oc patch configmap x2a-config -n x2a-convertor --type merge \
  -p '{"data":{"LLM_MODEL":"claude-3-5-sonnet-20241022"}}'

oc create secret generic x2a-secrets \
  --from-literal=AWS_BEARER_TOKEN_BEDROCK='your-token' \
  -n x2a-convertor --dry-run=client -o yaml | oc apply -f -
```

**OpenShift AI / RHOAI Model Serving:**
```bash
oc patch configmap x2a-config -n x2a-convertor --type merge \
  -p '{"data":{"LLM_MODEL":"llama-3-2-3b","OPENAI_API_BASE":"https://your-llama-endpoint.apps.cluster.example.com:443/v1"}}'

oc create secret generic x2a-secrets \
  --from-literal=OPENAI_API_KEY='your-api-key' \
  -n x2a-convertor --dry-run=client -o yaml | oc apply -f -
```

Replace `llama-3-2-3b` with your actual model name and update the endpoint URL to match your RHOAI deployment.

### Adjust Resources

Edit the Job YAML files to change memory/CPU limits:

```yaml
resources:
  requests:
    memory: "2Gi"
    cpu: "500m"
  limits:
    memory: "8Gi"   # Increase for large cookbooks
    cpu: "4000m"
```

## Helper Script Reference

The `run-job.sh` script simplifies running migrations by generating job manifests dynamically:

```bash
./run-job.sh <cookbook-path> <stage> [message]
```

**Stages:**
- `init` - Create high-level migration plan
- `analyze` - Detailed module analysis  
- `migrate` - Generate Ansible playbooks
- `validate` - Validate migration output

**Examples (matching official Docker usage):**
```bash
# Init (generic message)
./run-job.sh /data/source init "Migrate to Ansible"

# Analyze (specific cookbook name if known)
./run-job.sh /data/nginx analyze "Analyze nginx cookbook"

# Migrate (specific module)
./run-job.sh /data/nginx migrate "Migrate nginx"

# Validate (module name)
./run-job.sh /data/nginx validate "nginx"

# Follow logs automatically
FOLLOW_LOGS=true ./run-job.sh /data/source init "Migrate"
```

The script:
- Creates uniquely named jobs (no need to delete old ones)
- Uses the same ConfigMap and Secret configuration
- Supports all four migration stages
- Automatically shows the command to view logs

## Running Bulk Migrations

For migrating multiple cookbooks, use the helper script:

### 1. Organize Source Data

```
/data/
  ├── cookbook-nginx/
  │   ├── metadata.rb
  │   ├── recipes/
  │   └── ...
  ├── cookbook-apache/
  │   ├── metadata.rb
  │   └── ...
  └── cookbook-mysql/
      └── ...
```

### 2. Run Migrations in Parallel

```bash
# Run init for all cookbooks
for cookbook in nginx apache mysql; do
  ./run-job.sh /data/cookbook-${cookbook} init "Migrate to Ansible" &
done
wait

echo "All init jobs started!"

# Then analyze (after init completes)
for cookbook in nginx apache mysql; do
  ./run-job.sh /data/cookbook-${cookbook} analyze "Analyze ${cookbook} cookbook" &
done
wait

# Monitor all jobs
oc get jobs -n x2a-convertor -l stage=init
```

### 3. Monitor Progress

```bash
# List all jobs
oc get jobs -n x2a-convertor

# Check specific job
oc logs job/x2a-init-nginx -n x2a-convertor

# View all job statuses
oc get jobs -n x2a-convertor -o custom-columns=\
NAME:.metadata.name,\
STATUS:.status.conditions[0].type,\
COMPLETIONS:.status.succeeded,\
DURATION:.status.completionTime
```

### 4. Collect Results

```bash
# Download all migration artifacts
oc run download --image=registry.access.redhat.com/ubi9/ubi-minimal \
  --restart=Never -n x2a-convertor -- sleep 300

oc exec download -n x2a-convertor -- microdnf install -y tar

# Sync everything back
oc rsync download:/data/ ./migration-results/ -n x2a-convertor

oc delete pod download -n x2a-convertor
```

## Migration Workflow

The typical workflow follows four stages. Run these in sequence for each cookbook:

**Stage 1: Initialize**
- Creates high-level migration plan
- Identifies cookbooks and dependencies
- Outputs: `MIGRATION-PLAN.md`

**Stage 2: Analyze**
- Detailed analysis of each module
- Maps resources and configurations
- Outputs: `migration-plan-<module>.md` files

**Stage 3: Migrate**
- Generates Ansible playbooks
- Applies ansible-lint corrections
- Outputs: `ansible/` directory structure

**Stage 4: Validate**
- Compares original vs generated configs
- Reports differences
- Outputs: Validation report

## Job Management

### Viewing Logs

```bash
# Follow logs in real-time
oc logs -f job/x2a-init-job -n x2a-convertor

# View logs from completed job
oc logs job/x2a-init-job -n x2a-convertor --tail=100
```

### Rerunning Jobs

Jobs can't be rerun once completed. Delete and recreate:

```bash
oc delete job x2a-init-job -n x2a-convertor
oc apply -f openshift/job-init.yaml
```

### Cleaning Up Completed Jobs

```bash
# Delete all completed jobs
oc delete jobs -n x2a-convertor --field-selector status.successful=1

# Delete all jobs (fresh start)
oc delete jobs -n x2a-convertor --all
```

## Troubleshooting

### Job Stays in Pending State

Check PVC binding:
```bash
oc get pvc -n x2a-convertor
oc describe pvc x2a-source-data -n x2a-convertor
```

Check pod events:
```bash
oc get pods -n x2a-convertor
oc describe pod <pod-name> -n x2a-convertor
```

### LLM Connection Errors

Verify secret:
```bash
oc get secret x2a-secrets -n x2a-convertor -o yaml
```

Check ConfigMap:
```bash
oc get configmap x2a-config -n x2a-convertor -o yaml
```

Test from a debug pod:
```bash
oc run test --image=curlimages/curl --rm -it -n x2a-convertor -- \
  curl -H "Authorization: Bearer YOUR_TOKEN" YOUR_ENDPOINT/v1/models
```

### Out of Memory

Increase limits in Job YAML:
```yaml
resources:
  limits:
    memory: "16Gi"  # Default is 4Gi
```

### Permission Denied Errors

The Jobs use OpenShift's restricted security context. Check logs for specific permission issues:
```bash
oc logs <pod-name> -n x2a-convertor
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ OpenShift Cluster                                       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │ Namespace: x2a-convertor                         │  │
│  │                                                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │  │
│  │  │ ConfigMap   │  │ Secret      │  │ PVC     │ │  │
│  │  │             │  │             │  │ (5Gi)   │ │  │
│  │  │ - LLM Model │  │ - API Keys  │  │         │ │  │
│  │  │ - Log Level │  │             │  │ Source  │ │  │
│  │  └─────────────┘  └─────────────┘  └────┬────┘ │  │
│  │                                          │      │  │
│  │  ┌───────────────────────────────────────┼────┐ │  │
│  │  │ Job: x2a-init-nginx                   │    │ │  │
│  │  │  ├─ Image: quay.io/x2ansible/...      │    │ │  │
│  │  │  ├─ Args: init "..." --source-dir ... │    │ │  │
│  │  │  └─ Mounts: /data/source ◄─────────────────┘ │  │
│  │  └───────────────────────────────────────────────┘  │
│  │                                                  │  │
│  │  ┌───────────────────────────────────────────┐  │  │
│  │  │ Job: x2a-init-apache                      │  │  │
│  │  │  (runs in parallel)                       │  │  │
│  │  └───────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Storage Layout

Organize your PVC for multiple projects:

```
PVC: x2a-source-data (5Gi)
/data/
  ├── project-a/
  │   ├── cookbook-nginx/
  │   │   ├── MIGRATION-PLAN.md
  │   │   ├── migration-plan-nginx.md
  │   │   └── ansible/
  │   └── cookbook-apache/
  │       └── ...
  └── project-b/
      └── cookbook-mysql/
          └── ...
```

Point each Job to its specific directory using `--source-dir`.

## Alternative: Using Kustomize

If you prefer Kustomize over Make:

```bash
cd openshift

# Deploy infrastructure
oc apply -k .

# Run jobs manually
oc apply -f job-init.yaml
```

The `kustomization.yaml` file is provided for users who prefer declarative configuration management with Kustomize.

## Makefile Reference

The openshift Makefile provides convenient commands for all operations:

```bash
cd openshift

# Get help
make help

# Setup
make deploy-infra     # Deploy infrastructure (one time)
make deploy-secret    # Deploy secret from secret.yaml
make deploy           # Deploy everything

# Run jobs
make run-init         # Run init job
make run-analyze      # Run analyze job  
make run-migrate      # Run migrate job
make run-validate     # Run validate job

# Monitor
make status           # Show all resource status
make logs             # List all jobs
make logs-init        # View init job logs
make logs-analyze     # View analyze job logs
make logs-migrate     # View migrate job logs
make logs-validate    # View validate job logs

# Cleanup
make clean-jobs       # Delete all jobs
make clean            # Delete entire namespace (destructive!)
```

## Security Considerations

### Network Policies

If your cluster uses network policies, allow egress to LLM APIs:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: x2a-llm-egress
  namespace: x2a-convertor
spec:
  podSelector:
    matchLabels:
      app: x2a-convertor
  policyTypes:
    - Egress
  egress:
    - ports:
        - protocol: TCP
          port: 443
```

### Secrets Management

For production, use OpenShift's sealed secrets or external secret management:

```bash
# Example with sealed secrets
kubeseal --format=yaml < secret.yaml > sealed-secret.yaml
oc apply -f sealed-secret.yaml
```

### Service Mesh

If using Istio/OpenShift Service Mesh, configure egress for LLM endpoints:

```yaml
apiVersion: networking.istio.io/v1beta1
kind: ServiceEntry
metadata:
  name: openai-api
spec:
  hosts:
    - api.openai.com
  ports:
    - number: 443
      name: https
      protocol: HTTPS
  location: MESH_EXTERNAL
  resolution: DNS
```

## Production Recommendations

1. **Resource Quotas**: Set appropriate limits for the namespace
2. **Monitoring**: Add Prometheus metrics for job duration and success rates
3. **Audit Logging**: Enable OpenShift audit logging for compliance
4. **Backup**: Regularly backup PVC contents
5. **Access Control**: Use RBAC to restrict who can create jobs
6. **Cost Management**: Use `ttlSecondsAfterFinished` to auto-cleanup old jobs

## Related Documentation

- [Configuration Guide](../docs/getting-started/configuration.md) - LLM provider setup
- [Architecture](../docs/concepts/architecture.md) - How x2a-convertor works
- [Docker Usage](../docs/getting-started/docker-usage.md) - Local container usage
