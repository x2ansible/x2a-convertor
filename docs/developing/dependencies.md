# Development Dependencies

## Ansible Automation Platform on OpenShift (CRC)

This guide covers setting up Ansible Automation Platform (AAP) on OpenShift using CodeReady Containers (CRC) for development purposes.

### Prerequisites

If you're not familiar with OpenShift CRC:
- Follow the [CRC installation guide](https://crc.dev/docs/installing/)
- Get your [Red Hat pull secret](https://console.redhat.com/openshift/create/local) for installation

#### Configure CRC Resources

```bash
crc config set memory 24576
crc config set disk-size 100
crc config set cpus 8
```

### Installation

Save the following YAML as `aap-install.yaml`:

```yaml
---
apiVersion: v1
kind: Namespace
metadata:
  name: aap
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: aap-operator-group
  namespace: aap
spec:
  targetNamespaces:
  - aap
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: ansible-automation-platform
  namespace: aap
spec:
  channel: stable-2.6
  name: ansible-automation-platform-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
```

Apply the configuration:

```bash
oc apply -f aap-install.yaml
```


And when all is ready, also this Ansible Resource as `aap-resource.yaml`:

```
---
apiVersion: aap.ansible.com/v1alpha1
kind: AnsibleAutomationPlatform
metadata:
  name: aap
  namespace: aap
spec:
  controller:
    disabled: false
    replicas: 1

  hub:
    disabled: false
    replicas: 1
    file_storage_size: 10Gi
    file_storage_access_mode: ReadWriteOnce

  eda:
    disabled: true
  lightspeed:
    disabled: true

  database:
    replicas: 1
```

```bash
oc apply -f aap-resource.yaml
```

### Accessing AAP

Get the admin password:

```bash
oc get secrets -n aap aap-admin-password -o json | jq '.data.password | @base64d' -r
```

Get the web UI URL:

```bash
oc -n aap get route aap -o json | jq '"https://"+.spec.host' -r
```
