"""Chef execution domain models.

This module defines Pydantic models for representing Chef recipe execution flow.
These are pure data structures (no business logic) used for LLM structured outputs.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag

# ============================================================================
# Execution Item Models
# ============================================================================


class ExecutionItem(BaseModel):
    """Base execution item."""


class AttributeAssignment(ExecutionItem):
    """Attribute assignment (node.default['key'] = value)."""

    type: Literal["attribute_assignment"] = "attribute_assignment"
    attribute_path: str
    value: Any

    def format_label(self) -> str:
        """Format attribute assignment as tree label."""
        return f"[attribute] {self.attribute_path} = {self.value}"


class ResourceExecution(ExecutionItem):
    """Standard Chef resource (package, service, directory, etc.)."""

    type: Literal["resource"] = "resource"
    resource_type: str
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None

    def format_label(self) -> str:
        """Format resource as tree label."""
        label = f"[resource] {self.resource_type}[{self.name}]"

        # Show important attributes
        details_parts = []
        for key in ["source", "action", "command", "path"]:
            if key in self.attributes:
                details_parts.append(f"{key}: {self.attributes[key]}")

        if details_parts:
            return f"{label} ({', '.join(details_parts)})"
        return label


class ConditionalExecution(ExecutionItem):
    """Conditional block (if/unless/case) with nested execution."""

    type: Literal["conditional"] = "conditional"
    condition: str
    execution_order: list["ExecutionItemUnion"] = Field(default_factory=list)
    note: str | None = None

    def format_label(self) -> str:
        """Format conditional as tree label."""
        return f"if {self.condition} (Conditional execution)"


class CustomResourceExecution(ExecutionItem):
    """Custom resource (LWRP) with provider analysis."""

    type: Literal["custom_resource"] = "custom_resource"
    resource_type: str
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    provider_path: str | None = None

    def format_label(self) -> str:
        """Format custom resource as tree label."""
        label = f"[custom_resource] {self.resource_type}[{self.name}]"
        if self.provider_path:
            return f"{label} (provider: {self.provider_path})"
        return label


class RecipeChildNode(BaseModel):
    """Child recipe node (from include_recipe)."""

    recipe_path: str
    recipe_name: str
    execution_order: list["ExecutionItemUnion"] = Field(default_factory=list)


class IncludeRecipeExecution(ExecutionItem):
    """Include recipe statement with child node."""

    type: Literal["include_recipe"] = "include_recipe"
    recipe_name: str
    child_node: RecipeChildNode | None = None
    note: str | None = None

    def format_label(self) -> str:
        """Format include_recipe as tree label."""
        return f"include_recipe {self.recipe_name}"


# Discriminated union of all execution item types
# Uses the 'type' field to determine which model to instantiate
ExecutionItemUnion = Annotated[
    Annotated[AttributeAssignment, Tag("attribute_assignment")]
    | Annotated[ResourceExecution, Tag("resource")]
    | Annotated[ConditionalExecution, Tag("conditional")]
    | Annotated[CustomResourceExecution, Tag("custom_resource")]
    | Annotated[IncludeRecipeExecution, Tag("include_recipe")],
    Discriminator("type"),
]


# ============================================================================
# LLM Structured Outputs
# ============================================================================


class RecipeExecutionAnalysis(BaseModel):
    """LLM output for recipe execution analysis."""

    execution_order: list[ExecutionItemUnion] = Field(
        default_factory=list, description="List of execution items in sequence order"
    )


class ProviderAnalysisOutput(BaseModel):
    """LLM output for provider analysis."""

    unconditional_templates: list[dict[str, Any]] = Field(
        default_factory=list, description="Templates created unconditionally"
    )
    conditionals: list[dict[str, Any]] = Field(
        default_factory=list, description="Conditional branches with templates"
    )


class DefaultAttributesOutput(BaseModel):
    """LLM output for default attributes extraction."""

    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted default attribute values as nested dict",
    )
    platform_specific_notes: list[str] = Field(
        default_factory=list, description="Notes about platform-specific attributes"
    )


# ============================================================================
# Analysis Result Models (for workflow)
# ============================================================================


class AnalyzedFile(BaseModel):
    """Base model for individual file analysis result."""

    file_path: str
    file_type: str  # "recipe" | "provider" | "attributes"


class RecipeAnalysisResult(AnalyzedFile):
    """Recipe file analysis with execution order."""

    file_type: str = "recipe"
    analysis: RecipeExecutionAnalysis

    def referenced_files(self) -> list[str]:
        """Extract template and cookbook_file references from recipe execution."""
        files = []
        self._extract_from_execution_order(self.analysis.execution_order, files)

        # Prefix with cookbook directory (parent of recipes/)
        cookbook_dir = str(Path(self.file_path).parent.parent)
        return [f"{cookbook_dir}/{f}" for f in files]

    def _extract_from_execution_order(
        self, execution_order: list[ExecutionItemUnion], files: list
    ) -> None:
        """Recursively extract file references from execution order."""
        for item in execution_order:
            if isinstance(item, ResourceExecution):
                source = item.attributes.get("source")
                if source and isinstance(source, str):
                    # Skip dynamic expressions
                    if "node[" in source or "#{" in source:
                        continue
                    if item.resource_type == "template":
                        files.append(f"templates/default/{source}")
                    elif item.resource_type == "cookbook_file":
                        files.append(f"files/default/{source}")

            elif isinstance(item, ConditionalExecution):
                self._extract_from_execution_order(item.execution_order, files)


class ProviderAnalysisResult(AnalyzedFile):
    """Provider file analysis with templates and conditionals."""

    file_type: str = "provider"
    analysis: ProviderAnalysisOutput

    def referenced_files(self) -> list[str]:
        """Extract template references from provider analysis."""
        files = []

        for template in self.analysis.unconditional_templates:
            if "source" in template:
                files.append(template["source"])

        for conditional in self.analysis.conditionals:
            for template in conditional.get("templates", []):
                if "source" in template:
                    files.append(template["source"])

        # Prefix with cookbook directory (parent of providers/)
        cookbook_dir = str(Path(self.file_path).parent.parent)
        return [f"{cookbook_dir}/{f}" for f in files]


class AttributesAnalysisResult(AnalyzedFile):
    """Attributes file analysis with default values."""

    file_type: str = "attributes"
    analysis: DefaultAttributesOutput

    def referenced_files(self) -> list[str]:
        """Attributes don't reference other files."""
        return []


class StructuredAnalysis(BaseModel):
    """Aggregate of all structured analysis results from Chef cookbook.

    This model combines all analysis from recipes, providers, and attributes
    files into a single typed structure.
    """

    recipes: list[RecipeAnalysisResult] = Field(default_factory=list)
    providers: list[ProviderAnalysisResult] = Field(default_factory=list)
    attributes: list[AttributesAnalysisResult] = Field(default_factory=list)
    attribute_collections: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of collection attribute names to their item keys (for iteration expansion)",
    )

    def get_total_files_analyzed(self) -> int:
        """Get total number of files analyzed."""
        return len(self.recipes) + len(self.providers) + len(self.attributes)

    @property
    def analyzed_file_paths(self) -> list[str]:
        """Get all file paths including analyzed files and referenced templates.

        Returns analyzed files plus templates/cookbook_files referenced in execution.
        """
        files = []

        # Add analyzed file paths
        files.extend(r.file_path for r in self.recipes)
        files.extend(p.file_path for p in self.providers)
        files.extend(a.file_path for a in self.attributes)

        # Add referenced files from each analysis result
        files.extend(f for r in self.recipes for f in r.referenced_files())
        files.extend(f for p in self.providers for f in p.referenced_files())
        files.extend(f for a in self.attributes for f in a.referenced_files())

        return sorted(set(files))


# ============================================================================
# Execution Tree Models (for visual tree display)
# ============================================================================


class ExecutionNode(BaseModel):
    """Node in the execution tree showing recipe flow and resources.

    ExecutionNode wraps typed execution items and delegates formatting to them.
    This enables each node type to provide its own label formatting with full
    context (e.g., recipe nodes include complete file paths for LLM accuracy).

    Attributes:
        node_type: Type of node (recipe, resource, loop, custom_resource, loop_item, conditional)
        name: Display name for this node
        file_path: Optional file path (primarily for recipe nodes)
        children: Child nodes in execution order
        execution_item: Wrapped typed item (ResourceExecution, ConditionalExecution, etc.)
        recipe_result: Wrapped recipe analysis result (for recipe nodes)
        attributes: Attribute dictionary (for loop_item nodes)
        details: Additional metadata (for error messages and loop info)
    """

    node_type: str
    name: str
    file_path: str | None = None
    children: list["ExecutionNode"] = Field(default_factory=list)

    # References to original typed items
    execution_item: ExecutionItemUnion | None = (
        None  # For resource, conditional, custom_resource
    )
    recipe_result: "RecipeAnalysisResult | None" = None  # For recipe nodes

    # Fields for loop nodes and error placeholders
    attributes: dict[str, Any] = Field(default_factory=dict)
    details: str | None = None

    def format_label(self) -> str:
        """Format this node as a display label, delegating to wrapped items when available."""
        # Delegate to execution_item if available (resources, conditionals, custom_resources)
        if self.execution_item:
            return self.execution_item.format_label()

        # Recipe nodes with recipe_result can include full file path
        if self.node_type == "recipe":
            base_label = f"{self.name} {self.details}" if self.details else self.name
            # Include file path for LLM context (so it uses exact paths in migration plans)
            if self.recipe_result and self.recipe_result.file_path:
                return f"{base_label}  # {self.recipe_result.file_path}"
            if self.file_path:
                return f"{base_label}  # {self.file_path}"
            return base_label

        # Loop nodes
        if self.node_type == "loop":
            return f"LOOP over {self.name} ({len(self.children)} items)"

        # Loop item nodes
        if self.node_type == "loop_item":
            label = self.name
            if self.attributes:
                # Format attributes inline (first 3 items)
                attrs_str = ", ".join(
                    f"{k}: {v!r}" for k, v in list(self.attributes.items())[:3]
                )
                label += f" {{{attrs_str}}}"
            return label

        # Fallback for unknown types
        return f"{self.name} ({self.details})" if self.details else self.name
