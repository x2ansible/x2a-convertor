#!/bin/bash
# Helper script to run x2a-convertor jobs with custom parameters
# Usage: ./run-job.sh <stage> <cookbook-path> [additional args]

set -e

NAMESPACE=${NAMESPACE:-x2a-convertor}
COOKBOOK_PATH=${1:-/data/source}
STAGE=${2:-init}

if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    echo "Usage: $0 <cookbook-path> <stage> [message]"
    echo ""
    echo "Examples:"
    echo "  $0 /data/nginx init 'Migrate to Ansible'"
    echo "  $0 /data/nginx analyze 'Analyze nginx cookbook'"
    echo "  $0 /data/nginx migrate 'Migrate nginx'"
    echo "  $0 /data/nginx validate 'nginx'"
    echo ""
    echo "Stages: init, analyze, migrate, validate"
    echo "Note: Message is optional - sensible defaults are provided"
    exit 0
fi

# Generate unique job name with timestamp
TIMESTAMP=$(date +%s)
JOB_NAME="x2a-${STAGE}-${TIMESTAMP}"

echo "Creating job: $JOB_NAME"
echo "Cookbook path: $COOKBOOK_PATH"
echo "Stage: $STAGE"

# Build args based on stage
case $STAGE in
    init)
        USER_MESSAGE=${3:-"Migrate to Ansible"}
        ARGS="[\"init\", \"${USER_MESSAGE}\", \"--source-dir\", \"${COOKBOOK_PATH}\"]"
        ;;
    analyze)
        USER_MESSAGE=${3:-"Analyze cookbook"}
        ARGS="[\"analyze\", \"${USER_MESSAGE}\", \"--source-dir\", \"${COOKBOOK_PATH}\"]"
        ;;
    migrate)
        USER_MESSAGE=${3:-"Migrate"}
        MODULE_PLAN=${4:-"${COOKBOOK_PATH}/migration-plan-chef_to_ansible.md"}
        HIGH_LEVEL_PLAN=${5:-"${COOKBOOK_PATH}/migration-plan.md"}
        ARGS="[\"migrate\", \"${USER_MESSAGE}\", \"--source-dir\", \"${COOKBOOK_PATH}\", \"--source-technology\", \"Chef\", \"--module-migration-plan\", \"${MODULE_PLAN}\", \"--high-level-migration-plan\", \"${HIGH_LEVEL_PLAN}\"]"
        ;;
    validate)
        MODULE_NAME=${3:-"module"}
        ARGS="[\"validate\", \"${MODULE_NAME}\"]"
        ;;
    *)
        echo "Error: Unknown stage '$STAGE'"
        echo "Valid stages: init, analyze, migrate, validate"
        exit 1
        ;;
esac

# Create the job
cat <<EOF | oc apply -f -
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: x2a-convertor
    stage: ${STAGE}
spec:
  ttlSecondsAfterFinished: 3600
  backoffLimit: 2
  template:
    metadata:
      labels:
        app: x2a-convertor
        stage: ${STAGE}
    spec:
      serviceAccountName: x2a-convertor
      restartPolicy: OnFailure
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: x2a-convertor
          image: quay.io/x2ansible/x2a-convertor:latest
          imagePullPolicy: Always
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            capabilities:
              drop:
                - ALL
          args: ${ARGS}
          env:
            - name: UV_CACHE_DIR
              value: /tmp/.uv-cache
            - name: HOME
              value: /tmp
          envFrom:
            - configMapRef:
                name: x2a-config
            - secretRef:
                name: x2a-secrets
          volumeMounts:
            - name: source-data
              mountPath: /data/source
            - name: output-data
              mountPath: /data/output
          resources:
            requests:
              memory: "2Gi"
              cpu: "500m"
            limits:
              memory: "4Gi"
              cpu: "2000m"
      volumes:
        - name: source-data
          persistentVolumeClaim:
            claimName: x2a-source-data
        - name: output-data
          persistentVolumeClaim:
            claimName: x2a-output-data
EOF

echo ""
echo "✓ Job created: ${JOB_NAME}"
echo ""
echo "Monitor with:"
echo "  oc logs -f job/${JOB_NAME} -n ${NAMESPACE}"
echo "  oc get jobs ${JOB_NAME} -n ${NAMESPACE}"
echo ""

# Optionally follow logs
if [ "${FOLLOW_LOGS}" == "true" ]; then
    echo "Following logs..."
    sleep 3
    oc logs -f job/${JOB_NAME} -n ${NAMESPACE}
fi

