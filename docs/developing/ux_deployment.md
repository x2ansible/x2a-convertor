# X2A Backstage Plugin Deployment

This guide covers deploying the X2A Backstage plugin on OpenShift using Red Hat Developer Hub.

## Prerequisites

- OpenShift cluster access (CRC or production cluster)
- `oc` CLI tool installed and configured
- AWS credentials with access to Bedrock (for LLM)
- Ansible Automation Platform instance (optional, for publishing)

## Installation Steps

### 1. Install Red Hat Developer Hub Operator

Save the following YAML as `install.yaml`:

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-developer-hub
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: developer-hub-operator-subscription
  namespace: openshift-operators
spec:
  channel: fast
  installPlanApproval: Automatic
  name: rhdh
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

Apply the configuration:

```bash
oc apply -f install.yaml
```

Wait for the operator to be ready:

```bash
oc get csv -n openshift-operators | grep rhdh
```

### 2. Deploy Backstage with X2A Plugin

Save the following YAML as `bs.yaml`:

```yaml
---
kind: ConfigMap
apiVersion: v1
metadata:
  name: dynamic-plugins
  namespace: openshift-developer-hub
data:
  dynamic-plugins.yaml: |
    includes:
      - dynamic-plugins.default.yaml
    plugins:
      - package: "oci://quay.io/x2ansible/red-hat-developer-hub-backstage-plugin-x2a:x2a__0.1.0!red-hat-developer-hub-backstage-plugin-x2a"
        disabled: false
      - package: "oci://quay.io/x2ansible/red-hat-developer-hub-backstage-plugin-x2a-backend:x2a__0.1.0!red-hat-developer-hub-backstage-plugin-x2a-backend"
        disabled: false
---
kind: ConfigMap
apiVersion: v1
metadata:
  name: app-config-rhdh
  namespace: openshift-developer-hub
data:
  app-config-rhdh.yaml: |
    auth:
      environment: development
      providers:
        guest:
          dangerouslyAllowOutsideDevelopment: true
    permission:
      enabled: false

    dynamicPlugins:
      frontend:
        red-hat-developer-hub.backstage-plugin-x2a:
          dynamicRoutes:
            - path: /x2a
              importName: X2APage
              menuItem:
                text: X2A
                # icon: CloudQueue

    x2a:
      kubernetes:
        namespace: openshift-developer-hub  # Namespace where x2a jobs will run
        image: quay.io/x2ansible/x2a-convertor
        imageTag: latest
        ttlSecondsAfterFinished: 86400  # 24 hours
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
      credentials:
        llm:
          LLM_MODEL: ${LLM_MODEL}
          AWS_REGION: ${AWS_REGION}
          AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
          AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
        aap:
          url: ${AAP_URL}
          orgName: ${AAP_ORG_NAME}
          oauthToken: ${AAP_OAUTH_TOKEN}
---
kind: Secret
apiVersion: v1
metadata:
  name: x2a-credentials
  namespace: openshift-developer-hub
type: Opaque
stringData:
  LLM_MODEL: "anthropic.claude-3-7-sonnet-20250219-v1:0"
  AWS_REGION: "us-east-1"
  AWS_ACCESS_KEY_ID: "your-aws-access-key-id"
  AWS_SECRET_ACCESS_KEY: "your-aws-secret-access-key"
  AAP_URL: "https://your-aap-instance.com"
  AAP_ORG_NAME: "your-org"
  AAP_OAUTH_TOKEN: "your-oauth-token"
---
kind: PersistentVolumeClaim
apiVersion: v1
metadata:
  name: dynamic-plugins-root
  namespace: openshift-developer-hub
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: crc-csi-hostpath-provisioner
  resources:
    requests:
      storage: 2Gi
---
apiVersion: rhdh.redhat.com/v1alpha1
kind: Backstage
metadata:
  name: developer-hub
  namespace: openshift-developer-hub
spec:
  application:
    dynamicPluginsConfigMapName: dynamic-plugins
    appConfig:
      mountPath: /opt/app-root/src
      configMaps:
        - name: app-config-rhdh
    extraFiles:
      mountPath: /opt/app-root/src
    route:
      enabled: true
  extraEnvs:
    envs:
      - name: LOG_LEVEL
        value: INFO
    secrets:
      - name: x2a-credentials
```

Apply the configuration:

```bash
oc apply -f bs.yaml
```

### 3. Update Credentials

Edit the secret with your actual credentials:

```bash
oc edit secret x2a-credentials -n openshift-developer-hub
```

Update the following values:
- `LLM_MODEL`: Your preferred AWS Bedrock model
- `AWS_REGION`: Your AWS region
- `AWS_ACCESS_KEY_ID`: Your AWS access key
- `AWS_SECRET_ACCESS_KEY`: Your AWS secret key
- `AAP_URL`: Your Ansible Automation Platform URL (if using publish feature)
- `AAP_ORG_NAME`: Your AAP organization name
- `AAP_OAUTH_TOKEN`: Your AAP OAuth token

You need to delete the Backstage pod when the secret is changed.

### 4. Access the Application

Get the Developer Hub URL:

```bash
oc get route developer-hub -n openshift-developer-hub -o jsonpath='https://{.spec.host}{"\n"}'
```

Open the URL in your browser and navigate to the X2A menu item to start using the migration tool.

## Configuration Options

### Storage Class

For production environments, update the `storageClassName` in the PersistentVolumeClaim to match your cluster's storage provider:

```yaml
spec:
  storageClassName: your storage class
```

To list available storage classes:

```bash
oc get storageclass
```

## Troubleshooting

### Check operator installation

```bash
oc get csv -n openshift-operators | grep rhdh
oc get pods -n openshift-operators
```

### Check Backstage deployment

```bash
oc get backstage -n openshift-developer-hub
oc get pods -n openshift-developer-hub
oc logs -n openshift-developer-hub deployment/backstage-developer-hub
```

## Uninstall

To remove the X2A Backstage deployment:

```bash
oc delete backstage developer-hub -n openshift-developer-hub
oc delete -f bs.yaml
oc delete -f install.yaml
```
