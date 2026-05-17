"""Puppet analysis domain models.

This module defines Pydantic models for representing Puppet module analysis.
These are pure data structures used for LLM structured outputs.
"""

from typing import Any

from pydantic import BaseModel, Field

# ============================================================================
# Manifest Analysis Models
# ============================================================================


class PuppetResourceDeclaration(BaseModel):
    """A single Puppet resource declaration."""

    resource_type: str
    title: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class ClassInclude(BaseModel):
    """An include/contain/require of another class."""

    class_name: str
    relationship: str  # "include", "contain", "require"


class ClassInheritance(BaseModel):
    """Class inheritance via the 'inherits' keyword."""

    parent_class: str
    child_class: str
    overridden_params: list[str] = Field(default_factory=list)


class ConditionalBlock(BaseModel):
    """A conditional (if/unless/case/selector) in Puppet code."""

    condition: str
    condition_type: str  # "if", "unless", "case", "selector"
    resources: list[PuppetResourceDeclaration] = Field(default_factory=list)
    note: str | None = None


class IterationBlock(BaseModel):
    """An iteration construct (.each, .map, .filter, .reduce)."""

    iterator_type: str  # "each", "map", "filter", "reduce"
    collection_variable: str
    item_variable: str
    resources: list[PuppetResourceDeclaration] = Field(default_factory=list)
    note: str | None = None


class ManifestExecutionAnalysis(BaseModel):
    """LLM structured output for a single .pp manifest."""

    class_name: str | None = None
    class_parameters: dict[str, Any] = Field(default_factory=dict)
    class_inherits: ClassInheritance | None = None
    resources: list[PuppetResourceDeclaration] = Field(default_factory=list)
    class_includes: list[ClassInclude] = Field(default_factory=list)
    conditionals: list[ConditionalBlock] = Field(default_factory=list)
    iterations: list[IterationBlock] = Field(default_factory=list)
    exported_resources: list[PuppetResourceDeclaration] = Field(default_factory=list)
    virtual_resources: list[PuppetResourceDeclaration] = Field(default_factory=list)
    collectors: list[str] = Field(default_factory=list)
    puppetdb_queries: list[str] = Field(default_factory=list)
    relationship_chains: list[str] = Field(default_factory=list)


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
