"""Metadata extraction types"""

from pydantic import BaseModel, Field


class ModuleMetadata(BaseModel):
    """Metadata for a single module/cookbook identified in migration plan.

    Structured output schema for LLM extraction.
    """

    name: str = Field(description="Module or cookbook name")
    path: str = Field(description="Relative path to the module/cookbook directory")
    description: str = Field(description="Brief description of what this module does")
    technology: str = Field(
        default="Chef", description="Source technology (Chef, Puppet, Salt)"
    )


class MetadataCollection(BaseModel):
    """Collection of all modules identified in the migration plan.

    Top-level schema for structured output.
    """

    modules: list[ModuleMetadata] = Field(
        description="List of all modules/cookbooks found in the migration plan"
    )
