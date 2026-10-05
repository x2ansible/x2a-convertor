"""Shared Molecule scenario contract values used by generation and validation."""

DEFAULT_LINUX_IMAGE = "registry.access.redhat.com/ubi9/ubi-init:latest"
COLLECTIONS_PATH_TEMPLATE = "${MOLECULE_PROJECT_DIRECTORY}/collections"
SYSTEMD_COMMAND = "/sbin/init"
SYSTEMD_MODE = "always"
PODMAN_COLLECTION = "containers.podman"
REQUIREMENTS_FILE = "molecule/requirements.yml"
INVENTORY_ARGUMENT = "--inventory=${MOLECULE_SCENARIO_DIRECTORY}/inventory/"
LIFECYCLE_ACTIONS = ("create", "prepare", "converge", "verify", "destroy")
TEST_SEQUENCE = (
    "dependency",
    "destroy",
    "create",
    "prepare",
    "converge",
    "idempotence",
    "verify",
    "destroy",
)
