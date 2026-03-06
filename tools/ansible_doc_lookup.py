from __future__ import annotations

import re
import threading
from typing import Any, cast

from ansible import context
from ansible.cli import CLI
from ansible.cli.doc import DocCLI
from ansible.utils.context_objects import CLIArgs
from pydantic import BaseModel, Field

from src.utils.logging import get_logger
from tools.base_tool import X2ATool

logger = get_logger(__name__)

_MARKUP_RE = re.compile(r"[BCILOMRUEV]\(([^)]*)\)")


def _strip_markup(text: str) -> str:
    """Strip Ansible rst-ish markup like C(), V(), O(), I() to plain text."""
    return _MARKUP_RE.sub(r"\1", text)


class DocCLIBridge:
    """Bridge to ansible's DocCLI for loading module documentation.

    Performs one-time DocCLI initialization (plugin loader, collection finder)
    then exposes fast in-process lookups via ``_get_plugins_docs``.
    Works for ALL installed collections -- builtin, community, windows, etc.
    """

    _context_lock = threading.Lock()

    def __init__(self) -> None:
        self._cli = DocCLI(["ansible-doc", "--snippet", "dummy"])
        self._cli.parse()
        CLI.run(self._cli)

    def get_module_docs(self, fqcn: str) -> dict | None:
        """Get full doc dict for a single module FQCN."""
        docs = self._cli._get_plugins_docs("module", [fqcn])
        return docs.get(fqcn)

    def format_module_docs(self, fqcn: str) -> str | None:
        """Format module docs as compact plaintext for LLM consumption.

        Output is one line per parameter with inline metadata (type,
        required, default, choices). Only the first description sentence
        is kept. Ansible markup like C(), V(), O() is stripped.
        """
        plugin_docs = self.get_module_docs(fqcn)
        if not plugin_docs:
            return None

        doc = plugin_docs["doc"]
        return self._format_doc(doc)

    def list_collection_modules(self, collection_fqcn: str) -> dict[str, str]:
        """List modules in a collection with short descriptions.

        Returns a dict of ``{fqcn: short_description}``.
        """
        return self._list_with_args([collection_fqcn])

    def list_all_modules(self) -> dict[str, str]:
        """List all installed modules with short descriptions."""
        return self._list_with_args([])

    def _list_with_args(self, args: list[str]) -> dict[str, str]:
        """Temporarily override CLIARGS to call ``_list_plugins``.

        GlobalCLIArgs is a singleton that cannot be re-created, so we
        swap ``context.CLIARGS`` directly with a plain CLIArgs instance.

        Thread-safe: Uses a class-level lock to serialize global state mutations.
        """

        with self._context_lock:
            original = context.CLIARGS
            context.CLIARGS = CLIArgs(
                {
                    **dict(original),
                    "args": args,
                    "list_dir": True,
                    "list_files": False,
                }
            )
            try:
                # "dir" branch always returns dict[str, str]
                return cast(dict[str, str], self._cli._list_plugins("module", "dir"))
            finally:
                context.CLIARGS = original

    @staticmethod
    def _format_doc(doc: dict) -> str:
        """Render a doc dict as compact plaintext."""
        fqcn = doc.get("plugin_name", doc.get("module", "unknown"))
        short = _strip_markup(doc.get("short_description", ""))
        lines = [f"{fqcn} -- {short}", "", "Parameters:"]

        for name, opt in sorted(doc.get("options", {}).items()):
            meta = _build_param_meta(opt)
            desc = _flatten_description(opt.get("description", ""))
            tag = f" ({', '.join(meta)})" if meta else ""
            lines.append(f"  {name}{tag}: {desc}")

        return "\n".join(lines)


def _build_param_meta(opt: dict) -> list[str]:
    """Build inline metadata tags for a parameter."""
    meta: list[str] = []
    if opt.get("required"):
        meta.append("required")
    if opt.get("type"):
        meta.append(opt["type"])
    if "default" in opt and opt["default"] is not None:
        meta.append(f"default={opt['default']}")
    if "choices" in opt:
        meta.append(f"choices={opt['choices']}")
    return meta


def _flatten_description(raw: str | list) -> str:
    """Join all description sentences and strip Ansible markup."""
    if isinstance(raw, list):
        raw = " ".join(raw)
    return _strip_markup(raw)


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


class AnsibleDocLookupTool(X2ATool):
    """Lookup Ansible module documentation via DocCLI (in-process).

    This tool provides access to documentation for ALL installed Ansible
    collections without subprocess calls. It can list available modules or
    provide snippet-format documentation for specific modules.
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
        self._bridge = DocCLIBridge()

    def _handle_module_lookup(self, module_name: str) -> str:
        """Return compact plaintext documentation for a single module."""
        self.log.debug(f"Looking up documentation for module: {module_name}")
        result = self._bridge.format_module_docs(module_name)

        if result is None:
            return (
                f"ERROR: Module '{module_name}' not found.\n"
                f"Try listing modules with list_filter to find the correct name."
            )

        return result

    def _handle_module_list(self, filter_pattern: str | None) -> str:
        """Return a filtered list of modules with short descriptions."""
        self.log.debug(f"Listing modules with filter: {filter_pattern}")
        all_modules = self._bridge.list_all_modules()

        if filter_pattern:
            filter_lower = filter_pattern.lower()
            all_modules = {
                fqcn: desc
                for fqcn, desc in all_modules.items()
                if filter_lower in fqcn.lower()
            }

        if not all_modules:
            return f"No modules found matching filter: {filter_pattern}"

        header = f"# Available Ansible Modules ({len(all_modules)})\n"
        lines = [f"- {fqcn}: {desc}" for fqcn, desc in sorted(all_modules.items())]
        return header + "\n".join(lines)

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

        self.log.bind(
            module_name=module_name,
            list_filter=list_filter,
        )

        if module_name:
            return self._handle_module_lookup(module_name)

        return self._handle_module_list(list_filter)
