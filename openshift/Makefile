# OpenShift Deployment Makefile for x2a-convertor
# Usage: cd openshift && make <target>

OC ?= oc
NAMESPACE ?= x2a-convertor

.PHONY: help deploy deploy-infra deploy-secret status clean clean-jobs \
	run-init run-analyze run-migrate run-validate \
	logs logs-init logs-analyze logs-migrate logs-validate

help:
	@echo "x2a-convertor OpenShift Deployment"
	@echo ""
	@echo "Setup Commands:"
	@echo "  make deploy-infra    - Deploy namespace, configmap, PVCs, serviceaccount"
	@echo "  make deploy-secret   - Deploy secret (edit secret.yaml first)"
	@echo "  make deploy          - Deploy everything (infra + secret)"
	@echo ""
	@echo "Run Jobs:"
	@echo "  make run-init        - Run init job"
	@echo "  make run-analyze     - Run analyze job"
	@echo "  make run-migrate     - Run migrate job"
	@echo "  make run-validate    - Run validate job"
	@echo ""
	@echo "Monitoring:"
	@echo "  make status          - Show all resources status"
	@echo "  make logs            - List all jobs"
	@echo "  make logs-init       - View init job logs"
	@echo "  make logs-analyze    - View analyze job logs"
	@echo "  make logs-migrate    - View migrate job logs"
	@echo "  make logs-validate   - View validate job logs"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean-jobs      - Delete all jobs"
	@echo "  make clean           - Delete entire namespace"
	@echo ""
	@echo "Configuration:"
	@echo "  OC=oc                - OpenShift CLI command (default: oc)"
	@echo "  NAMESPACE=x2a-convertor - Target namespace (default: x2a-convertor)"

# Deploy infrastructure (namespace, configmap, PVCs, RBAC)
deploy-infra:
	@echo "Deploying infrastructure to namespace: $(NAMESPACE)"
	$(OC) apply -f namespace.yaml
	$(OC) apply -f configmap.yaml
	$(OC) apply -f pvc.yaml
	$(OC) apply -f serviceaccount.yaml
	@echo ""
	@echo "✓ Infrastructure deployed successfully"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Configure your LLM credentials:"
	@echo "     $(OC) create secret generic x2a-secrets \\"
	@echo "       --from-literal=OPENAI_API_KEY='your-key' \\"
	@echo "       -n $(NAMESPACE)"
	@echo ""
	@echo "  2. Or edit and apply the secret file:"
	@echo "     vim secret.yaml"
	@echo "     make deploy-secret"

# Deploy secret (requires manual configuration first)
deploy-secret:
	@echo "Deploying secret..."
	$(OC) apply -f secret.yaml
	@echo "✓ Secret deployed"

# Deploy everything
deploy: deploy-infra
	@echo ""
	@echo "Note: Remember to configure secrets before running jobs!"
	@echo "See: make deploy-secret"

# Run init job
run-init:
	@echo "Running init job..."
	-$(OC) delete job x2a-init-job -n $(NAMESPACE) --ignore-not-found=true
	$(OC) apply -f job-init.yaml
	@echo ""
	@echo "Job started. Monitor with:"
	@echo "  make logs-init"
	@echo ""
	@echo "Waiting for job to start..."
	@sleep 5
	@$(OC) logs -f job/x2a-init-job -n $(NAMESPACE) 2>/dev/null || \
		echo "Job starting... Use 'make logs-init' to view logs"

# Run analyze job
run-analyze:
	@echo "Running analyze job..."
	-$(OC) delete job x2a-analyze-job -n $(NAMESPACE) --ignore-not-found=true
	$(OC) apply -f job-analyze.yaml
	@echo ""
	@echo "Job started. Monitor with:"
	@echo "  make logs-analyze"
	@echo ""
	@echo "Waiting for job to start..."
	@sleep 5
	@$(OC) logs -f job/x2a-analyze-job -n $(NAMESPACE) 2>/dev/null || \
		echo "Job starting... Use 'make logs-analyze' to view logs"

# Run migrate job
run-migrate:
	@echo "Running migrate job..."
	-$(OC) delete job x2a-migrate-job -n $(NAMESPACE) --ignore-not-found=true
	$(OC) apply -f job-migrate.yaml
	@echo ""
	@echo "Job started. Monitor with:"
	@echo "  make logs-migrate"
	@echo ""
	@echo "Waiting for job to start..."
	@sleep 5
	@$(OC) logs -f job/x2a-migrate-job -n $(NAMESPACE) 2>/dev/null || \
		echo "Job starting... Use 'make logs-migrate' to view logs"

# Run validate job
run-validate:
	@echo "Running validate job..."
	-$(OC) delete job x2a-validate-job -n $(NAMESPACE) --ignore-not-found=true
	$(OC) apply -f job-validate.yaml
	@echo ""
	@echo "Job started. Monitor with:"
	@echo "  make logs-validate"
	@echo ""
	@echo "Waiting for job to start..."
	@sleep 5
	@$(OC) logs -f job/x2a-validate-job -n $(NAMESPACE) 2>/dev/null || \
		echo "Job starting... Use 'make logs-validate' to view logs"

# View logs
logs:
	@echo "=== Jobs in namespace: $(NAMESPACE) ==="
	@$(OC) get jobs -n $(NAMESPACE) 2>/dev/null || echo "No jobs found"
	@echo ""
	@echo "View logs with:"
	@echo "  make logs-init"
	@echo "  make logs-analyze"
	@echo "  make logs-migrate"
	@echo "  make logs-validate"

logs-init:
	@$(OC) logs -f job/x2a-init-job -n $(NAMESPACE) --tail=100 2>/dev/null || \
		echo "Job not found or not started yet"

logs-analyze:
	@$(OC) logs -f job/x2a-analyze-job -n $(NAMESPACE) --tail=100 2>/dev/null || \
		echo "Job not found or not started yet"

logs-migrate:
	@$(OC) logs -f job/x2a-migrate-job -n $(NAMESPACE) --tail=100 2>/dev/null || \
		echo "Job not found or not started yet"

logs-validate:
	@$(OC) logs -f job/x2a-validate-job -n $(NAMESPACE) --tail=100 2>/dev/null || \
		echo "Job not found or not started yet"

# Check status
status:
	@echo "=== Namespace ==="
	@$(OC) get namespace $(NAMESPACE) 2>/dev/null || echo "Namespace not found"
	@echo ""
	@echo "=== Jobs ==="
	@$(OC) get jobs -n $(NAMESPACE) 2>/dev/null || echo "No jobs found"
	@echo ""
	@echo "=== Pods ==="
	@$(OC) get pods -n $(NAMESPACE) 2>/dev/null || echo "No pods found"
	@echo ""
	@echo "=== PVCs ==="
	@$(OC) get pvc -n $(NAMESPACE) 2>/dev/null || echo "No PVCs found"
	@echo ""
	@echo "=== ConfigMap ==="
	@$(OC) get configmap x2a-config -n $(NAMESPACE) -o jsonpath='{.data}' 2>/dev/null | \
		python3 -m json.tool 2>/dev/null || echo "ConfigMap not found"
	@echo ""

# Clean up
clean-jobs:
	@echo "Deleting all jobs in namespace: $(NAMESPACE)"
	$(OC) delete jobs -n $(NAMESPACE) --all
	@echo "✓ All jobs deleted"

clean:
	@echo "WARNING: This will delete the entire namespace: $(NAMESPACE)"
	@echo "Press Ctrl+C to cancel, or wait 5 seconds to continue..."
	@sleep 5
	$(OC) delete namespace $(NAMESPACE) --ignore-not-found=true
	@echo "✓ Namespace deleted"

