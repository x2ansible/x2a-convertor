import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.utils.logging import get_logger

logger = get_logger(__name__)

ANSIBLE_BUILTIN_COLLECTION = "ansible.builtin"
MODULE_NAME_PREFIX = f"{ANSIBLE_BUILTIN_COLLECTION}."


@dataclass
class ModuleParameter:
    """Value object representing an Ansible module parameter."""

    name: str
    description: str
    param_type: str | None = None
    required: bool = False
    default: Any | None = None
    choices: list[str] | None = None

    @classmethod
    def from_dict(cls, name: str, param_dict: dict[str, Any]) -> "ModuleParameter":
        """Create ModuleParameter from Ansible's parameter dictionary."""
        description = param_dict.get("description", "")
        if isinstance(description, list):
            description = " ".join(description)

        return cls(
            name=name,
            description=description,
            param_type=param_dict.get("type"),
            required=param_dict.get("required", False),
            default=param_dict.get("default"),
            choices=param_dict.get("choices"),
        )


@dataclass
class ReturnValue:
    """Value object representing an Ansible module return value."""

    name: str
    description: str
    return_type: str | None = None

    @classmethod
    def from_dict(cls, name: str, return_dict: dict[str, Any]) -> "ReturnValue":
        """Create ReturnValue from Ansible's return value dictionary."""
        description = return_dict.get("description", "")
        if isinstance(description, list):
            description = " ".join(description)

        return cls(
            name=name,
            description=description,
            return_type=return_dict.get("type"),
        )


@dataclass
class ModuleInfo:
    """Domain entity representing an Ansible module with its documentation."""

    name: str
    fqcn: str
    short_description: str
    description: str | None = None
    parameters: list[ModuleParameter] = field(default_factory=list)
    examples: str | None = None
    return_values: list[ReturnValue] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        base_name: str,
        doc_dict: dict[str, Any],
        examples: str | None = None,
        return_dict: dict[str, Any] | None = None,
    ) -> "ModuleInfo":
        """Factory method to create ModuleInfo from parsed Ansible documentation."""
        description = doc_dict.get("description")
        if isinstance(description, list):
            description = " ".join(description)

        parameters = [
            ModuleParameter.from_dict(name, param_dict)
            for name, param_dict in doc_dict.get("options", {}).items()
        ]

        return_values = []
        if return_dict:
            return_values = [
                ReturnValue.from_dict(name, ret_dict)
                for name, ret_dict in return_dict.items()
                if isinstance(ret_dict, dict)
            ]

        return cls(
            name=base_name,
            fqcn=f"{MODULE_NAME_PREFIX}{base_name}",
            short_description=doc_dict.get("short_description", ""),
            description=description,
            parameters=parameters,
            examples=examples,
            return_values=return_values,
        )


class ModuleDocumentationFormatter:
    """Formats module documentation as markdown for LLM consumption."""

    @staticmethod
    def format_header(info: ModuleInfo) -> list[str]:
        """Format module header section."""
        return [f"# {info.fqcn}", "", info.short_description, ""]

    @staticmethod
    def format_description(description: str | None) -> list[str]:
        """Format module description section."""
        if not description:
            return []
        return ["## Description", description, ""]

    @staticmethod
    def format_parameter(param: ModuleParameter) -> list[str]:
        """Format a single parameter."""
        lines = []
        req_marker = " (required)" if param.required else ""
        lines.append(f"### {param.name}{req_marker}")
        lines.append(param.description)

        if param.param_type:
            lines.append(f"- Type: {param.param_type}")
        if param.default is not None:
            lines.append(f"- Default: {param.default}")
        if param.choices:
            choices = ", ".join(str(c) for c in param.choices)
            lines.append(f"- Choices: {choices}")

        lines.append("")
        return lines

    @staticmethod
    def format_parameters(parameters: list[ModuleParameter]) -> list[str]:
        """Format all parameters section."""
        if not parameters:
            return []

        lines = ["## Parameters", ""]
        for param in parameters:
            lines.extend(ModuleDocumentationFormatter.format_parameter(param))
        return lines

    @staticmethod
    def format_examples(examples: str | None) -> list[str]:
        """Format examples section."""
        if not examples:
            return []
        return ["## Examples", "", "```yaml", examples.strip(), "```", ""]

    @staticmethod
    def format_return_value(ret_val: ReturnValue) -> list[str]:
        """Format a single return value."""
        lines = [f"### {ret_val.name}", ret_val.description]
        if ret_val.return_type:
            lines.append(f"- Type: {ret_val.return_type}")
        lines.append("")
        return lines

    @staticmethod
    def format_return_values(return_values: list[ReturnValue]) -> list[str]:
        """Format all return values section."""
        if not return_values:
            return []

        lines = ["## Return Values", ""]
        for ret_val in return_values:
            lines.extend(ModuleDocumentationFormatter.format_return_value(ret_val))
        return lines

    def format_module_documentation(self, info: ModuleInfo) -> str:
        """Format complete module documentation."""
        output = []
        output.extend(self.format_header(info))
        output.extend(self.format_description(info.description))
        output.extend(self.format_parameters(info.parameters))
        output.extend(self.format_examples(info.examples))
        output.extend(self.format_return_values(info.return_values))
        return "\n".join(output)


class ModuleDiscoveryService:
    """Infrastructure service for discovering and loading Ansible modules."""

    def __init__(self):
        self._modules_list: list[str] | None = None

    def discover_builtin_modules(self) -> list[str]:
        """Discover all builtin Ansible modules from filesystem."""
        if self._modules_list is not None:
            return self._modules_list

        try:
            import ansible.modules

            modules_path = Path(ansible.modules.__file__).parent
            py_files = modules_path.glob("*.py")

            self._modules_list = sorted(
                [
                    f.stem
                    for f in py_files
                    if f.stem != "__init__" and not f.stem.startswith("_")
                ]
            )
            return self._modules_list

        except Exception as e:
            logger.error(f"Failed to discover builtin modules: {e}")
            return []

    def load_module_documentation(self, base_name: str) -> ModuleInfo | None:
        """Load documentation for a specific module."""
        try:
            mod = importlib.import_module(f"ansible.modules.{base_name}")

            if not hasattr(mod, "DOCUMENTATION"):
                return None

            doc_dict = yaml.safe_load(mod.DOCUMENTATION)
            examples = getattr(mod, "EXAMPLES", None)
            return_dict = self._parse_return_values(mod)

            return ModuleInfo.create(base_name, doc_dict, examples, return_dict)

        except ModuleNotFoundError:
            logger.debug(f"Module not found: {base_name}")
            return None
        except Exception as e:
            logger.error(f"Failed to load module doc for {base_name}: {e}")
            return None

    @staticmethod
    def _parse_return_values(mod: Any) -> dict[str, Any] | None:
        """Parse return values from module, handling malformed YAML."""
        if not hasattr(mod, "RETURN"):
            return None

        try:
            return yaml.safe_load(mod.RETURN)
        except Exception:
            return None


class ModuleNameNormalizer:
    """Domain service for normalizing module names."""

    @staticmethod
    def normalize(module_name: str) -> str:
        """Normalize module name to base name without FQCN prefix."""
        if module_name.startswith(MODULE_NAME_PREFIX):
            return module_name.replace(MODULE_NAME_PREFIX, "")
        return module_name

    @staticmethod
    def to_fqcn(base_name: str) -> str:
        """Convert base module name to FQCN."""
        return f"{MODULE_NAME_PREFIX}{base_name}"


class AnsibleDocLookupInput(BaseModel):
    """Input schema for Ansible documentation lookup."""

    module_name: str | None = Field(
        default=None,
        description="Module name to get documentation for (e.g., 'ansible.builtin.apt', 'apt', 'template'). Leave empty to list all available modules.",
    )
    list_filter: str | None = Field(
        default=None,
        description="Filter pattern when listing modules (e.g., 'apt', 'file', 'template'). Only used when module_name is not provided.",
    )


class ModuleListFormatter:
    """Formats module lists for LLM consumption."""

    def __init__(self, discovery_service: ModuleDiscoveryService):
        self._discovery_service = discovery_service

    def format_module_list(
        self, modules: list[str], filter_pattern: str | None = None
    ) -> str:
        """Format a list of modules with descriptions."""
        if not modules:
            return f"No modules found matching filter: {filter_pattern}"

        output = [f"# Available Ansible Builtin Modules ({len(modules)})", ""]

        for module_name in modules:
            info = self._discovery_service.load_module_documentation(module_name)
            if info:
                output.append(f"- {info.fqcn}: {info.short_description}")
            else:
                output.append(f"- {ModuleNameNormalizer.to_fqcn(module_name)}")

        return "\n".join(output)


class AnsibleDocLookupTool(BaseTool):
    """Lookup Ansible module documentation using pure Python API.

    This tool provides access to Ansible's builtin module documentation without
    subprocess calls. It can list available modules or provide detailed documentation
    for specific modules.
    """

    name: str = "ansible_doc_lookup"
    description: str = (
        "Query Ansible module documentation. "
        "Provide module_name to get detailed docs (parameters, examples, return values). "
        "Leave module_name empty and use list_filter to search for modules by name pattern. "
        "Returns formatted documentation for understanding module usage and parameters."
    )

    args_schema: type[BaseModel] | dict[str, Any] | None = AnsibleDocLookupInput

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._discovery_service = ModuleDiscoveryService()
        self._doc_formatter = ModuleDocumentationFormatter()
        self._list_formatter = ModuleListFormatter(self._discovery_service)

    def _load_module(self, module_name: str) -> ModuleInfo | None:
        """Load module documentation."""
        base_name = ModuleNameNormalizer.normalize(module_name)
        return self._discovery_service.load_module_documentation(base_name)

    def _filter_modules(
        self, modules: list[str], filter_pattern: str | None
    ) -> list[str]:
        """Filter module list by pattern."""
        if not filter_pattern:
            return modules

        filter_lower = filter_pattern.lower()
        return [m for m in modules if filter_lower in m.lower()]

    def _handle_module_lookup(self, module_name: str) -> str:
        """Handle detailed module documentation lookup."""
        logger.debug(f"Looking up documentation for module: {module_name}")
        info = self._load_module(module_name)

        if info is None:
            return (
                f"ERROR: Module '{module_name}' not found in {ANSIBLE_BUILTIN_COLLECTION} collection.\n"
                f"Try listing modules with list_filter to find the correct name."
            )

        return self._doc_formatter.format_module_documentation(info)

    def _handle_module_list(self, filter_pattern: str | None) -> str:
        """Handle module listing."""
        logger.debug(f"Listing modules with filter: {filter_pattern}")
        all_modules = self._discovery_service.discover_builtin_modules()
        filtered_modules = self._filter_modules(all_modules, filter_pattern)
        return self._list_formatter.format_module_list(filtered_modules, filter_pattern)

    def _run(self, *args: Any, **kwargs: Any) -> str:
        """Execute the ansible_doc_lookup tool.

        Args:
            module_name: Specific module to get documentation for
            list_filter: Filter pattern when listing modules

        Returns:
            Formatted documentation or module list
        """
        module_name = kwargs.get("module_name")
        list_filter = kwargs.get("list_filter")

        logger.bind(
            phase="AnsibleDocLookupTool",
            module_name=module_name,
            list_filter=list_filter,
        )

        if module_name:
            return self._handle_module_lookup(module_name)

        return self._handle_module_list(list_filter)
