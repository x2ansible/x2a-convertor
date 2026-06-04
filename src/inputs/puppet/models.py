"""Puppet analysis domain models.

This module defines Pydantic models for representing Puppet module analysis.
These are pure data structures used for LLM structured outputs.
"""

from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Execution Item Models (Bedrock-compatible - no circular references)
# ============================================================================


class NestedExecutionItem(BaseModel):
    """Nested execution item (used inside conditionals/iterations).

    Separate from ExecutionItem to avoid circular references which Bedrock doesn't support.
    This level cannot contain further nesting.
    """

    type: str  # "resource", "class_include", "exported_resource", "virtual_resource", "collector"

    # Resource fields
    resource_type: str | None = None
    title: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    # Class include fields
    class_name: str | None = None
    relationship: str | None = None

    # Collector fields
    query: str | None = None

    # Optional note
    note: str | None = None


class ExecutionItem(BaseModel):
    """Unified execution item for Puppet manifests.

    Uses a type discriminator with optional fields instead of discriminated unions
    to maintain Bedrock compatibility (Bedrock doesn't support oneOf).

    Nested items use NestedExecutionItem to avoid circular references.
    """

    type: str  # "resource", "class_include", "conditional", "iteration", etc.

    # Resource fields (type: resource, exported_resource, virtual_resource)
    resource_type: str | None = None
    title: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    # Class include fields (type: class_include)
    class_name: str | None = None
    relationship: str | None = None

    # Conditional fields (type: conditional)
    condition: str | None = None
    condition_type: str | None = None

    # Iteration fields (type: iteration)
    iterator_type: str | None = None
    collection_variable: str | None = None
    item_variable: str | None = None

    # Collector fields (type: collector)
    query: str | None = None

    # Nested execution order (for conditional, iteration)
    # Uses NestedExecutionItem instead of ExecutionItem to avoid circular reference
    execution_order: list[NestedExecutionItem] = Field(default_factory=list)

    # Optional note
    note: str | None = None

    def format_label(self) -> str:
        """Format this item as a tree label based on its type."""
        if self.type == "resource":
            label = f"[resource] {self.resource_type}[{self.title}]"
            return f"{label} ({self.note})" if self.note else label

        if self.type == "class_include":
            return f"{self.relationship} {self.class_name}"

        if self.type == "conditional":
            return f"{self.condition_type} {self.condition}"

        if self.type == "iteration":
            return f"{self.iterator_type} over {self.collection_variable} as {self.item_variable}"

        if self.type == "exported_resource":
            return f"[exported] {self.resource_type}[{self.title}]"

        if self.type == "virtual_resource":
            return f"[virtual] {self.resource_type}[{self.title}]"

        if self.type == "collector":
            return f"[collector] {self.resource_type} <| {self.query} |>"

        return f"{self.type} ({self.note})" if self.note else self.type


# Force Pydantic to rebuild the model to ensure no forward references
ExecutionItem.model_rebuild()
NestedExecutionItem.model_rebuild()


# ============================================================================
# Metadata Models
# ============================================================================


class ClassInheritance(BaseModel):
    """Class inheritance via the 'inherits' keyword."""

    parent_class: str
    child_class: str
    overridden_params: list[str] = Field(default_factory=list)


class ManifestExecutionAnalysis(BaseModel):
    """LLM structured output for a single .pp manifest."""

    class_name: str = ""
    class_parameters: dict[str, str] = Field(default_factory=dict)
    class_inherits: ClassInheritance | None = None
    execution_order: list[ExecutionItem] = Field(
        default_factory=list, description="Sequential execution order of all items"
    )
    puppetdb_queries: list[str] = Field(default_factory=list)
    relationship_chains: list[str] = Field(default_factory=list)
    fact_references: list[str] = Field(default_factory=list)


# ============================================================================
# Hiera Data Analysis Models
# ============================================================================


class HieraVariableMapping(BaseModel):
    """Mapping of a single Hiera variable to its Ansible target."""

    puppet_key: str
    value_type: str  # "string", "hash", "array", "integer", "boolean"
    is_encrypted: bool = False
    ansible_target: str = ""
    ansible_variable_name: str = ""


class HieraDataAnalysis(BaseModel):
    """LLM structured output for a single Hiera data file."""

    variables: list[HieraVariableMapping] = Field(default_factory=list)
    merge_behavior: dict[str, Any] = Field(default_factory=dict)
    lookup_options: dict[str, Any] = Field(default_factory=dict)
    cross_level_overrides: list[str] = Field(default_factory=list)
    notes: str = ""


# ============================================================================
# Template Analysis Models
# ============================================================================


class PuppetTemplateAnalysis(BaseModel):
    """LLM structured output for an ERB (.erb) or EPP (.epp) template."""

    template_type: str  # "erb" or "epp"
    variables_used: list[str] = Field(default_factory=list)
    hiera_lookups: list[str] = Field(default_factory=list)
    loops: list[str] = Field(default_factory=list)
    ruby_logic: list[str] = Field(default_factory=list)
    jinja2_equivalent_notes: str = ""


# ============================================================================
# Custom Type/Provider/Fact Analysis Models
# ============================================================================


class CustomTypeAnalysis(BaseModel):
    """LLM structured output for custom types, providers, facts, and functions."""

    component_type: str  # "type", "provider", "fact", "function"
    name: str
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    ansible_equivalent: str = ""
    requires_custom_module: bool = False
    note: str | None = None


# ============================================================================
# Credential Analysis Models
# ============================================================================


class CredentialEntry(BaseModel):
    """A single detected credential or secret."""

    purpose: str
    variable_names: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    storage_method: str  # "eyaml", "hiera plaintext", "exec", "file source"
    usage_context: str
    ansible_recommendation: str  # "ansible-vault", "CyberArk lookup", "env var"


class CredentialAnalysis(BaseModel):
    """LLM structured output for credential detection."""

    credentials: list[CredentialEntry] = Field(default_factory=list)
    provider_info: str = ""
    total_detected: int = 0


# ============================================================================
# Hiera Hierarchy Models (from deterministic parser)
# ============================================================================


class HieraLevel(BaseModel):
    """A single level in the Hiera hierarchy."""

    name: str
    path_pattern: str
    datadir: str = "data"
    resolved_files: list[str] = Field(default_factory=list)


class HieraHierarchy(BaseModel):
    """Parsed hiera.yaml structure."""

    version: int = 5
    defaults: dict[str, Any] = Field(default_factory=dict)
    levels: list[HieraLevel] = Field(default_factory=list)
    total_data_files: int = 0


# ============================================================================
# Analysis Result Models (for workflow)
# ============================================================================


class ManifestAnalysisResult(BaseModel):
    """Manifest file analysis result."""

    file_path: str
    file_type: str = "manifest"
    analysis: ManifestExecutionAnalysis


class HieraDataAnalysisResult(BaseModel):
    """Hiera data file analysis result."""

    file_path: str
    hierarchy_level: str
    raw_content: str = ""
    analysis: HieraDataAnalysis


class TemplateAnalysisResult(BaseModel):
    """Template file analysis result."""

    file_path: str
    analysis: PuppetTemplateAnalysis


class CustomTypeAnalysisResult(BaseModel):
    """Custom type/provider/fact/function analysis result."""

    file_path: str
    component_type: str
    analysis: CustomTypeAnalysis


class CredentialAnalysisResult(BaseModel):
    """Credential detection result."""

    analysis: CredentialAnalysis


class PuppetStructuredAnalysis(BaseModel):
    """Aggregate of all analysis results from a Puppet module."""

    manifests: list[ManifestAnalysisResult] = Field(default_factory=list)
    hiera_data: list[HieraDataAnalysisResult] = Field(default_factory=list)
    templates: list[TemplateAnalysisResult] = Field(default_factory=list)
    custom_types: list[CustomTypeAnalysisResult] = Field(default_factory=list)

    def get_total_files_analyzed(self) -> int:
        return (
            len(self.manifests)
            + len(self.hiera_data)
            + len(self.templates)
            + len(self.custom_types)
        )

    @property
    def analyzed_file_paths(self) -> list[str]:
        files: list[str] = []
        files.extend(m.file_path for m in self.manifests)
        files.extend(h.file_path for h in self.hiera_data)
        files.extend(t.file_path for t in self.templates)
        files.extend(c.file_path for c in self.custom_types)
        return sorted(set(files))
