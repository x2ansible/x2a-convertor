"""Puppet dependency fetcher.

Parses Puppetfile to catalog external module dependencies and
downloads them using r10k for analysis.
"""

import shutil
import subprocess
from pathlib import Path

import tree_sitter_ruby as tsruby
from tree_sitter import Language, Node, Parser

from src.utils.logging import get_logger

logger = get_logger(__name__)

_VERSION_SYMBOLS = frozenset({":tag", ":ref", ":branch"})


DEPENDENCIES_DIR = "migration-dependencies"


class PuppetDependencyFetcher:
    """Parse Puppetfile to catalog module dependencies and download them."""

    def __init__(self, module_path: str):
        self._module_path = Path(module_path).resolve()
        self._puppetfile_path = self._find_puppetfile(self._module_path)
        self._dependencies: list[dict] | None = None
        self._parser = Parser(Language(tsruby.language()))
        puppetfile_root = (
            self._puppetfile_path.parent if self._puppetfile_path else self._module_path
        )
        self._deps_dir = puppetfile_root / DEPENDENCIES_DIR

    @staticmethod
    def _find_puppetfile(start: Path) -> Path | None:
        for candidate in [start, *list(start.parents)]:
            pf = candidate / "Puppetfile"
            if pf.is_file():
                return pf
            if candidate == candidate.parent:
                break
        return None

    def has_dependencies(self) -> tuple[bool, list[str]]:
        if self._puppetfile_path is None:
            return False, []
        deps = self.get_dependency_info()
        return bool(deps), [d["name"] for d in deps]

    def get_dependency_info(self) -> list[dict]:
        if self._dependencies is not None:
            return self._dependencies

        if self._puppetfile_path is None:
            logger.info("No Puppetfile found")
            self._dependencies = []
            return self._dependencies

        content = self._puppetfile_path.read_text()
        self._dependencies = self._parse_puppetfile(content)
        logger.info(f"Found {len(self._dependencies)} dependencies in Puppetfile")
        return self._dependencies

    def download_dependencies(self) -> Path | None:
        """Download dependencies using r10k puppetfile install.

        Returns the path to the downloaded modules directory, or None on failure.
        """
        if self._puppetfile_path is None:
            return None

        if not shutil.which("r10k"):
            logger.warning(
                "r10k not found in PATH — cannot download dependencies. "
                "Install with: gem install r10k"
            )
            return None

        self._deps_dir.mkdir(exist_ok=True)
        cmd = [
            "r10k",
            "puppetfile",
            "install",
            "--puppetfile",
            str(self._puppetfile_path),
            "--moduledir",
            str(self._deps_dir),
        ]

        try:
            logger.info(f"Downloading dependencies to {self._deps_dir}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self._module_path),
            )
            if result.returncode != 0:
                logger.error(f"r10k failed: {result.stderr}")
                return None
            logger.info(f"Dependencies downloaded to {self._deps_dir}")
            return self._deps_dir
        except subprocess.TimeoutExpired:
            logger.error("r10k timed out after 300s")
            return None
        except Exception as e:
            logger.error(f"Failed to run r10k: {e}")
            return None

    def _parse_puppetfile(self, content: str) -> list[dict]:
        content_bytes = content.encode()
        tree = self._parser.parse(content_bytes)
        return self._extract_mod_calls(tree.root_node, content_bytes)

    def _extract_mod_calls(self, root: Node, content_bytes: bytes) -> list[dict]:
        deps: list[dict] = []
        git_names: set[str] = set()

        for node in root.children:
            if node.type != "call":
                continue

            identifier = node.child_by_field_name("method")
            if identifier is None:
                for child in node.children:
                    if child.type == "identifier":
                        identifier = child
                        break

            if identifier is None or self._text(identifier, content_bytes) != "mod":
                continue

            dep = self._parse_mod_arguments(node, content_bytes)
            if dep:
                deps.append(dep)
                if dep["source"] == "git":
                    git_names.add(dep["name"])

        return [d for d in deps if d["source"] == "git" or d["name"] not in git_names]

    def _parse_mod_arguments(
        self, call_node: Node, content_bytes: bytes
    ) -> dict | None:
        args = call_node.child_by_field_name("arguments")
        if args is None:
            for child in call_node.children:
                if child.type == "argument_list":
                    args = child
                    break

        if args is None:
            return None

        strings: list[str] = []
        pairs: dict[str, str] = {}

        for child in args.children:
            if child.type == "string":
                strings.append(self._string_content(child, content_bytes))
            elif child.type == "pair":
                key_node = child.children[0] if child.children else None
                val_node = child.children[-1] if len(child.children) >= 3 else None
                if key_node and val_node:
                    key = self._text(key_node, content_bytes)
                    val = self._string_content(val_node, content_bytes)
                    pairs[key] = val

        if not strings:
            return None

        name = strings[0]

        if ":git" in pairs:
            version = "HEAD"
            for sym in _VERSION_SYMBOLS:
                if sym in pairs:
                    version = pairs[sym]
                    break
            return {
                "name": name,
                "source": "git",
                "url": pairs[":git"],
                "version": version,
            }

        return {
            "name": name,
            "source": "forge",
            "url": "",
            "version": strings[1] if len(strings) > 1 else "",
        }

    @staticmethod
    def _text(node: Node, content_bytes: bytes) -> str:
        return content_bytes[node.start_byte : node.end_byte].decode()

    @staticmethod
    def _string_content(node: Node, content_bytes: bytes) -> str:
        for child in node.children:
            if child.type == "string_content":
                return content_bytes[child.start_byte : child.end_byte].decode()
        return content_bytes[node.start_byte : node.end_byte].decode().strip("'\"")
