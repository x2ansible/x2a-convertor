import logging
import re
import tree_sitter_json as tsjson
import tree_sitter_ruby as tsruby

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from tree_sitter import Language, Parser, Node
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# Chef-specific constants
CHEF_RESOURCES = [
    "package",
    "service",
    "file",
    "template",
    "cookbook_file",
    "directory",
    "user",
    "group",
    "execute",
    "script",
    "cron",
    "mount",
    "route",
    "apt_package",
    "yum_package",
    "gem_package",
    "remote_file",
    "link",
    "ruby_block",
    "bash",
    "powershell_script",
]

CHEF_ATTRIBUTES = [
    "action",
    "notifies",
    "subscribes",
    "only_if",
    "not_if",
    "user",
    "group",
    "mode",
    "owner",
    "source",
    "variables",
    "cookbook",
    "template",
    "path",
    "content",
    "command",
    "supports",
]

# Lookup tables for better maintainability

FILE_EXTENSION_PARSER_MAP = {
    ".rb": "ruby",
    ".json": "json",
}

FILE_CATEGORY_MAP = {
    "attributes/": "attributes",
    "recipes/": "recipes",
    "resources/": "resources",
    "metadata.rb": "metadata",
}

IMPORTANT_ATTRIBUTES = {
    "action",
    "source",
    "mode",
    "variables",
    "command",
    "content",
    "path",
}

logger = logging.getLogger(__name__)


@dataclass
class ChefResource:
    """Represents a Chef resource with its properties."""

    type: str
    name: Optional[str]
    line: int
    attributes: Dict[str, Any]
    block_content: Optional[str] = None
    category: str = "other"
    has_dynamic_name: bool = False
    important_attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChefAttribute:
    """Represents a Chef attribute assignment."""

    name: str
    value: str
    line: int
    display_value: str = ""

    def __post_init__(self) -> None:
        if not self.display_value:
            self.display_value = (
                self.value[:77] + "..." if len(self.value) > 80 else self.value
            )


@dataclass
class LoopInfo:
    """Represents a detected loop in Chef code."""

    type: str
    variable: str
    iterator_vars: str
    full_expression: str


@dataclass
class TemplateFile:
    """Represents a Chef template file."""

    path: str
    name: str
    purpose: str


class ChefReporting:
    """Handles generation of LLM-friendly reports for Chef cookbook analysis."""

    def __init__(self) -> None:
        """Initialize the Chef reporting system."""
        pass

    def generate_report(
        self, directory_path: str, analysis_results: Dict[str, Any]
    ) -> str:
        """Generate a comprehensive LLM-friendly report of Chef cookbook structure.

        Args:
            directory_path: Path to the analyzed directory
            analysis_results: Enriched results from TreeSitterAnalyzer.analyze_directory()

        Returns:
            Formatted text report suitable for LLM consumption
        """
        if "error" in analysis_results:
            return f"Error analyzing directory: {analysis_results['error']}"

        # Start building the report
        report_lines = [
            f"**Directory:** {analysis_results.get('directory_path', directory_path)}",
            "",
        ]

        # Use the enriched categorized data
        categorized = analysis_results.get("categorized_files", {})
        template_files = analysis_results.get("template_files", [])

        # Process each file type using enriched data
        self._add_attributes_section(categorized.get("attributes", {}), report_lines)
        self._add_recipes_section(categorized.get("recipes", {}), report_lines)
        self._add_resources_section(categorized.get("resources", {}), report_lines)
        self._add_metadata_section(categorized.get("metadata", {}), report_lines)
        self._add_templates_section(template_files, report_lines)

        return "\n".join(report_lines)

    def _convert_include_to_path(self, include: str) -> str:
        """Convert Chef include_recipe string to file path format.

        Args:
            include: Chef include string like 'cookbook::recipe' or 'recipe'

        Returns:
            Recipe file path like 'recipe.rb'
        """
        # Convert :: to / for namespaced recipes
        path = include.replace("::", "/")

        # Remove cookbook prefix if it matches the pattern cookbook/recipe
        if "/" in path:
            parts = path.split("/")
            if len(parts) == 2:
                # For cookbook::recipe pattern, just use the recipe name
                path = parts[1]
            elif len(parts) > 2:
                # For more complex paths, remove first part (cookbook name)
                path = "/".join(parts[1:])

        return f"{path}.rb"

    def _add_attributes_section(
        self, attributes_files: Dict[str, Any], report_lines: List[str]
    ) -> None:
        """Add attributes files section using enriched data."""
        if not attributes_files:
            return

        report_lines.extend(["**Attributes Files**", ""])

        for file_path, file_data in attributes_files.items():
            report_lines.append(f"**{file_path}:**")

            # Use enriched Chef attributes data
            chef_attributes = file_data.get("chef_attributes", [])
            if chef_attributes:
                report_lines.append("Variables assigned:")
                for attr in chef_attributes:
                    if isinstance(attr, ChefAttribute):
                        report_lines.append(f"  • {attr.name} = {attr.display_value}")
                    else:
                        # Fallback for old dict format
                        name = attr.get("name", "unknown")
                        display_value = attr.get(
                            "display_value", attr.get("value", "N/A")
                        )
                        report_lines.append(f"  • {name} = {display_value}")
            else:
                report_lines.append("No Chef attributes detected")

            report_lines.append("")

    def _add_recipes_section(
        self, recipe_files: Dict[str, Any], report_lines: List[str]
    ) -> None:
        """Add recipe files section using enriched data."""
        if not recipe_files:
            return

        report_lines.extend(["**Recipe Files**", ""])

        for file_path, file_data in recipe_files.items():
            report_lines.append(f"**{file_path}:**")

            # Show includes
            includes = file_data.get("includes", [])
            if includes:
                report_lines.append("**Includes the following recipes:**")
                for include in includes:
                    recipe_file = self._convert_include_to_path(include)
                    report_lines.append(f"  • {recipe_file}")
                report_lines.append("")

            # Show loops
            loops = file_data.get("loops", [])
            if loops:
                for loop in loops:
                    if isinstance(loop, LoopInfo):
                        expr = loop.full_expression
                    else:
                        # Fallback for old dict format
                        expr = loop.get("full_expression", "")
                    report_lines.append(f"  *Loop detected: {expr}*")
                report_lines.append("")

            # Show Chef resources using enriched data
            resources = file_data.get("chef_resources", [])
            if resources:
                report_lines.append("**Chef Resources:**")
                for resource in resources:
                    self._add_enriched_resource(resource, report_lines)

            report_lines.append("")

    def _add_enriched_resource(self, resource, report_lines: List[str]) -> None:
        """Add an enriched Chef resource to the report."""

        resource_type = resource.type
        resource_name = resource.name
        has_dynamic_name = resource.has_dynamic_name
        important_attrs = resource.important_attributes

        if has_dynamic_name:
            report_lines.append(
                f"  • **{resource_type}** (dynamic name: `{resource_name}`)"
            )
        else:
            name_part = f" '{resource_name}'" if resource_name else ""
            report_lines.append(f"  • **{resource_type}**{name_part}")

        # Show important attributes
        if important_attrs:
            attrs_list = [f"{k}: {v}" for k, v in important_attrs.items()]
            report_lines.append(f"    - {', '.join(attrs_list)}")

    def _add_resources_section(
        self, resource_files: Dict[str, Any], report_lines: List[str]
    ) -> None:
        """Add custom resource files section using enriched data."""
        if not resource_files:
            return

        report_lines.extend(["**Custom Resource Files**", ""])

        for file_path, file_data in resource_files.items():
            resource_name = file_data.get("file_stem", Path(file_path).stem)
            report_lines.append(f"**{file_path}:**")
            report_lines.append(f"Custom resource definition: `{resource_name}`")
            report_lines.append("")

    def _add_metadata_section(
        self, metadata_files: Dict[str, Any], report_lines: List[str]
    ) -> None:
        """Add metadata files section using enriched data."""
        if not metadata_files:
            return

        report_lines.extend(["**Cookbook Metadata**", ""])

        for file_path, file_data in metadata_files.items():
            report_lines.append(f"**{file_path}:**")
            report_lines.append(
                "Contains cookbook metadata (name, version, dependencies, etc.)"
            )
            report_lines.append("")

    def _add_templates_section(
        self, template_files: List[TemplateFile], report_lines: List[str]
    ) -> None:
        """Add template files section using enriched data."""
        if not template_files:
            return

        report_lines.extend(["**Template Files**", ""])
        report_lines.append("ERB templates used by the cookbook:")

        for template in template_files:
            if isinstance(template, TemplateFile):
                report_lines.append(f"  • `{template.path}` ({template.purpose})")
            else:
                # Fallback for old dict format
                path = template.get("path", "")
                purpose = template.get("purpose", "template file")
                report_lines.append(f"  • `{path}` ({purpose})")

        report_lines.append("")


class BaseTreeSitterParser(ABC):
    """Base class for tree-sitter parsers with shared functionality."""

    def __init__(self, parser: Parser) -> None:
        """Initialize parser with dependency injection.

        Args:
            parser: Pre-configured tree-sitter Parser instance
        """
        self.parser = parser

    @staticmethod
    def get_node_text(node: Optional[Node], content: bytes) -> str:
        """Get text content of an AST node.

        Args:
            node: Tree-sitter AST node or None
            content: Raw file content as bytes

        Returns:
            Decoded text content or empty string if node is None
        """
        if node is None:
            return ""
        return content[node.start_byte : node.end_byte].decode("utf-8")

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Parse a file and return its structure.

        Args:
            file_path: Path to file to parse

        Returns:
            Dictionary containing parsed structure or error information
        """
        try:
            with open(file_path, "rb") as f:
                content = f.read()

            tree = self.parser.parse(content)
            return self._extract_structure(tree.root_node, content)
        except FileNotFoundError:
            error_msg = f"File not found: {file_path}"
            logger.error(error_msg)
            return {"error": error_msg}
        except PermissionError:
            error_msg = f"Permission denied: {file_path}"
            logger.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Failed to parse {file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}

    @abstractmethod
    def _extract_structure(self, root_node: Node, content: bytes) -> Dict[str, Any]:
        """Extract structure from AST root node.

        Args:
            root_node: Root node of the AST
            content: Raw file content as bytes

        Returns:
            Dictionary containing extracted structure
        """
        pass


class RubyParser(BaseTreeSitterParser):
    """Parser for Ruby files with Chef-specific extraction."""

    @classmethod
    def create(cls) -> "RubyParser":
        """Factory method to create a RubyParser with proper language setup.

        Returns:
            Configured RubyParser instance
        """
        ruby_language = Language(tsruby.language())
        parser = Parser(ruby_language)
        return cls(parser)

    def _extract_structure(self, root_node: Node, content: bytes) -> Dict[str, Any]:
        """Extract Ruby/Chef structure from AST.

        Args:
            root_node: Root node of the Ruby AST
            content: Raw file content as bytes

        Returns:
            Dictionary containing enriched Ruby/Chef structure
        """
        structure = {
            "type": "ruby_file",
            "file_category": "unknown",  # Will be determined later
            "classes": [],
            "methods": [],
            "constants": [],
            "includes": [],
            "requires": [],
            "chef_resources": [],
            "chef_attributes": [],  # Separate Chef attributes
            "loops": [],  # Detected loops
            "summary": {},  # File-level summary
        }

        self._traverse_ruby_node(root_node, content, structure)
        self._enrich_structure(structure, content)
        return structure

    def _traverse_ruby_node(
        self, node: Node, content: bytes, structure: Dict[str, Any]
    ) -> None:
        """Traverse Ruby AST and extract Chef-specific patterns.

        Args:
            node: Current AST node to traverse
            content: Raw file content as bytes
            structure: Structure dictionary to populate
        """
        # Use explicit stack to avoid deep recursion
        stack = [node]

        while stack:
            current_node = stack.pop()

            match current_node.type:
                case "class":
                    class_name = self.get_node_text(
                        current_node.child_by_field_name("name"), content
                    )
                    structure.get("classes", []).append(
                        {"name": class_name, "line": current_node.start_point[0] + 1}
                    )

                case "method":
                    method_name = self.get_node_text(
                        current_node.child_by_field_name("name"), content
                    )
                    structure.get("methods", []).append(
                        {"name": method_name, "line": current_node.start_point[0] + 1}
                    )

                case "call":
                    self._handle_method_call(current_node, content, structure)

                case "assignment":
                    self._handle_assignment(current_node, content, structure)

            # Add children to stack for processing
            stack.extend(reversed(current_node.children))

    def _handle_method_call(
        self, node: Node, content: bytes, structure: Dict[str, Any]
    ) -> None:
        """Handle method call nodes for Chef resources and includes."""
        method_node = node.child_by_field_name("method")
        if not method_node:
            return

        method_name = self.get_node_text(method_node, content)

        match method_name:
            case name if name in CHEF_RESOURCES:
                resource = self._parse_chef_resource(node, content, method_name)
                structure.get("chef_resources", []).append(resource)

            case "include_recipe" | "require":
                args = self._extract_string_args(node, content)
                target_list = (
                    structure.get("includes", [])
                    if method_name == "include_recipe"
                    else structure.get("requires", [])
                )
                target_list.extend(args)

    def _handle_assignment(
        self, node: Node, content: bytes, structure: Dict[str, Any]
    ) -> None:
        """Handle assignment nodes for Chef attributes."""
        left = node.child_by_field_name("left")
        if not left or left.type not in ["constant", "call", "element_reference"]:
            return

        assignment = self._parse_assignment(node, content)
        if assignment:
            structure.get("constants", []).append(assignment)

    def _parse_chef_resource(
        self, node: Node, content: bytes, resource_type: str
    ) -> ChefResource:
        """Parse a Chef resource with its block and attributes.

        Args:
            node: AST node representing the Chef resource
            content: Raw file content as bytes
            resource_type: Type of Chef resource (e.g., 'package', 'service')

        Returns:
            ChefResource instance containing resource information
        """
        resource_name: Optional[str] = None
        attributes = {}
        block_content = None

        # Extract resource name from arguments
        for child in node.children:
            match child.type:
                case "argument_list":
                    for arg in child.children:
                        if arg.type == "string" and resource_name is None:
                            resource_name = self.get_node_text(arg, content).strip(
                                "\"'"
                            )

                case "block" | "do_block":
                    block_content = self.get_node_text(child, content)
                    attributes = self._parse_chef_block(child, content)

        return ChefResource(
            type=resource_type,
            name=resource_name,
            line=node.start_point[0] + 1,
            attributes=attributes,
            block_content=block_content,
        )

    def _parse_chef_block(self, block_node: Node, content: bytes) -> Dict[str, Any]:
        """Parse Chef resource block to extract attributes.

        Args:
            block_node: AST node representing the resource block
            content: Raw file content as bytes

        Returns:
            Dictionary of attribute names to values
        """
        attributes = {}

        # Use explicit stack to avoid deep recursion
        stack = [block_node]

        while stack:
            current_node = stack.pop()

            match current_node.type:
                case "call":
                    method_node = current_node.child_by_field_name("method")
                    if method_node:
                        attr_name = self.get_node_text(method_node, content)
                        if attr_name in CHEF_ATTRIBUTES:
                            attr_value = self._extract_attribute_value(
                                current_node, content
                            )
                            attributes[attr_name] = attr_value

                case "assignment":
                    left = current_node.child_by_field_name("left")
                    right = current_node.child_by_field_name("right")
                    if left and right:
                        attr_name = self.get_node_text(left, content)
                        attr_value = self.get_node_text(right, content)
                        attributes[attr_name] = attr_value

            # Add children to stack for processing
            stack.extend(reversed(current_node.children))

        return attributes

    def _extract_attribute_value(self, node: Node, content: bytes) -> Optional[str]:
        """Extract the value of a Chef resource attribute.

        Args:
            node: AST node containing the attribute call
            content: Raw file content as bytes

        Returns:
            Attribute value as string or None if not found
        """
        for child in node.children:
            if child.type == "argument_list":
                arg_text = self.get_node_text(child, content)
                return arg_text.strip("() ")

        return None

    def _extract_string_args(self, node: Node, content: bytes) -> List[str]:
        """Extract string arguments from a method call.

        Args:
            node: AST node containing the method call
            content: Raw file content as bytes

        Returns:
            List of string arguments
        """
        args = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type == "string":
                        args.append(self.get_node_text(arg, content).strip("\"'"))
        return args

    def _parse_assignment(self, node: Node, content: bytes) -> Optional[Dict[str, Any]]:
        """Parse variable assignments, especially Chef attributes.

        Args:
            node: AST node representing the assignment
            content: Raw file content as bytes

        Returns:
            Dictionary containing assignment information or None if invalid
        """
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")

        if not left or not right:
            return None

        var_name = self.get_node_text(left, content)
        var_value = self.get_node_text(right, content)

        return {
            "name": var_name,
            "value": var_value,
            "type": "chef_attribute"
            if var_name.startswith(("default[", "node["))
            else "variable",
            "line": node.start_point[0] + 1,
        }

    def _enrich_structure(self, structure: Dict[str, Any], content: bytes) -> None:
        """Enrich the structure with additional processed information.

        Args:
            structure: The structure dictionary to enrich
            content: Raw file content as bytes
        """
        # Separate Chef attributes from regular constants
        chef_attributes = []
        regular_constants = []

        for const in structure.get("constants", []):
            if const.get("type") == "chef_attribute":
                chef_attributes.append(
                    ChefAttribute(
                        name=const.get("name", ""),
                        value=const.get("value", ""),
                        line=const.get("line", 0),
                    )
                )
            else:
                regular_constants.append(const)

        structure["chef_attributes"] = chef_attributes
        structure["constants"] = regular_constants

        # Detect loops in the content
        structure["loops"] = self._detect_all_loops(content)

        # Add enriched Chef resources
        structure["chef_resources"] = self._enrich_chef_resources(
            structure.get("chef_resources", [])
        )

    def _detect_all_loops(self, content: bytes) -> List[LoopInfo]:
        """Detect all types of loops in the content."""
        loops = []
        content_str = content.decode("utf-8")

        # Detect .each loops
        each_pattern = r"(\w+(?:\[.*?\])?)\s*\.\s*each\s+do\s*\|\s*([^|]+)\s*\|"
        for match in re.finditer(each_pattern, content_str):
            loops.append(
                LoopInfo(
                    type="each",
                    variable=match.group(1),
                    iterator_vars=match.group(2).strip(),
                    full_expression=match.group(0),
                )
            )

        return loops

    def _enrich_chef_resources(
        self, resources: List[ChefResource]
    ) -> List[ChefResource]:
        """Enrich Chef resources with additional metadata."""
        enriched = []

        for resource in resources:
            # Analyze resource name
            has_dynamic_name = "#{" in resource.name if resource.name else False

            # Extract important attributes for display
            important_attrs = {
                k: v
                for k, v in resource.attributes.items()
                if k in IMPORTANT_ATTRIBUTES
            }

            # Create enriched resource
            enriched_resource = ChefResource(
                type=resource.type,
                name=resource.name,
                line=resource.line,
                attributes=resource.attributes,
                block_content=resource.block_content,
                category="other",  # Simplified - no categorization
                has_dynamic_name=has_dynamic_name,
                important_attributes=important_attrs,
            )

            enriched.append(enriched_resource)

        return enriched


class JsonParser(BaseTreeSitterParser):
    """Parser for JSON files with key extraction."""

    @classmethod
    def create(cls) -> "JsonParser":
        """Factory method to create a JsonParser with proper language setup.

        Returns:
            Configured JsonParser instance
        """
        json_language = Language(tsjson.language())
        parser = Parser(json_language)
        return cls(parser)

    def _extract_structure(self, root_node: Node, content: bytes) -> Dict[str, Any]:
        """Extract JSON structure from AST.

        Args:
            root_node: Root node of the JSON AST
            content: Raw file content as bytes

        Returns:
            Dictionary containing JSON structure
        """
        structure = {"type": "json_file", "keys": [], "structure": {}}

        self._traverse_json_node(root_node, content, structure)
        return structure

    def _traverse_json_node(
        self, node: Node, content: bytes, structure: Dict[str, Any]
    ) -> None:
        """Traverse JSON AST and extract keys.

        Args:
            node: Current AST node to traverse
            content: Raw file content as bytes
            structure: Structure dictionary to populate
        """
        # Use explicit stack to avoid deep recursion
        stack = [node]

        while stack:
            current_node = stack.pop()

            if current_node.type == "pair":
                key_node = current_node.child_by_field_name("key")
                if key_node:
                    key = self.get_node_text(key_node, content).strip('"')
                    structure.get("keys", []).append(key)

            # Add children to stack for processing
            stack.extend(reversed(current_node.children))


class TreeSitterAnalyzer:
    """Main analyzer that coordinates Ruby and JSON parsing."""

    def __init__(
        self,
        ruby_parser: Optional[RubyParser] = None,
        json_parser: Optional[JsonParser] = None,
        reporter: Optional[ChefReporting] = None,
    ) -> None:
        """Initialize analyzer with optional parser injection.

        Args:
            ruby_parser: Optional RubyParser instance for dependency injection
            json_parser: Optional JsonParser instance for dependency injection
            reporter: Optional ChefReporting instance for dependency injection
        """
        self.ruby_parser = ruby_parser or RubyParser.create()
        self.json_parser = json_parser or JsonParser.create()
        self.reporter = reporter or ChefReporting()

    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """Parse a file using the appropriate parser.

        Args:
            file_path: Path to file to parse

        Returns:
            Dictionary containing parsed structure or error information
        """
        try:
            path = Path(file_path)
            file_extension = path.suffix
            parser_type = FILE_EXTENSION_PARSER_MAP.get(file_extension)

            if parser_type == "ruby":
                return self.ruby_parser.parse_file(file_path)
            elif parser_type == "json":
                return self.json_parser.parse_file(file_path)
            else:
                error_msg = f"Unsupported file type: {file_path}"
                logger.warning(error_msg)
                return {"error": error_msg}
        except Exception as e:
            error_msg = f"Failed to determine file type for {file_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}

    def analyze_directory(self, directory_path: str) -> Dict[str, Any]:
        """Analyze all Ruby and JSON files in a directory.

        Args:
            directory_path: Path to directory to analyze

        Returns:
            Dictionary with categorized analysis results and metadata
        """
        try:
            path = Path(directory_path)

            if not path.exists():
                error_msg = f"Directory does not exist: {directory_path}"
                logger.error(error_msg)
                return {"error": error_msg}

            if not path.is_dir():
                error_msg = f"Path is not a directory: {directory_path}"
                logger.error(error_msg)
                return {"error": error_msg}

            # Initialize results structure
            results: Dict[str, Any] = {
                "directory_path": directory_path,
                "files": {},
                "categorized_files": {
                    "attributes": {},
                    "recipes": {},
                    "resources": {},
                    "metadata": {},
                    "other": {},
                },
                "template_files": [],
                "summary": {},
            }

            # Process Ruby files
            for file_path in path.rglob("*.rb"):
                rel_path = self._get_relative_path(str(file_path), directory_path)
                analysis = self.parse_file(str(file_path))

                if "error" not in analysis:
                    # Categorize the file and enrich with metadata
                    analysis = self._categorize_and_enrich_file(analysis, rel_path)

                results["files"][rel_path] = analysis
                self._add_to_category(results["categorized_files"], rel_path, analysis)

            # Process JSON files
            for file_path in path.rglob("*.json"):
                rel_path = self._get_relative_path(str(file_path), directory_path)
                analysis = self.parse_file(str(file_path))
                results["files"][rel_path] = analysis
                self._add_to_category(results["categorized_files"], rel_path, analysis)

            # Find template files
            results["template_files"] = self._find_template_files(directory_path)

            logger.info(f"Analyzed {len(results['files'])} files in {directory_path}")
            return results

        except Exception as e:
            error_msg = f"Failed to analyze directory {directory_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {"error": error_msg}

    def _get_relative_path(self, file_path: str, base_path: str) -> str:
        """Get relative path from base directory."""
        try:
            return str(Path(file_path).relative_to(Path(base_path)))
        except ValueError:
            # Fallback if not relative
            return file_path

    def _categorize_and_enrich_file(
        self, analysis: Dict[str, Any], rel_path: str
    ) -> Dict[str, Any]:
        """Categorize file and add enrichment metadata."""
        # Determine file category using lookup table
        category = "other"  # default
        for pattern, cat in FILE_CATEGORY_MAP.items():
            if rel_path.startswith(pattern) or rel_path == pattern:
                category = cat
                break
        analysis["file_category"] = category

        # Add file metadata
        analysis["file_path"] = rel_path
        analysis["file_name"] = Path(rel_path).name
        analysis["file_stem"] = Path(rel_path).stem

        return analysis

    def _add_to_category(
        self, categorized: Dict[str, Dict], rel_path: str, analysis: Dict[str, Any]
    ) -> None:
        """Add file analysis to appropriate category."""
        category = analysis.get("file_category", "other")
        if category in categorized:
            categorized[category][rel_path] = analysis
        else:
            categorized["other"][rel_path] = analysis

    def _find_template_files(self, directory_path: str) -> List[TemplateFile]:
        """Find and categorize template files."""
        template_files = []
        try:
            path = Path(directory_path)
            for template_path in path.rglob("*.erb"):
                rel_path = template_path.relative_to(path)
                template_files.append(
                    TemplateFile(
                        path=str(rel_path),
                        name=template_path.name,
                        purpose=self._infer_template_purpose(str(rel_path)),
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to scan for template files: {e}")
        return sorted(template_files, key=lambda x: x.path)

    def _infer_template_purpose(self, template_path: str) -> str:
        """Infer the purpose of a template from its path."""
        return "template file"

    def report_directory(self, directory_path: str) -> str:
        """Generate a comprehensive LLM-friendly report of Chef cookbook structure.

        Args:
            directory_path: Path to directory to analyze and report on

        Returns:
            Formatted text report suitable for LLM consumption
        """
        try:
            # Get analysis results
            results = self.analyze_directory(directory_path)

            # Delegate report generation to the ChefReporting class
            return self.reporter.generate_report(directory_path, results)

        except Exception as e:
            error_msg = f"Failed to generate report for {directory_path}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return f"Error generating report: {error_msg}"
