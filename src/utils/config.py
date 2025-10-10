import os

# Maximum recursion limit for the analyze phase
ANALYZE_RECURSION_LIMIT = os.getenv("ANALYZE_RECURSION_LIMIT", default=100)

# Maximum number of attempts to export the Ansible playbook
MAX_EXPORT_ATTEMPTS = os.getenv("MAX_EXPORT_ATTEMPTS", default=5)
