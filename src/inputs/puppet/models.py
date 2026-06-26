"""Puppet analysis domain models.

This module defines Pydantic models for representing Puppet module analysis.
These are pure data structures used for LLM structured outputs.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# ============================================================================
# Dependency Models
# ============================================================================


class PuppetDependency(BaseModel):
    """A Puppet module dependency from Puppetfile."""

    name: str = Field(description="Module name (e.g., 'puppetlabs-stdlib')")
    source: Literal["git", "forge"] = Field(description="Source type")
    version: str = Field(default="", description="Version string or git ref")
    url: str = Field(default="", description="Git URL (empty for forge)")
    path: str = Field(
        default="", description="Filesystem path where dependency was downloaded"
    )

    @property
    def is_forge(self) -> bool:
        return self.source == "forge"

    @property
    def is_git(self) -> bool:
        return self.source == "git"


class PuppetDependencyList(BaseModel):
    """Wrapper for LLM structured output of multiple dependencies."""

    dependencies: list[PuppetDependency] = Field(
        default_factory=list,
        description="List of Puppet module dependencies parsed from Puppetfile",
    )


# ============================================================================
# Execution Item Models (Bedrock-compatible - no circular references)
# ============================================================================


class NestedExecutionItem(BaseModel):
    """Single Puppet resource or declaration inside a conditional or iteration block.

    Separate from ExecutionItem to avoid circular references which Bedrock doesn't support.
    This level cannot contain further nesting. Populate only the fields relevant to the type.
    """

    type: str = Field(
        description='Item type: "resource", "class_include", "exported_resource", "virtual_resource", or "collector"'
    )

    resource_type: str | None = Field(
        default=None,
        description="Puppet resource type (e.g., 'file', 'package', 'service'). Set for resource/exported_resource/virtual_resource/collector types",
    )
    title: str | None = Field(
        default=None,
        description="Resource title or namevar (e.g., '/etc/nginx/nginx.conf'). Set for resource types",
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Resource attributes as key-value pairs (e.g., {'ensure': 'present', 'mode': '0644'})",
    )

    class_name: str | None = Field(
        default=None,
        description="Fully qualified Puppet class name (e.g., 'apache::mod::ssl'). Set for class_include type",
    )
    relationship: str | None = Field(
        default=None,
        description="Relationship keyword: 'include', 'require', 'contain', or 'class'",
    )

    query: str | None = Field(
        default=None,
        description="Collector query expression (e.g., 'tag == production'). Set for collector type",
    )

    note: str | None = Field(
        default=None,
        description="Additional context about this item when the resource has non-obvious behavior",
    )


class ExecutionItem(BaseModel):
    """Single execution step in a Puppet manifest.

    Uses a type discriminator with optional fields instead of discriminated unions
    to maintain Bedrock compatibility (Bedrock doesn't support oneOf).
    Populate only the fields relevant to the given type.
    """

    type: str = Field(
        description='Item type: "resource", "class_include", "conditional", "iteration", "exported_resource", "virtual_resource", or "collector"'
    )

    resource_type: str | None = Field(
        default=None,
        description="Puppet resource type (e.g., 'file', 'package', 'service'). Set for resource/exported_resource/virtual_resource/collector types",
    )
    title: str | None = Field(
        default=None,
        description="Resource title or namevar (e.g., '/etc/nginx/nginx.conf'). Set for resource types",
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Resource attributes as key-value pairs (e.g., {'ensure': 'present', 'mode': '0644'})",
    )

    class_name: str | None = Field(
        default=None,
        description="Fully qualified Puppet class name (e.g., 'apache::mod::ssl'). Set for class_include type",
    )
    relationship: str | None = Field(
        default=None,
        description="Relationship keyword: 'include', 'require', 'contain', or 'class'",
    )

    condition: str | None = Field(
        default=None,
        description="Condition expression (e.g., '$::osfamily == RedHat'). Set for conditional type",
    )
    condition_type: str | None = Field(
        default=None,
        description="Conditional keyword: 'if', 'unless', 'case', or 'selector'",
    )

    iterator_type: str | None = Field(
        default=None,
        description="Iterator function: 'each', 'map', 'filter', or 'reduce'. Set for iteration type",
    )
    collection_variable: str | None = Field(
        default=None,
        description="Variable or expression being iterated over (e.g., '$packages')",
    )
    item_variable: str | None = Field(
        default=None,
        description="Loop variable name bound to each element (e.g., '$pkg')",
    )

    query: str | None = Field(
        default=None,
        description="Collector query expression (e.g., 'tag == production'). Set for collector type",
    )

    execution_order: list[NestedExecutionItem] = Field(
        default_factory=list,
        description="Nested execution items inside this block. Used for conditional and iteration types",
    )

    note: str | None = Field(
        default=None,
        description="Additional context about this item when the resource has non-obvious behavior",
    )

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
    """Puppet class inheritance relationship via the 'inherits' keyword."""

    parent_class: str = Field(
        description="Fully qualified name of the parent class being inherited from"
    )
    child_class: str = Field(
        description="Fully qualified name of the child class that inherits"
    )
    overridden_params: list[str] = Field(
        default_factory=list,
        description="Parameter names from the parent class that the child overrides",
    )


class ManifestExecutionAnalysis(BaseModel):
    """Execution analysis of a single Puppet .pp manifest file.

    Captures the class declaration, its parameters, inheritance, and the
    sequential execution order of all resources and control structures.
    """

    class_name: str = Field(
        default="",
        description="Fully qualified Puppet class or defined type name (e.g., 'apache::vhost'). Empty if the manifest has no class declaration",
    )
    class_parameters: dict[str, str] = Field(
        default_factory=dict,
        description="Class parameters as name-to-default-value pairs (e.g., {'port': '80', 'docroot': '/var/www'})",
    )
    class_inherits: ClassInheritance | None = Field(
        default=None,
        description="Inheritance relationship if the class uses 'inherits'. Null if no inheritance",
    )
    execution_order: list[ExecutionItem] = Field(
        default_factory=list,
        description="All resources and control structures in the order they appear in the manifest",
    )
    puppetdb_queries: list[str] = Field(
        default_factory=list,
        description="PuppetDB query expressions found in the manifest (e.g., puppetdb_query() calls)",
    )
    relationship_chains: list[str] = Field(
        default_factory=list,
        description="Resource ordering chains using -> or ~> notation (e.g., 'Package[nginx] -> Service[nginx]')",
    )
    fact_references: list[str] = Field(
        default_factory=list,
        description="Facter fact variables referenced in the manifest (e.g., '$::osfamily', '$facts[os][family]')",
    )


# ============================================================================
# Hiera Data Analysis Models
# ============================================================================


class HieraVariableMapping(BaseModel):
    """Mapping of a single Hiera data key to its Ansible equivalent."""

    puppet_key: str = Field(
        description="Hiera lookup key (e.g., 'apache::port', 'profile::base::packages')"
    )
    value_type: str = Field(
        description='Data type of the value: "string", "hash", "array", "integer", or "boolean"'
    )
    is_encrypted: bool = Field(
        default=False,
        description="Whether the value is encrypted with hiera-eyaml (ENC[...] wrapper)",
    )
    ansible_target: str = Field(
        default="",
        description="Suggested Ansible variable file or location (e.g., 'group_vars/all', 'host_vars/webserver')",
    )
    ansible_variable_name: str = Field(
        default="",
        description="Suggested Ansible variable name (e.g., 'apache_port', 'base_packages')",
    )


class HieraDataAnalysis(BaseModel):
    """Analysis of a single Hiera YAML data file.

    Extracts all key-value pairs, their types, merge strategies,
    and maps them to Ansible variable equivalents.
    """

    variables: list[HieraVariableMapping] = Field(
        default_factory=list,
        description="All Hiera key-value pairs found in this data file with their Ansible mappings",
    )
    merge_behavior: dict[str, Any] = Field(
        default_factory=dict,
        description="Merge strategy declarations (e.g., {'lookup_options': {'merge': 'deep'}})",
    )
    lookup_options: dict[str, Any] = Field(
        default_factory=dict,
        description="Hiera lookup_options block if present, defining per-key merge and convert behavior",
    )
    cross_level_overrides: list[str] = Field(
        default_factory=list,
        description="Keys in this file that override values from a different hierarchy level",
    )
    notes: str = Field(
        default="",
        description="Additional observations about the data file (e.g., unusual patterns, migration concerns)",
    )


# ============================================================================
# Template Analysis Models
# ============================================================================


class PuppetTemplateAnalysis(BaseModel):
    """Analysis of a Puppet ERB (.erb) or EPP (.epp) template file.

    Extracts variables, logic blocks, and Hiera lookups to inform
    the conversion to Ansible Jinja2 templates.
    """

    template_type: str = Field(
        description='Template format: "erb" for Ruby ERB templates or "epp" for Puppet EPP templates'
    )
    variables_used: list[str] = Field(
        default_factory=list,
        description="Variable names referenced in the template (e.g., '@port', '$apache::docroot')",
    )
    hiera_lookups: list[str] = Field(
        default_factory=list,
        description="Hiera lookup calls found in the template (e.g., 'hiera(\"apache::port\")')",
    )
    loops: list[str] = Field(
        default_factory=list,
        description="Loop constructs as descriptive strings (e.g., 'each over @vhosts')",
    )
    ruby_logic: list[str] = Field(
        default_factory=list,
        description="Complex Ruby/Puppet logic blocks that need manual conversion (e.g., case statements, method calls)",
    )
    jinja2_equivalent_notes: str = Field(
        default="",
        description="Suggested Jinja2 equivalents or migration notes for complex template logic",
    )


# ============================================================================
# Custom Type/Provider/Fact Analysis Models
# ============================================================================


class CustomTypeAnalysis(BaseModel):
    """Analysis of a Puppet custom type, provider, fact, or function.

    Captures the component's interface and suggests the corresponding
    Ansible mechanism (built-in module, custom module, or plugin).
    """

    component_type: str = Field(
        description='Kind of Puppet component: "type", "provider", "fact", or "function"'
    )
    name: str = Field(
        description="Component name as declared in Puppet (e.g., 'myapp_config', 'concat')"
    )
    parameters: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Parameter definitions with keys 'name', 'type', and optionally 'default' and 'description'",
    )
    ansible_equivalent: str = Field(
        default="",
        description="Suggested Ansible module or plugin that provides equivalent functionality (e.g., 'ansible.builtin.template')",
    )
    requires_custom_module: bool = Field(
        default=False,
        description="Whether this component has no Ansible equivalent and requires writing a custom module",
    )
    note: str | None = Field(
        default=None,
        description="Additional migration context or caveats for this component",
    )


# ============================================================================
# Credential Analysis Models
# ============================================================================


class CredentialEntry(BaseModel):
    """A single detected credential or secret in a Puppet module."""

    purpose: str = Field(
        description="What this credential is used for (e.g., 'database root password', 'SSL certificate key')"
    )
    variable_names: list[str] = Field(
        default_factory=list,
        description="Puppet variable names that hold this credential (e.g., ['$db_password', '$mysql::root_pw'])",
    )
    source_files: list[str] = Field(
        default_factory=list,
        description="File paths where this credential is defined or referenced",
    )
    storage_method: str = Field(
        description='How the credential is stored: "eyaml", "hiera plaintext", "exec", or "file source"'
    )
    usage_context: str = Field(
        description="How and where the credential is consumed (e.g., 'passed to mysql::server class as root_password')"
    )
    ansible_recommendation: str = Field(
        description='Suggested Ansible secret management approach: "ansible-vault", "CyberArk lookup", or "env var"'
    )


class CredentialAnalysis(BaseModel):
    """Credential and secret detection results for a Puppet module.

    Identifies all credentials, secrets, and sensitive data in the module
    along with their storage methods and Ansible migration recommendations.
    """

    credentials: list[CredentialEntry] = Field(
        default_factory=list,
        description="All credentials and secrets detected in the module",
    )
    provider_info: str = Field(
        default="",
        description="External secret provider details if applicable (e.g., 'HashiCorp Vault via hiera-vault backend')",
    )
    total_detected: int = Field(
        default=0,
        description="Total number of distinct credentials detected",
    )


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
