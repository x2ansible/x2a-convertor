import os

# Maximum recursion limit for LLM calls
RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", default="100"))

# Maximum number of attempts to export the Ansible playbook
MAX_EXPORT_ATTEMPTS = int(os.getenv("MAX_EXPORT_ATTEMPTS", default="5"))
