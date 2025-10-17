import os
from typing import Literal

defaults = {
    "RECURSION_LIMIT": 100,
    "MAX_EXPORT_ATTEMPTS": 10,
}


# Delay os.getnv() in favor of dotenv
def get_config_int(
    envVar: Literal["RECURSION_LIMIT", "MAX_EXPORT_ATTEMPTS"],
) -> int:
    """Get an integer configuration value from the environment
    Args:
        envVar: The environment variable to get the value from

        RECURSION_LIMIT: Maximum recursion limit for LLM calls
        MAX_EXPORT_ATTEMPTS: Maximum number of attempts to export the Ansible playbook
    Returns:
        The integer value of the environment variable
    """
    if envVar not in defaults:
        raise ValueError(f"Invalid environment variable: {envVar}")

    return int(os.getenv(envVar, default=defaults[envVar]))
