"""Metadata extraction types"""

from pydantic import BaseModel, Field

from src.types.technology import Technology


class ModuleMetadata(BaseModel):
    """Metadata for a single module/cookbook identified in migration plan.

    Structured output schema for LLM extraction.
    """

    name: str = Field(
        description="Module or cookbook name (e.g., 'web_server', 'database', 'monitoring')"
    )
    path: str = Field(
        description="Relative path to the module/cookbook directory (e.g., 'cookbooks/web_server', 'modules/database')"
    )
    description: str = Field(
        description="Brief description of what this module does (1-2 sentences maximum, focus on primary purpose)"
    )
    technology: Technology = Field(
        default=Technology.CHEF,
        description='Source technology - must be exactly one of: "Chef", "Puppet", "PowerShell", or "Ansible"',
    )


class MetadataCollection(BaseModel):
    """Collection of all modules identified in the migration plan.

    Top-level schema for structured output.

    Example JSON output:
    {
      "modules": [
        {
          "name": "web_server",
          "path": "cookbooks/web_server",
          "description": "Manages web server installation and configuration with SSL support.",
          "technology": "Chef"
        },
        {
          "name": "database",
          "path": "modules/database",
          "description": "Installs and configures database server with user and schema management.",
          "technology": "Puppet"
        },
        {
          "name": "monitoring",
          "path": "salt/monitoring",
          "description": "Deploys monitoring agents and configures alerting rules.",
          "technology": "Salt"
        }
      ]
    }
    """

    modules: list[ModuleMetadata] = Field(
        description="List of all modules/cookbooks found in the migration plan. Each entry represents a distinct module (not individual files or recipes)."
    )
