"""Chef execution domain models.

This module defines Pydantic models for representing Chef recipe execution flow.
These are pure data structures (no business logic) used for LLM structured outputs.
"""

import json
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, Tag, field_validator


class ChefAttributePrecedence(StrEnum):
    """Actual Chef attribute precedence levels, in increasing order."""

    DEFAULT = "default"
    FORCE_DEFAULT = "force_default"
    NORMAL = "normal"
    OVERRIDE = "override"
    FORCE_OVERRIDE = "force_override"
    AUTOMATIC = "automatic"


CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER: tuple[ChefAttributePrecedence, ...] = tuple(
    precedence
    for precedence in ChefAttributePrecedence
    if precedence is not ChefAttributePrecedence.AUTOMATIC
)

# ============================================================================
# Execution Item Models
# ============================================================================


class ExecutionItem(BaseModel):
    """Base execution item."""


class AttributeAssignment(ExecutionItem):
    """Attribute assignment with its Chef precedence level."""

    type: Literal["attribute_assignment"] = "attribute_assignment"
    attribute_path: str
    precedence: ChefAttributePrecedence | None = None
    value: Any
    clears_precedence: bool = Field(
        default=False,
        description="True when the Chef assignment uses ! to clear a precedence level",
    )

    def format_label(self) -> str:
        """Format attribute assignment as tree label."""
        precedence = f": {self.precedence.value}" if self.precedence else ""
        reset = " (clears precedence)" if self.clears_precedence else ""
        return f"[attribute{precedence}] {self.attribute_path} = {self.value}{reset}"


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


class DataBagExecution(ExecutionItem):
    """Chef data bag lookup.

    Represents both listing a bag with data_bag(...) and loading an item with
    data_bag_item(...) or Chef::EncryptedDataBagItem.load(...).
    """

    type: Literal["data_bag"] = "data_bag"
    data_bag: str
    item_id: str | None = None
    encrypted: bool = False

    def format_label(self) -> str:
        label = f"[data_bag] {self.data_bag}"
        if self.item_id:
            label = f"{label}/{self.item_id}"
        if self.encrypted:
            return f"{label} (encrypted)"
        return label


# Discriminated union of all execution item types
# Uses the 'type' field to determine which model to instantiate
ExecutionItemUnion = Annotated[
    Annotated[AttributeAssignment, Tag("attribute_assignment")]
    | Annotated[ResourceExecution, Tag("resource")]
    | Annotated[ConditionalExecution, Tag("conditional")]
    | Annotated[CustomResourceExecution, Tag("custom_resource")]
    | Annotated[IncludeRecipeExecution, Tag("include_recipe")]
    | Annotated[DataBagExecution, Tag("data_bag")],
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


class ChefAttributeWrite(BaseModel):
    """One ordered assignment from a Chef cookbook attribute file."""

    precedence: ChefAttributePrecedence
    attribute_path: list[str] = Field(min_length=1)
    value: Any
    clears_precedence: bool = False

    @field_validator("precedence")
    @classmethod
    def validate_cookbook_precedence(
        cls, precedence: ChefAttributePrecedence
    ) -> ChefAttributePrecedence:
        """Reject runtime-only precedence in cookbook attribute files."""
        if precedence not in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER:
            raise ValueError("Cookbook attribute writes require a writable Chef level")
        return precedence


class ChefAttributesOutput(BaseModel):
    """Ordered Chef cookbook attribute writes extracted from one file."""

    assignments: list[ChefAttributeWrite] = Field(default_factory=list)

    @staticmethod
    def _path_parent(attributes: dict[str, Any], path: list[str]) -> dict[str, Any]:
        """Return the parent dictionary, creating missing path components."""
        current = attributes
        for component in path[:-1]:
            child = current.get(component)
            if not isinstance(child, dict):
                child = {}
                current[component] = child
            current = child
        return current

    @classmethod
    def write_path(
        cls, attributes: dict[str, Any], path: list[str], value: Any
    ) -> None:
        """Execute an ordinary Ruby assignment, replacing the value at its path."""
        parent = cls._path_parent(attributes, path)
        parent[path[-1]] = deepcopy(value)

    @staticmethod
    def remove_path(attributes: dict[str, Any], path: list[str]) -> None:
        """Remove a path and prune empty parent dictionaries."""
        parents = []
        current = attributes
        for component in path[:-1]:
            child = current.get(component)
            if not isinstance(child, dict):
                return
            parents.append((current, component, child))
            current = child
        if path[-1] not in current:
            return
        current.pop(path[-1])
        for parent, component, child in reversed(parents):
            if child:
                return
            parent.pop(component, None)

    @classmethod
    def merge_nested(
        cls, base: dict[str, Any], overriding: dict[str, Any]
    ) -> dict[str, Any]:
        """Merge precedence components recursively, replacing arrays and scalars."""
        merged = deepcopy(base)
        for key, value in overriding.items():
            current = merged.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key] = cls.merge_nested(current, value)
                continue
            merged[key] = deepcopy(value)
        return merged


class ChefAttributeResolution(BaseModel):
    """Resolved cookbook writes, retaining their surviving precedence components."""

    levels: dict[ChefAttributePrecedence, dict[str, Any]] = Field(
        default_factory=lambda: {
            level: {} for level in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER
        }
    )

    def apply(self, assignment: ChefAttributeWrite) -> None:
        """Apply Chef's component-specific bang resets, then assign the value."""
        if assignment.clears_precedence:
            for level in self._reset_levels(assignment.precedence):
                ChefAttributesOutput.remove_path(
                    self.levels[level], assignment.attribute_path
                )
        ChefAttributesOutput.write_path(
            self.levels[assignment.precedence],
            assignment.attribute_path,
            assignment.value,
        )

    @staticmethod
    def _reset_levels(
        level: ChefAttributePrecedence,
    ) -> tuple[ChefAttributePrecedence, ...]:
        """Only force bangs clear another cookbook precedence component."""
        if level is ChefAttributePrecedence.FORCE_DEFAULT:
            return (ChefAttributePrecedence.DEFAULT, level)
        if level is ChefAttributePrecedence.FORCE_OVERRIDE:
            return (ChefAttributePrecedence.OVERRIDE, level)
        return (level,)

    def merged_values(self) -> dict[str, Any]:
        """Return effective cookbook values in Chef precedence order."""
        merged: dict[str, Any] = {}
        for level in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER:
            merged = ChefAttributesOutput.merge_nested(merged, self.levels[level])
        return merged

    def values_by_target(self) -> dict[str, dict[str, Any]]:
        """Group namespace attributes by destination, keeping dictionaries intact."""
        higher_values: dict[str, Any] = {}
        for level in CHEF_COOKBOOK_ATTRIBUTE_PRECEDENCE_ORDER:
            if level in (
                ChefAttributePrecedence.DEFAULT,
                ChefAttributePrecedence.FORCE_DEFAULT,
            ):
                continue
            higher_values = ChefAttributesOutput.merge_nested(
                higher_values, self.levels[level]
            )
        groups: dict[str, dict[str, Any]] = {
            "defaults/main.yml": {},
            "vars/main.yml": {},
        }
        for namespace, value in self.merged_values().items():
            attributes = (
                value.items() if isinstance(value, dict) and value else [(None, value)]
            )
            for attribute, effective_value in attributes:
                path = [namespace] if attribute is None else [namespace, attribute]
                target = (
                    "vars/main.yml"
                    if self._has_path(higher_values, path)
                    else "defaults/main.yml"
                )
                ChefAttributesOutput.write_path(groups[target], path, effective_value)
        return groups

    @staticmethod
    def _has_path(values: dict[str, Any], path: list[str]) -> bool:
        current = values
        for key in path:
            if not isinstance(current, dict) or key not in current:
                return False
            current = current[key]
        return True

    def format_summary(self) -> str:
        """Expose effective values and their computed Ansible destinations."""
        return "COOKBOOK ATTRIBUTE VALUES BY ANSIBLE TARGET:\n" + json.dumps(
            self.values_by_target(), indent=2, sort_keys=True
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
    """Precedence-aware analysis result for one Chef attribute file."""

    file_type: str = "attributes"
    analysis: ChefAttributesOutput

    def format_summary(self) -> str:
        """Format ordered writes with their source file and Chef level."""
        return "\n".join(
            self._format_assignment(assignment)
            for assignment in self.analysis.assignments
        )

    def _format_assignment(self, assignment: ChefAttributeWrite) -> str:
        """Format one write without hiding its path or source order."""
        precedence = assignment.precedence.value
        if assignment.clears_precedence:
            precedence = f"{precedence}!"
        path = ".".join(assignment.attribute_path)
        value = json.dumps(assignment.value, sort_keys=True)
        return f"{self.file_path} [{precedence}] {path} = {value}"

    def referenced_files(self) -> list[str]:
        """Attributes don't reference other files."""
        return []


class DataBagItemAnalysis(BaseModel):
    """A Chef data bag item loaded from a JSON file."""

    data_bag: str
    item_id: str
    file_path: str
    encrypted: bool = False
    keys: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class StructuredAnalysis(BaseModel):
    """Aggregate of all structured analysis results from Chef cookbook.

    This model combines all analysis from recipes, providers, and attributes
    files into a single typed structure.
    """

    recipes: list[RecipeAnalysisResult] = Field(default_factory=list)
    providers: list[ProviderAnalysisResult] = Field(default_factory=list)
    attributes: list[AttributesAnalysisResult] = Field(default_factory=list)
    data_bags: list[DataBagItemAnalysis] = Field(default_factory=list)
    attribute_collections: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Map of collection attribute names to their item keys (for iteration expansion)",
    )

    def resolve_attributes(self) -> ChefAttributeResolution:
        """Resolve ordered cookbook writes without mutating extracted values."""
        resolution = ChefAttributeResolution()
        for attribute_file in self.attributes:
            for assignment in attribute_file.analysis.assignments:
                resolution.apply(assignment)
        return resolution

    def merged_attribute_values(self) -> dict[str, Any]:
        """Return effective values after cookbook assignments and precedence."""
        return self.resolve_attributes().merged_values()

    def format_attribute_summary(self) -> str:
        """Format ordered source writes and their authoritative resolved values."""
        summaries = [
            summary
            for attribute_file in self.attributes
            if (summary := attribute_file.format_summary())
        ]
        if not summaries:
            return ""
        return (
            "COOKBOOK ATTRIBUTE ASSIGNMENTS BY SOURCE AND PRECEDENCE:\n\n"
            + "\n\n".join(summaries)
            + "\n\n"
            + self.resolve_attributes().format_summary()
        )

    def get_total_files_analyzed(self) -> int:
        """Get total number of files analyzed."""
        return (
            len(self.recipes)
            + len(self.providers)
            + len(self.attributes)
            + len(self.data_bags)
        )

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
        files.extend(d.file_path for d in self.data_bags)

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
