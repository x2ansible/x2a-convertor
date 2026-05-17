"""Build hierarchical execution tree from Puppet structured analysis.

This module builds a visual tree showing the complete class execution flow
with iterations expanded and resource details inline.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from src.utils.logging import get_logger

from .models import (
    ManifestAnalysisResult,
    ManifestExecutionAnalysis,
    PuppetStructuredAnalysis,
)

logger = get_logger(__name__)


def _format_class(n: "ExecutionTreeNode") -> str:
    label = f"[class] {n.name}"
    if n.file_path:
        label += f"  # {n.file_path}"
    if n.details:
        label += f" ({n.details})"
    return label


_LABEL_FORMATTERS: dict[str, Callable[["ExecutionTreeNode"], str]] = {
    "class": _format_class,
    "resource": lambda n: f"[resource] {n.name}",
    "iteration": lambda n: f"LOOP {n.name}",
    "conditional": lambda n: f"[conditional] {n.name}",
    "exported": lambda n: f"[exported @@] {n.name}",
    "virtual": lambda n: f"[virtual @] {n.name}",
    "relationship": lambda n: f"[ordering] {n.name}",
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
    children: list["ExecutionTreeNode"] = field(default_factory=list)

    def format_label(self) -> str:
        formatter = _LABEL_FORMATTERS.get(self.node_type)
        if formatter:
            return formatter(self)
        return f"{self.name} ({self.details})" if self.details else self.name


class PuppetExecutionTreeBuilder:
    """Builds execution tree from Puppet manifest analysis results."""

    def __init__(self, structured_analysis: PuppetStructuredAnalysis):
        self.analysis = structured_analysis
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
            return ExecutionTreeNode(
                node_type="class",
                name=class_name,
                details="class not analyzed",
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

        node.children.extend(self._build_resource_nodes(analysis))

        for include in analysis.class_includes:
            child = self._expand_class(include.class_name)
            node.children.append(child)

        if analysis.relationship_chains:
            for chain in analysis.relationship_chains:
                node.children.append(
                    ExecutionTreeNode(node_type="relationship", name=chain)
                )

        return node

    def _build_resource_nodes(
        self, analysis: ManifestExecutionAnalysis
    ) -> list[ExecutionTreeNode]:
        nodes: list[ExecutionTreeNode] = []

        for res in analysis.resources:
            details_parts = []
            for key in ["ensure", "action", "command", "source"]:
                if key in res.attributes:
                    details_parts.append(f"{key}: {res.attributes[key]}")
            detail = ", ".join(details_parts) if details_parts else None

            nodes.append(
                ExecutionTreeNode(
                    node_type="resource",
                    name=f"{res.resource_type}[{res.title}]",
                    details=detail,
                )
            )

        for cond in analysis.conditionals:
            cond_node = ExecutionTreeNode(
                node_type="conditional",
                name=f"{cond.condition_type} {cond.condition}",
            )
            for res in cond.resources:
                cond_node.children.append(
                    ExecutionTreeNode(
                        node_type="resource",
                        name=f"{res.resource_type}[{res.title}]",
                    )
                )
            nodes.append(cond_node)

        for iteration in analysis.iterations:
            iter_node = ExecutionTreeNode(
                node_type="iteration",
                name=f"{iteration.collection_variable}.{iteration.iterator_type} |{iteration.item_variable}|",
            )
            for res in iteration.resources:
                iter_node.children.append(
                    ExecutionTreeNode(
                        node_type="resource",
                        name=f"{res.resource_type}[{res.title}]",
                    )
                )
            nodes.append(iter_node)

        for exp in analysis.exported_resources:
            nodes.append(
                ExecutionTreeNode(
                    node_type="exported",
                    name=f"{exp.resource_type}[{exp.title}]",
                )
            )

        for virt in analysis.virtual_resources:
            nodes.append(
                ExecutionTreeNode(
                    node_type="virtual",
                    name=f"{virt.resource_type}[{virt.title}]",
                )
            )

        return nodes
