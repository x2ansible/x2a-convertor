"""Build hierarchical execution tree from Puppet structured analysis.

This module builds a visual tree showing the complete class execution flow
with iterations expanded and resource details inline.
"""

from __future__ import annotations

from collections.abc import Callable
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


def _format_class(n: ExecutionTreeNode) -> str:
    label = f"[class] {n.name}"
    if n.file_path:
        label += f"  # {n.file_path}"
    if n.details:
        label += f" ({n.details})"
    return label


_LABEL_FORMATTERS: dict[str, Callable[[ExecutionTreeNode], str]] = {
    "class": _format_class,
    "resource": lambda n: f"[resource] {n.name}",
    "iteration": lambda n: f"LOOP {n.name}",
    "conditional": lambda n: f"[conditional] {n.name}",
    "exported": lambda n: f"[exported @@] {n.name}",
    "virtual": lambda n: f"[virtual @] {n.name}",
    "collector": lambda n: f"[collector <<| |>>] {n.name}",
    "puppetdb_query": lambda n: f"[puppetdb_query] {n.name}",
    "relationship": lambda n: f"[ordering] {n.name}",
    "fact": lambda n: f"[fact] {n.name}",
}


@dataclass
class ExecutionTreeNode:
    """Node in the Puppet execution tree."""

    node_type: (
        str  # "class", "resource", "iteration", "conditional", "exported", "virtual"
    )
    name: str
    file_path: str | None = None
    details: str | None = None
    children: list[ExecutionTreeNode] = field(default_factory=list)

    def format_label(self) -> str:
        formatter = _LABEL_FORMATTERS.get(self.node_type)
        if formatter:
            return formatter(self)
        return f"{self.name} ({self.details})" if self.details else self.name


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
                self._manifest_map[m.analysis.class_name] = m

    def build_tree(self, entry_class: str | None = None) -> ExecutionTreeNode:
        if entry_class is None:
            entry_class = self._find_entry_class()

        if entry_class is None:
            return ExecutionTreeNode(
                node_type="class",
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

    def _find_entry_class(self) -> str | None:
        for m in self.analysis.manifests:
            if m.analysis.class_name and "init.pp" in m.file_path:
                return m.analysis.class_name
        if self.analysis.manifests and self.analysis.manifests[0].analysis.class_name:
            return self.analysis.manifests[0].analysis.class_name
        return None

    def _expand_class(self, class_name: str) -> ExecutionTreeNode:
        if class_name in self._visited:
            return ExecutionTreeNode(
                node_type="class",
                name=class_name,
                details="[CIRCULAR - already visited]",
            )

        self._visited.add(class_name)

        manifest = self._manifest_map.get(class_name)
        if manifest is None:
            details = "class not analyzed"
            if self.path_resolver:
                resolved = self.path_resolver.resolve_class(class_name)
                if resolved:
                    details = f"external class — {resolved}"
            return ExecutionTreeNode(
                node_type="class",
                name=class_name,
                details=details,
            )

        analysis = manifest.analysis
        node = ExecutionTreeNode(
            node_type="class",
            name=class_name,
            file_path=manifest.file_path,
        )

        if analysis.class_inherits:
            node.children.append(
                ExecutionTreeNode(
                    node_type="class",
                    name=f"inherits {analysis.class_inherits.parent_class}",
                    details=f"overrides: {', '.join(analysis.class_inherits.overridden_params)}"
                    if analysis.class_inherits.overridden_params
                    else None,
                )
            )

        node.children.extend(self._build_execution_nodes(analysis.execution_order))

        if analysis.relationship_chains:
            for chain in analysis.relationship_chains:
                node.children.append(
                    ExecutionTreeNode(node_type="relationship", name=chain)
                )

        if analysis.fact_references:
            for fact in analysis.fact_references:
                node.children.append(ExecutionTreeNode(node_type="fact", name=fact))

        return node

    def _build_execution_nodes(self, execution_order: list) -> list[ExecutionTreeNode]:
        """Build tree nodes from execution order list."""
        nodes: list[ExecutionTreeNode] = []

        for item in execution_order:
            if item.type == "resource":
                details_parts = []
                for key in ["ensure", "action", "command", "source"]:
                    if key in item.attributes:
                        details_parts.append(f"{key}: {item.attributes[key]}")
                detail = ", ".join(details_parts) if details_parts else None

                nodes.append(
                    ExecutionTreeNode(
                        node_type="resource",
                        name=f"{item.resource_type}[{item.title}]",
                        details=detail,
                    )
                )

            elif item.type == "class_include":
                child = self._expand_class(item.class_name)
                nodes.append(child)

            elif item.type == "conditional":
                cond_node = ExecutionTreeNode(
                    node_type="conditional",
                    name=f"{item.condition_type} {item.condition}",
                )
                cond_node.children.extend(
                    self._build_execution_nodes(item.execution_order)
                )
                nodes.append(cond_node)

            elif item.type == "iteration":
                iter_node = ExecutionTreeNode(
                    node_type="iteration",
                    name=f"{item.collection_variable}.{item.iterator_type} |{item.item_variable}|",
                )
                iter_node.children.extend(
                    self._build_execution_nodes(item.execution_order)
                )
                nodes.append(iter_node)

            elif item.type == "exported_resource":
                nodes.append(
                    ExecutionTreeNode(
                        node_type="exported",
                        name=f"{item.resource_type}[{item.title}]",
                    )
                )

            elif item.type == "virtual_resource":
                nodes.append(
                    ExecutionTreeNode(
                        node_type="virtual",
                        name=f"{item.resource_type}[{item.title}]",
                    )
                )

            elif item.type == "collector":
                nodes.append(
                    ExecutionTreeNode(
                        node_type="collector",
                        name=f"{item.resource_type} <| {item.query} |>",
                    )
                )

        return nodes
