"""Build hierarchical execution tree from Chef structured analysis.

This module builds a visual tree showing the complete recipe execution flow
with loops expanded and attribute values inline.
"""

from pathlib import Path

from src.utils.logging import get_logger

from .models import (
    ConditionalExecution,
    CustomResourceExecution,
    ExecutionItemUnion,
    ExecutionNode,
    IncludeRecipeExecution,
    RecipeAnalysisResult,
    ResourceExecution,
    StructuredAnalysis,
)
from .path_resolver import ChefPathResolver

logger = get_logger(__name__)


class ExecutionTreeBuilder:
    """Builds hierarchical execution tree from structured analysis."""

    def __init__(
        self,
        structured_analysis: StructuredAnalysis,
        path_resolver: ChefPathResolver,
        dependency_paths: list[str],
    ):
        self.analysis = structured_analysis
        self.path_resolver = path_resolver
        self.dependency_paths = dependency_paths
        self.visited_recipes = set()  # Prevent circular includes

        # Build recipe lookup map
        self.recipe_map = {}
        for recipe_result in structured_analysis.recipes:
            self.recipe_map[recipe_result.file_path] = recipe_result

    def build_tree(self, entry_recipe_path: str) -> ExecutionNode:
        """Build execution tree starting from entry recipe."""
        logger.info(f"Building execution tree from {entry_recipe_path}")

        # Find the entry recipe in analyzed recipes
        if entry_recipe_path not in self.recipe_map:
            logger.warning(f"Entry recipe not found in analysis: {entry_recipe_path}")
            return ExecutionNode(
                node_type="recipe",
                name=entry_recipe_path,
                details="Recipe not found in analysis",
            )

        return self._expand_recipe(entry_recipe_path)

    def _get_recipe_display_name(self, recipe_path: str) -> str:
        """Extract a meaningful display name from recipe path.

        Examples:
            /path/cookbooks/nginx/recipes/default.rb -> nginx::default
            /path/cookbook_artifacts/memcached-hash/recipes/default.rb -> memcached::default
            /path/cookbooks/cache/recipes/security.rb -> cache::security
        """
        path_obj = Path(recipe_path)
        recipe_name = path_obj.stem

        # Extract cookbook name from path
        path_parts = path_obj.parts
        cookbook_name = None

        for i, part in enumerate(path_parts):
            if part in ("cookbooks", "cookbook_artifacts") and i + 1 < len(path_parts):
                cookbook_part = path_parts[i + 1]
                # Handle cookbook_artifacts naming: cookbook-hash
                if "-" in cookbook_part and part == "cookbook_artifacts":
                    cookbook_name = cookbook_part.split("-")[0]
                else:
                    cookbook_name = cookbook_part
                break

        if cookbook_name:
            return f"{cookbook_name}::{recipe_name}"
        else:
            return recipe_name

    def _expand_recipe(self, recipe_path: str) -> ExecutionNode:
        """Recursively expand a recipe and its includes."""
        # Prevent circular includes
        if recipe_path in self.visited_recipes:
            return ExecutionNode(
                node_type="recipe",
                name=self._get_recipe_display_name(recipe_path),
                file_path=recipe_path,
                details="[CIRCULAR DEPENDENCY - already visited]",
            )

        self.visited_recipes.add(recipe_path)

        recipe_result = self.recipe_map.get(recipe_path)
        if not recipe_result:
            return ExecutionNode(
                node_type="recipe",
                name=self._get_recipe_display_name(recipe_path),
                file_path=recipe_path,
                details="Recipe not analyzed",
            )

        # Create recipe node with reference to recipe_result (for full file path)
        recipe_node = ExecutionNode(
            node_type="recipe",
            name=self._get_recipe_display_name(recipe_path),
            file_path=recipe_path,
            recipe_result=recipe_result,
        )

        # Process execution order items
        recipe_node.children.extend(
            self._process_execution_items(recipe_result.analysis.execution_order)
        )

        # Check if this recipe has loops to expand
        recipe_node = self._expand_loops_in_recipe(recipe_node, recipe_result)

        return recipe_node

    def _process_execution_items(
        self, execution_order: list[ExecutionItemUnion]
    ) -> list[ExecutionNode]:
        """Process a list of execution order items into ExecutionNodes.

        This method handles both top-level and nested execution items.
        """
        nodes = []

        for item in execution_order:
            if isinstance(item, IncludeRecipeExecution):
                # Recursively expand included recipe
                included_recipe_path = self._resolve_recipe_path(item.recipe_name)

                if included_recipe_path:
                    child_node = self._expand_recipe(included_recipe_path)
                    nodes.append(child_node)
                else:
                    # Recipe not found, add a placeholder
                    nodes.append(
                        ExecutionNode(
                            node_type="recipe",
                            name=item.recipe_name,
                            details="Recipe file not found",
                        )
                    )

            elif isinstance(item, ResourceExecution):
                # Standard Chef resource - pass execution_item for typed formatting
                nodes.append(
                    ExecutionNode(
                        node_type="resource",
                        name=f"{item.resource_type}[{item.name}]",
                        execution_item=item,
                    )
                )

            elif isinstance(item, CustomResourceExecution):
                # Custom resource (LWRP) - pass execution_item for typed formatting
                nodes.append(
                    ExecutionNode(
                        node_type="custom_resource",
                        name=f"{item.resource_type}[{item.name}]",
                        execution_item=item,
                    )
                )

            elif isinstance(item, ConditionalExecution):
                # Conditional block - pass execution_item for typed formatting
                conditional_node = ExecutionNode(
                    node_type="conditional",
                    name=f"if {item.condition}",
                    execution_item=item,
                )

                # Recursively process nested execution_order
                if item.execution_order:
                    conditional_node.children = self._process_execution_items(
                        item.execution_order
                    )

                nodes.append(conditional_node)

        return nodes

    def _expand_loops_in_recipe(
        self, recipe_node: ExecutionNode, recipe_result: RecipeAnalysisResult
    ) -> ExecutionNode:
        """Detect and expand loops in the recipe using attribute collections."""
        # If no attribute collections, no loops to expand
        if not self.analysis.attribute_collections:
            logger.debug(f"No attribute collections to expand in {recipe_node.name}")
            return recipe_node

        logger.debug(
            f"Checking {recipe_node.name} for loops. Available collections: {list(self.analysis.attribute_collections.keys())}"
        )

        # Look for conditional nodes with .each patterns in execution order
        new_children = []
        for child in recipe_node.children:
            # Check if this is a conditional with .each (loop pattern)
            if (
                child.node_type == "conditional"
                and child.name
                and ".each" in child.name
            ):
                logger.info(f"Found .each loop in {recipe_node.name}: {child.name}")
                # This looks like a loop - try to expand it
                expanded = self._try_expand_loop(child)
                new_children.append(expanded)
            else:
                new_children.append(child)

        recipe_node.children = new_children
        return recipe_node

    def _try_expand_loop(self, conditional_node: ExecutionNode) -> ExecutionNode:
        """Try to expand a .each loop into explicit items."""
        # Extract collection name from conditional like "node['nginx']['sites'].each"
        # or "redis_instances.each"
        condition = conditional_node.name
        logger.debug(f"Trying to expand loop with condition: {condition}")

        # Find matching collection in attribute_collections
        for collection_name, items in self.analysis.attribute_collections.items():
            # Match patterns like:
            # - "node['nginx']['sites'].each" -> nginx.sites
            # - "sites.each" -> sites
            # Simple heuristic: if collection_name appears in condition
            collection_parts = collection_name.split(".")
            logger.debug(
                f"Checking collection '{collection_name}' (parts: {collection_parts}) against condition"
            )

            if any(part in condition for part in collection_parts):
                logger.info(
                    f"✓ Matched collection '{collection_name}' with {len(items)} items: {items}"
                )
                # Found matching collection - create LOOP node
                loop_node = ExecutionNode(
                    node_type="loop",
                    name=collection_name,
                    details=f"{len(items)} items",
                )

                # Get attribute values for each item
                item_attributes = self._get_collection_attributes(collection_name)
                logger.debug(f"Extracted attributes for {len(item_attributes)} items")

                # Create loop_item nodes for each item
                for item_name in items:
                    item_attrs = item_attributes.get(item_name, {})
                    loop_item = ExecutionNode(
                        node_type="loop_item",
                        name=item_name,
                        attributes=item_attrs,
                        # Include the original resources from the loop body
                        children=conditional_node.children,
                    )
                    loop_node.children.append(loop_item)

                logger.info(f"✓ Expanded loop into {len(loop_node.children)} items")
                return loop_node

        # No matching collection found, return as-is
        logger.warning(f"No matching collection found for condition: {condition}")
        return conditional_node

    def _get_collection_attributes(self, collection_path: str) -> dict:
        """Get attribute values for a collection path like 'nginx.sites'."""
        result = {}

        # Navigate through attribute files to find the collection values
        for attr_result in self.analysis.attributes:
            attrs = attr_result.analysis.attributes

            # Split path like "nginx.sites" into ["nginx", "sites"]
            parts = collection_path.split(".")
            current = attrs

            # Navigate nested dict
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    current = None
                    break

            # If we found the collection, return it
            if isinstance(current, dict):
                result = current
                break

        return result

    def _resolve_recipe_path(self, recipe_name: str) -> str | None:
        """Resolve recipe name to file path.

        Args:
            recipe_name: Recipe in format "cookbook::recipe" or just "cookbook"
                        - "cookbook::recipe" -> cookbooks/cookbook/recipes/recipe.rb
                        - "cookbook" -> cookbooks/cookbook/recipes/default.rb

        Returns:
            Full path to recipe file, or None if not found
        """
        # Parse recipe name
        if "::" in recipe_name:
            cookbook_name, recipe_file = recipe_name.split("::", 1)
        else:
            # No :: means it's referring to another cookbook's default.rb
            cookbook_name = recipe_name
            recipe_file = "default"

        # Search in recipe_map for matching file
        for path in self.recipe_map:
            path_obj = Path(path)

            # Check if recipe filename matches
            if path_obj.stem != recipe_file:
                continue

            # Verify cookbook name matches in path
            # Path formats to check:
            # - /path/to/cookbooks/{cookbook_name}/recipes/
            # - /path/to/cookbook_artifacts/{cookbook_name}-{hash}/recipes/
            # - /path/to/{cookbook_name}/recipes/

            # Normalize path for matching
            normalized_path = path.replace("\\", "/")

            # Check various path patterns
            if (
                f"/{cookbook_name}/recipes/" in normalized_path
                or f"cookbooks/{cookbook_name}/recipes/" in normalized_path
                or f"cookbook_artifacts/{cookbook_name}-" in normalized_path
            ):
                logger.debug(f"Resolved '{recipe_name}' to {path}")
                return path

        logger.warning(f"Could not resolve recipe path for: {recipe_name}")
        logger.debug(f"Available recipes: {list(self.recipe_map.keys())}")
        return None

    def format_tree(
        self, node: ExecutionNode, prefix: str = "", is_last: bool = True
    ) -> str:
        """Format execution tree as visual ASCII tree."""
        lines = []

        # Format current node
        connector = "└── " if is_last else "├── "
        if not prefix:  # Root node
            connector = ""

        # Use the node's own formatting logic
        label = node.format_label()
        lines.append(f"{prefix}{connector}{label}")

        # Format children
        if node.children:
            for idx, child in enumerate(node.children):
                is_last_child = idx == len(node.children) - 1

                # Build child prefix based on current node position
                extension = "    " if is_last else "│   "
                child_prefix = prefix + extension

                child_lines = self.format_tree(child, child_prefix, is_last_child)
                lines.append(child_lines)

        return "\n".join(lines)
