"""Build hierarchical execution tree from Puppet structured analysis.

This module builds a visual tree showing the complete class execution flow
with iterations expanded and resource details inline.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.utils.logging import get_logger

from .models import (
    ManifestAnalysisResult,
    PuppetStructuredAnalysis,
)

if TYPE_CHECKING:
    from .path_resolver import PuppetPathResolver

logger = get_logger(__name__)


# ============================================================================
# Execution Tree Node Hierarchy
# ============================================================================


@dataclass
class ExecutionTreeNode(ABC):
    """Base class for all execution tree nodes."""

    name: str
    file_path: str | None = None
    details: str | None = None
    children: list[ExecutionTreeNode] = field(default_factory=list)

    @property
    @abstractmethod
    def node_type(self) -> str: ...

    @abstractmethod
    def format_label(self) -> str: ...


@dataclass
class ClassNode(ExecutionTreeNode):
    """A Puppet class in the execution tree."""

    @property
    def node_type(self) -> str:
        return "class"

    def format_label(self) -> str:
        label = f"[class] {self.name}"
        if self.file_path:
            label += f"  # {self.file_path}"
        if self.details:
            label += f" ({self.details})"
        return label


@dataclass
class ResourceNode(ExecutionTreeNode):
    """A Puppet resource (package, file, service, exec, etc.)."""

    @property
    def node_type(self) -> str:
        return "resource"

    def format_label(self) -> str:
        return f"[resource] {self.name}"


@dataclass
class DefinedTypeNode(ExecutionTreeNode):
    """An expanded Puppet defined type instance."""

    @property
    def node_type(self) -> str:
        return "defined_type"

    def format_label(self) -> str:
        label = f"[defined_type] {self.name}"
        if self.file_path:
            label += f"  # {self.file_path}"
        if self.details:
            label += f" ({self.details})"
        return label


@dataclass
class IterationNode(ExecutionTreeNode):
    """A loop (.each, .map, etc.) in the execution tree."""

    @property
    def node_type(self) -> str:
        return "iteration"

    def format_label(self) -> str:
        return f"LOOP {self.name}"


@dataclass
class ConditionalNode(ExecutionTreeNode):
    """A conditional (if, unless, case) in the execution tree."""

    @property
    def node_type(self) -> str:
        return "conditional"

    def format_label(self) -> str:
        return f"[conditional] {self.name}"


@dataclass
class ExportedResourceNode(ExecutionTreeNode):
    """An exported resource (@@) shared via PuppetDB."""

    @property
    def node_type(self) -> str:
        return "exported"

    def format_label(self) -> str:
        return f"[exported @@] {self.name}"


@dataclass
class VirtualResourceNode(ExecutionTreeNode):
    """A virtual resource (@) realized conditionally."""

    @property
    def node_type(self) -> str:
        return "virtual"

    def format_label(self) -> str:
        return f"[virtual @] {self.name}"


@dataclass
class CollectorNode(ExecutionTreeNode):
    """A resource collector (<<| |>>)."""

    @property
    def node_type(self) -> str:
        return "collector"

    def format_label(self) -> str:
        return f"[collector <<| |>>] {self.name}"


@dataclass
class PuppetDBQueryNode(ExecutionTreeNode):
    """A PuppetDB query node."""

    @property
    def node_type(self) -> str:
        return "puppetdb_query"

    def format_label(self) -> str:
        return f"[puppetdb_query] {self.name}"


@dataclass
class RelationshipNode(ExecutionTreeNode):
    """An ordering/notification relationship chain."""

    @property
    def node_type(self) -> str:
        return "relationship"

    def format_label(self) -> str:
        return f"[ordering] {self.name}"


@dataclass
class FactNode(ExecutionTreeNode):
    """A Puppet fact reference."""

    @property
    def node_type(self) -> str:
        return "fact"

    def format_label(self) -> str:
        return f"[fact] {self.name}"


@dataclass
class TemplateNode(ExecutionTreeNode):
    """A template reference within a resource."""

    @property
    def node_type(self) -> str:
        return "template"

    def format_label(self) -> str:
        label = f"[template] {self.name}"
        if self.details:
            label += f" ({self.details})"
        return label


# ============================================================================
# Execution Tree Builder
# ============================================================================


class PuppetExecutionTreeBuilder:
    """Builds execution tree from Puppet manifest analysis results."""

    def __init__(
        self,
        structured_analysis: PuppetStructuredAnalysis,
        path_resolver: PuppetPathResolver | None = None,
    ):
        self.analysis = structured_analysis
        self.path_resolver = path_resolver
        self._visited: set[str] = set()

        self._manifest_map: dict[str, ManifestAnalysisResult] = {}
        for m in structured_analysis.manifests:
            if m.analysis.class_name:
                normalized = self._normalize_class_name(m.analysis.class_name)
                self._manifest_map[normalized] = m

    def build_tree(self, entry_class: str | None = None) -> ExecutionTreeNode:
        if entry_class is None:
            entry_class = self._find_entry_class()

        if entry_class is None:
            return ClassNode(
                name="(no entry class found)",
                details="No init.pp or main class detected",
            )

        logger.info(f"Building execution tree from {entry_class}")
        return self._expand_class(entry_class)

    def format_tree(
        self, node: ExecutionTreeNode, prefix: str = "", is_last: bool = True
    ) -> str:
        lines: list[str] = []
        connector = "└── " if is_last else "├── "
        if not prefix:
            connector = ""

        lines.append(f"{prefix}{connector}{node.format_label()}")

        for idx, child in enumerate(node.children):
            is_last_child = idx == len(node.children) - 1
            extension = "    " if is_last else "│   "
            child_prefix = prefix + extension
            lines.append(self.format_tree(child, child_prefix, is_last_child))

        return "\n".join(lines)

    def collect_file_paths(self, node: ExecutionTreeNode) -> set[str]:
        """Collect all file paths from execution tree nodes."""
        paths = set()

        if node.file_path:
            paths.add(node.file_path)

        for child in node.children:
            paths.update(self.collect_file_paths(child))

        return paths

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_class_name(self, class_name: str) -> str:
        return class_name.lstrip(":")

    def _find_entry_class(self) -> str | None:
        for m in self.analysis.manifests:
            if m.analysis.class_name and "init.pp" in m.file_path:
                return m.analysis.class_name
        if self.analysis.manifests and self.analysis.manifests[0].analysis.class_name:
            return self.analysis.manifests[0].analysis.class_name
        return None

    def _expand_class(self, class_name: str) -> ClassNode:
        normalized = self._normalize_class_name(class_name)

        if normalized in self._visited:
            return ClassNode(
                name=class_name,
                details="[CIRCULAR - already visited]",
            )

        self._visited.add(normalized)

        manifest = self._manifest_map.get(normalized)
        if manifest is None:
            details = "class not analyzed"
            if self.path_resolver:
                resolved = self.path_resolver.resolve_class(class_name)
                if resolved:
                    details = f"external class — {resolved}"
            return ClassNode(name=class_name, details=details)

        analysis = manifest.analysis
        node = ClassNode(name=class_name, file_path=manifest.file_path)

        if analysis.class_inherits:
            node.children.append(
                ClassNode(
                    name=f"inherits {analysis.class_inherits.parent_class}",
                    details=f"overrides: {', '.join(analysis.class_inherits.overridden_params)}"
                    if analysis.class_inherits.overridden_params
                    else None,
                )
            )

        node.children.extend(self._build_execution_nodes(analysis.execution_order))

        for chain in analysis.relationship_chains:
            node.children.append(RelationshipNode(name=chain))

        for fact in analysis.fact_references:
            node.children.append(FactNode(name=fact))

        return node

    def _expand_defined_type(self, defined_type: str, title: str) -> ExecutionTreeNode:
        normalized = self._normalize_class_name(defined_type)

        visit_key = f"{normalized}[{title}]"
        if visit_key in self._visited:
            return ResourceNode(
                name=f"{defined_type}[{title}]",
                details="[CIRCULAR - already visited]",
            )

        self._visited.add(visit_key)

        manifest = self._manifest_map.get(normalized)
        if manifest is None:
            return ResourceNode(
                name=f"{defined_type}[{title}]",
                details="defined type not analyzed",
            )

        analysis = manifest.analysis

        details = None
        if analysis.class_parameters:
            details = f"{len(analysis.class_parameters)} parameters"

        node = DefinedTypeNode(
            name=f"{defined_type}[{title}]",
            file_path=manifest.file_path,
            details=details,
        )

        node.children.extend(self._build_execution_nodes(analysis.execution_order))
        return node

    def _is_defined_type(self, resource_type: str) -> bool:
        normalized = self._normalize_class_name(resource_type)
        return normalized in self._manifest_map

    def _extract_template_reference(self, item) -> TemplateNode | None:
        if not hasattr(item, "attributes") or not item.attributes:
            return None

        template_attrs = ["content", "source"]
        for attr_name in template_attrs:
            if attr_name not in item.attributes:
                continue

            value = str(item.attributes[attr_name])
            for pattern in [
                r"(?:template|epp|erb|inline_epp)\(['\"]([^'\"]+)['\"]",
                r"(?:template|epp|erb|inline_epp)\('([^']+)'",
                r'(?:template|epp|erb|inline_epp)\("([^"]+)"',
            ]:
                match = re.search(pattern, value)
                if not match:
                    continue

                template_path = match.group(1)
                template_info = self._find_template_info(template_path)

                if template_info:
                    details = f"{len(template_info['variables'])} variables"
                    if template_info["logic"]:
                        details += f", {len(template_info['logic'])} logic blocks"
                else:
                    details = "template file"

                return TemplateNode(name=template_path, details=details)

        return None

    def _find_template_info(self, template_path: str) -> dict | None:
        if not self.analysis or not hasattr(self.analysis, "templates"):
            return None

        for template in self.analysis.templates:
            file_path = template.file_path

            template_filename = template_path.split("/")[-1]
            if template_filename in file_path and all(
                part in file_path for part in template_path.split("/")[:-1]
            ):
                return {
                    "file_path": file_path,
                    "variables": template.analysis.variables_used,
                    "logic": template.analysis.ruby_logic,
                }

            if template_path in file_path:
                return {
                    "file_path": file_path,
                    "variables": template.analysis.variables_used,
                    "logic": template.analysis.ruby_logic,
                }

        return None

    def _build_execution_nodes(self, execution_order: list) -> list[ExecutionTreeNode]:
        nodes: list[ExecutionTreeNode] = []

        for item in execution_order:
            if item.type == "resource":
                if item.resource_type and item.resource_type.lower() == "class":
                    child = self._expand_class(item.title)
                    nodes.append(child)
                elif item.resource_type and self._is_defined_type(item.resource_type):
                    child = self._expand_defined_type(item.resource_type, item.title)
                    nodes.append(child)
                else:
                    details_parts = [
                        f"{key}: {value}"
                        for key, value in (item.attributes or {}).items()
                    ]
                    detail = ", ".join(details_parts) if details_parts else None

                    resource_node = ResourceNode(
                        name=f"{item.resource_type}[{item.title}]",
                        details=detail,
                    )

                    template_child = self._extract_template_reference(item)
                    if template_child:
                        resource_node.children.append(template_child)

                    nodes.append(resource_node)

            elif item.type == "class_include":
                child = self._expand_class(item.class_name)
                nodes.append(child)

            elif item.type == "conditional":
                if hasattr(item, "execution_order"):
                    cond_node = ConditionalNode(
                        name=f"{item.condition_type} {item.condition}",
                    )
                    cond_node.children.extend(
                        self._build_execution_nodes(item.execution_order)
                    )
                    nodes.append(cond_node)

            elif item.type == "iteration":
                if hasattr(item, "execution_order"):
                    iter_node = IterationNode(
                        name=f"{item.collection_variable}.{item.iterator_type} |{item.item_variable}|",
                    )
                    iter_node.children.extend(
                        self._build_execution_nodes(item.execution_order)
                    )
                    nodes.append(iter_node)

            elif item.type == "exported_resource":
                nodes.append(
                    ExportedResourceNode(
                        name=f"{item.resource_type}[{item.title}]",
                    )
                )

            elif item.type == "virtual_resource":
                nodes.append(
                    VirtualResourceNode(
                        name=f"{item.resource_type}[{item.title}]",
                    )
                )

            elif item.type == "collector":
                nodes.append(
                    CollectorNode(
                        name=f"{item.resource_type} <| {item.query} |>",
                    )
                )

        return nodes
